from __future__ import annotations

import asyncio
import getpass
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pwinput  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]
from reolink_aio.api import Host

from .provider import CHANNEL, SETTING_ALIASES, UnsupportedSettingError, read_setting

DEFAULT_CAMERAS_FILE = Path("cameras.yaml")
# reolink-aio defaults to a 30s *per-request* timeout, and when port/https
# aren't specified (as here) login() probes HTTPS:443, then HTTP:80, then a
# separate Baichuan protocol handshake -- sequentially, each getting its own
# budget. REQUEST_TIMEOUT bounds each individual request (passed as
# Host(timeout=...)). CONNECT_TIMEOUT is the *separate*, larger outer budget
# for the whole attempt (used by asyncio.wait_for around the full connect),
# and must comfortably exceed REQUEST_TIMEOUT -- a real camera that only
# answers on the second protocol tried needs the first (failing) attempt to
# finish *and still leave time* for the one that succeeds. Setting these to
# the same value (an earlier version of this file did) means the first
# attempt alone can consume the entire outer budget, cancelling the whole
# connection before the fallback that would have worked ever runs -- this
# was caught after real cameras that needed the HTTP or Baichuan fallback
# started failing to connect even though they were reachable. An
# unreachable host exhausting every fallback in sequence was measured at
# ~33s with a 10s per-request timeout, so 40s comfortably covers that
# worst case.
REQUEST_TIMEOUT = 10
CONNECT_TIMEOUT = 40


def _prompt_password(prompt: str) -> str:
    """Prompt for a password, masked with asterisks via pwinput.

    pwinput needs raw access to the terminal and only falls back to getpass
    when sys.stdin has been reassigned to something else -- it does *not*
    detect plain piped/non-tty stdin (e.g. shell redirection), where it
    raises a raw termios error instead. Falling back to getpass (hidden, no
    asterisks, but battle-tested against exactly this case) here keeps that
    from crashing with a traceback.
    """
    try:
        result: str = pwinput.pwinput(prompt)
        return result
    except Exception:
        return getpass.getpass(prompt)


def prompt_connection_details(
    input_fn: Callable[[str], str] = input,
    password_input_fn: Callable[[str], str] = _prompt_password,
) -> dict[str, str]:
    """Collect host/username/password, one prompt per field.

    The password uses a separate injectable function (pwinput by default,
    which masks input with asterisks) so it can stay hidden in real use
    while still being testable with a plain fake in tests. Isolating all
    prompts behind injectable functions (rather than calling input()/
    pwinput() inline) lets tests drive this with parameterized fixtures
    instead of real stdin.
    """
    return {
        "host": input_fn("Host/IP: "),
        "username": input_fn("Username: "),
        "password": password_input_fn("Password: "),
    }


def prompt_camera_name(default: str, input_fn: Callable[[str], str] = input) -> str:
    """Prompt for the camera's Pulumi resource name, defaulting to `default`.

    `default` is the camera's own configured name (read from the device
    itself), so most users can just press Enter; typing something else
    overrides it.
    """
    typed = input_fn(f"Camera Name [{default}]: ").strip()
    return typed or default


def slugify_password_key(name: str) -> str:
    """Derive a stable Pulumi config key from a camera name.

    E.g. "Front Doorbell" -> "front-doorbell-password".
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug or 'camera'}-password"


async def _connect(host: str, username: str, password: str) -> Host:
    client = Host(host, username, password, timeout=REQUEST_TIMEOUT)
    await client.login()
    try:
        # Discovers the camera's channels and capabilities. Without this,
        # get_states() has no channels to iterate and every setting getter
        # silently falls back to its default (False/0) instead of the real
        # value.
        await client.get_host_data()
        await client.get_states()
    except Exception:
        # Don't leak a logged-in session on a failed post-login step --
        # repeated failed bootstrap attempts could otherwise exhaust the
        # camera's session limit.
        await client.logout()
        raise
    return client


def _query_settings(client: Host) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for key in SETTING_ALIASES:
        try:
            settings[key] = read_setting(client, CHANNEL, key)
        except UnsupportedSettingError:
            continue
    return settings


def append_camera(cameras_file: Path, entry: dict[str, Any]) -> None:
    """Append `entry` to the `cameras:` list in `cameras_file`, creating it if needed."""
    cameras: list[dict[str, Any]] = []
    if cameras_file.exists():
        try:
            loaded = yaml.safe_load(cameras_file.read_text())
        except yaml.YAMLError as exc:
            raise ValueError(f"{cameras_file} contains invalid YAML: {exc}") from exc
        cameras = list((loaded or {}).get("cameras") or [])
    cameras.append(entry)
    cameras_file.write_text(yaml.safe_dump({"cameras": cameras}, sort_keys=False))


async def _connect_and_gather(
    host: str, username: str, password: str
) -> tuple[str, dict[str, Any]]:
    client = await _connect(host, username, password)
    try:
        return client.camera_name(CHANNEL), _query_settings(client)
    finally:
        await client.logout()


def run_bootstrap(
    input_fn: Callable[[str], str] = input,
    cameras_file: Path = DEFAULT_CAMERAS_FILE,
    password_input_fn: Callable[[str], str] = _prompt_password,
) -> dict[str, Any]:
    connection = prompt_connection_details(input_fn, password_input_fn)

    print(f"Connecting to {connection['host']}...")
    try:
        fetched_name, settings = asyncio.run(
            asyncio.wait_for(
                _connect_and_gather(
                    connection["host"], connection["username"], connection["password"]
                ),
                timeout=CONNECT_TIMEOUT,
            )
        )
    except Exception as exc:
        print(f"\nCould not connect to {connection['host']}: {type(exc).__name__}: {exc}")
        print("Check the host/IP, username, and password, then try again.")
        sys.exit(1)

    print(f"Connected. Camera reports its name as '{fetched_name}'.")
    skipped = len(SETTING_ALIASES) - len(settings)
    if skipped:
        print(
            f"Retrieved {len(settings)} setting(s); {skipped} not supported "
            "by this camera and skipped."
        )
    else:
        print(f"Retrieved {len(settings)} setting(s).")

    name = prompt_camera_name(fetched_name, input_fn)
    password_key = slugify_password_key(name)

    entry: dict[str, Any] = {
        "name": name,
        "host": connection["host"],
        "username": connection["username"],
        "password_key": password_key,
        "settings": settings,
    }
    print(f"Saving configuration to {cameras_file}...")
    append_camera(cameras_file, entry)
    print(f"Saved. '{name}' added to {cameras_file}.")

    print(
        "Run this to store the password securely "
        "(replace <password> with the one you just entered):"
    )
    print(f'  pulumi config set --secret {password_key} "<password>"')
    return entry


def main() -> None:
    run_bootstrap()


if __name__ == "__main__":  # pragma: no cover
    main()
