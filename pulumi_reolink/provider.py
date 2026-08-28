from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pulumi
from pulumi import dynamic
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


# The provider connects to a single camera per resource; multi-channel NVRs
# are out of scope for the initial implementation, so we always target the
# NVR's own channel 0 (which is the camera itself for standalone devices).
CHANNEL = 0


async def _connect(host: str, port: int | None, username: str, password: str) -> Host:
    client = Host(host, username, password, port=port)
    await client.login()
    return client


async def _read_settings(client: Host, keys: list[str]) -> dict[str, Any]:
    await client.get_states()
    return {key: read_setting(client, CHANNEL, key) for key in keys}


async def _apply_settings(client: Host, settings: dict[str, Any]) -> None:
    for key, value in settings.items():
        await apply_setting(client, CHANNEL, key, value)


def _resource_id(props: dict[str, Any]) -> str:
    return f"{props['host']}:{props.get('port') or 'default'}"


class _ReolinkDeviceProvider(dynamic.ResourceProvider):
    def create(self, props: dict[str, Any]) -> dynamic.CreateResult:
        async def run() -> dict[str, Any]:
            client = await _connect(
                props["host"], props.get("port"), props["username"], props["password"]
            )
            try:
                settings = props.get("settings") or {}
                await _apply_settings(client, settings)
                return await _read_settings(client, list(settings))
            finally:
                await client.logout()

        current = asyncio.run(run())
        outs = {**props, "settings": current}
        return dynamic.CreateResult(id_=_resource_id(props), outs=outs)

    def diff(self, _id: str, olds: dict[str, Any], news: dict[str, Any]) -> dynamic.DiffResult:
        replaces = [key for key in ("host", "port", "username") if olds.get(key) != news.get(key)]
        changed = (
            bool(replaces)
            or olds.get("password") != news.get("password")
            or olds.get("settings") != news.get("settings")
        )
        return dynamic.DiffResult(changes=changed, replaces=replaces)

    def update(self, _id: str, olds: dict[str, Any], news: dict[str, Any]) -> dynamic.UpdateResult:
        async def run() -> dict[str, Any]:
            client = await _connect(
                news["host"], news.get("port"), news["username"], news["password"]
            )
            try:
                old_settings = olds.get("settings") or {}
                new_settings = news.get("settings") or {}
                changed_settings = {
                    key: value
                    for key, value in new_settings.items()
                    if old_settings.get(key) != value
                }
                await _apply_settings(client, changed_settings)
                return await _read_settings(client, list(new_settings))
            finally:
                await client.logout()

        current = asyncio.run(run())
        return dynamic.UpdateResult(outs={**news, "settings": current})

    def read(self, id_: str, props: dict[str, Any]) -> dynamic.ReadResult:
        async def run() -> dict[str, Any]:
            client = await _connect(
                props["host"], props.get("port"), props["username"], props["password"]
            )
            try:
                return await _read_settings(client, list(props.get("settings") or {}))
            finally:
                await client.logout()

        current = asyncio.run(run())
        return dynamic.ReadResult(id_=id_, outs={**props, "settings": current})

    def delete(self, _id: str, _props: dict[str, Any]) -> None:
        # Removing the resource from IaC must never mutate the physical
        # camera or reset its settings out-of-band changes remain intact.
        return None


class ReolinkDevice(dynamic.Resource):
    """A Pulumi dynamic resource managing settings on a single Reolink camera or doorbell.

    Connects to `host` over HTTP via `reolink-aio` to apply `settings` --
    a dict of stable setting names (see `SETTING_ALIASES`) to desired
    values. `create`/`update` apply changed settings; `read` (used by
    `pulumi refresh`) re-queries the camera to support drift detection.
    Removing the resource from your Pulumi program never mutates the
    physical camera -- `delete` is a no-op.

    Args:
        name: The Pulumi resource name.
        host: The camera's IP address or hostname.
        username: Admin username to authenticate with.
        password: Admin password; pass a secret Output (e.g. from
            `pulumi.Config().require_secret(...)`) to keep it encrypted
            in stack state.
        settings: Desired setting values, keyed by stable alias name.
        port: The HTTP/HTTPS port, if not the camera's default.
        opts: Standard Pulumi `ResourceOptions`.
    """

    host: pulumi.Output[str]
    port: pulumi.Output[int | None]
    username: pulumi.Output[str]
    password: pulumi.Output[str]
    settings: pulumi.Output[dict[str, Any]]

    def __init__(
        self,
        name: str,
        host: pulumi.Input[str],
        username: pulumi.Input[str],
        password: pulumi.Input[str],
        settings: pulumi.Input[dict[str, Any]] | None = None,
        port: pulumi.Input[int] | None = None,
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        props: dict[str, Any] = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "settings": settings if settings is not None else {},
        }
        secret_opts = pulumi.ResourceOptions(additional_secret_outputs=["password"])
        super().__init__(
            _ReolinkDeviceProvider(), name, props, pulumi.ResourceOptions.merge(secret_opts, opts)
        )
