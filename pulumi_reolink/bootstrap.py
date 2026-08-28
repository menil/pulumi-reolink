from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from reolink_aio.api import Host

from .provider import CHANNEL, SETTING_ALIASES, UnsupportedSettingError, read_setting

DEFAULT_CAMERAS_FILE = Path("cameras.yaml")


def prompt_connection_details(input_fn: Callable[[str], str] = input) -> dict[str, str]:
    """Collect host/username/password via `input_fn`, one prompt per field.

    Isolating the prompts behind an injectable `input_fn` (rather than
    calling `input()` inline throughout the workflow) lets tests drive this
    with parameterized fixtures instead of real stdin.
    """
    return {
        "host": input_fn("Host/IP: "),
        "username": input_fn("Username: "),
        "password": input_fn("Password: "),
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
    client = Host(host, username, password)
    await client.login()
    await client.get_states()
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
) -> dict[str, Any]:
    connection = prompt_connection_details(input_fn)
    fetched_name, settings = asyncio.run(
        _connect_and_gather(connection["host"], connection["username"], connection["password"])
    )
    name = prompt_camera_name(fetched_name, input_fn)
    password_key = slugify_password_key(name)

    entry: dict[str, Any] = {
        "name": name,
        "host": connection["host"],
        "username": connection["username"],
        "password_key": password_key,
        "settings": settings,
    }
    append_camera(cameras_file, entry)
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
