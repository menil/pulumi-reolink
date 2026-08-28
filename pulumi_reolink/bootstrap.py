from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from reolink_aio.api import Host

from .provider import CHANNEL, SETTING_ALIASES, UnsupportedSettingError, read_setting

DEFAULT_CAMERAS_FILE = Path("cameras.yaml")


def prompt_camera_details(input_fn: Callable[[str], str] = input) -> dict[str, str]:
    """Collect camera connection details via `input_fn`, one prompt per field.

    Isolating the prompts behind an injectable `input_fn` (rather than
    calling `input()` inline throughout the workflow) lets tests drive this
    with parameterized fixtures instead of real stdin.
    """
    return {
        "name": input_fn("Camera Name: "),
        "host": input_fn("Host/IP: "),
        "username": input_fn("Username: "),
        "password": input_fn("Password: "),
        "password_key": input_fn("Secret Config Key: "),
    }


async def _query_settings(host: str, username: str, password: str) -> dict[str, Any]:
    client = Host(host, username, password)
    await client.login()
    try:
        await client.get_states()
        settings: dict[str, Any] = {}
        for key in SETTING_ALIASES:
            try:
                settings[key] = read_setting(client, CHANNEL, key)
            except UnsupportedSettingError:
                continue
        return settings
    finally:
        await client.logout()


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


def run_bootstrap(
    input_fn: Callable[[str], str] = input,
    cameras_file: Path = DEFAULT_CAMERAS_FILE,
) -> dict[str, Any]:
    details = prompt_camera_details(input_fn)
    settings = asyncio.run(
        _query_settings(details["host"], details["username"], details["password"])
    )
    entry: dict[str, Any] = {
        "name": details["name"],
        "host": details["host"],
        "username": details["username"],
        "password_key": details["password_key"],
        "settings": settings,
    }
    append_camera(cameras_file, entry)
    print(
        "Run this to store the password securely "
        "(replace <password> with the one you just entered):"
    )
    print(f'  pulumi config set --secret {details["password_key"]} "<password>"')
    return entry


def main() -> None:
    run_bootstrap()
