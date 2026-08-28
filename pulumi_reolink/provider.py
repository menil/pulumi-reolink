from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from reolink_aio.api import Host
from reolink_aio.exceptions import ReolinkError

Getter = Callable[[Host, int], Any]
Setter = Callable[[Host, int, Any], Awaitable[None]]


class UnsupportedSettingError(ReolinkError):
    """A setting is unknown to pulumi_reolink, or rejected by the connected camera."""


@dataclass(frozen=True)
class SettingAlias:
    """Maps a stable IaC setting name to a `reolink_aio.api.Host` getter/setter pair.

    Keeping this mapping isolated from the rest of the provider means that if
    Reolink or reolink-aio renames the underlying API, only this table needs
    updating; user configuration written against the alias names is unaffected.
    """

    get: Getter
    set: Setter


SETTING_ALIASES: dict[str, SettingAlias] = {
    "status_led": SettingAlias(
        get=lambda host, channel: host.status_led_enabled(channel),
        set=lambda host, channel, value: host.set_status_led(channel, value),
    ),
    "ir_lights": SettingAlias(
        get=lambda host, channel: host.ir_enabled(channel),
        set=lambda host, channel, value: host.set_ir_lights(channel, value),
    ),
    "push_notifications": SettingAlias(
        get=lambda host, channel: host.push_enabled(channel),
        set=lambda host, channel, value: host.set_push(channel, value),
    ),
    "recording": SettingAlias(
        get=lambda host, channel: host.recording_enabled(channel),
        set=lambda host, channel, value: host.set_recording(channel, value),
    ),
    "motion_sensitivity": SettingAlias(
        get=lambda host, channel: host.md_sensitivity(channel),
        set=lambda host, channel, value: host.set_md_sensitivity(channel, value),
    ),
    "ptz_guard_enabled": SettingAlias(
        get=lambda host, channel: host.ptz_guard_enabled(channel),
        set=lambda host, channel, value: host.set_ptz_guard(channel, enable=value),
    ),
}


def _resolve_alias(host: Host, key: str) -> SettingAlias:
    """Look up `key` in SETTING_ALIASES, falling back to dynamic reflection.

    The fallback inspects `host` for a `set_<key>` method and, if present, a
    bare `<key>` getter. It only supports settings whose setter accepts the
    value as its second positional argument (after `channel`) -- settings
    that need extra keyword arguments must be added to SETTING_ALIASES
    explicitly, since there is no reliable way to infer them by name alone.
    """
    alias = SETTING_ALIASES.get(key)
    if alias is not None:
        return alias

    setter = getattr(host, f"set_{key}", None)
    if not callable(setter):
        raise UnsupportedSettingError(
            f"'{key}' is not a known pulumi_reolink setting, and the connected "
            f"camera has no 'set_{key}' method to fall back on."
        )
    getter = getattr(host, key, None)

    def reflected_get(host: Host, channel: int) -> Any:
        # Some real reolink-aio settings (e.g. the siren) are write-only
        # actions with no getter, so a missing getter must not silently
        # block the setter fallback above -- but reading one must fail
        # loudly rather than fabricate a None value that would corrupt
        # diff/drift-detection output.
        if not callable(getter):
            raise UnsupportedSettingError(
                f"'{key}' has no bare '{key}' getter on the connected camera to read from."
            )
        return getter(channel)

    def reflected_set(host: Host, channel: int, value: Any) -> Awaitable[None]:
        result: Awaitable[None] = setter(channel, value)
        return result

    return SettingAlias(get=reflected_get, set=reflected_set)


def read_setting(host: Host, channel: int, key: str) -> Any:
    """Read the current value of `key` from an already-refreshed `host`."""
    alias = _resolve_alias(host, key)
    try:
        return alias.get(host, channel)
    except ReolinkError as exc:
        raise UnsupportedSettingError(
            f"Could not read setting '{key}' from the camera: {exc}"
        ) from exc


async def apply_setting(host: Host, channel: int, key: str, value: Any) -> None:
    """Apply `value` for `key` on `host`, raising UnsupportedSettingError on failure.

    Reolink-aio's setters already validate model support and value shape
    internally and raise a descriptive ReolinkError when a setting is
    unsupported or invalid; that message is preserved and re-raised as an
    UnsupportedSettingError so IaC deployments fail with a clear explanation
    instead of silently no-opping.
    """
    alias = _resolve_alias(host, key)
    try:
        await alias.set(host, channel, value)
    except ReolinkError as exc:
        raise UnsupportedSettingError(f"Could not apply setting '{key}': {exc}") from exc


class ReolinkDevice:
    pass
