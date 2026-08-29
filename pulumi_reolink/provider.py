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


def _sentinel_guarded_getter(getter_name: str, sentinel: Any, label: str) -> Getter:
    """Build a getter that raises UnsupportedSettingError instead of
    returning `sentinel`.

    Some reolink-aio getters return a plausible-looking default (0, -1,
    None, ...) instead of raising when a channel hasn't reported that
    setting -- e.g. HDR_state() returns -1, which isn't a valid HDREnum
    member, when re-applied via set_HDR() on a real camera that had never
    reported ISP/HDR data. Treating the sentinel as unsupported, the same
    as any other unsupported setting, keeps it from being captured by
    bootstrap and later rejected by the setter.
    """

    def get(host: Host, channel: int) -> Any:
        value = getattr(host, getter_name)(channel)
        if value == sentinel:
            raise UnsupportedSettingError(f"{label} is not available on channel {channel}.")
        return value

    return get


def _device_level_getter(capability: str, getter_name: str) -> Getter:
    """Build a getter for a setting that must be queried device-wide
    (channel=None) rather than per-channel.

    reolink-aio's push_enabled()/recording_enabled()/ftp_enabled()/
    email_enabled()/buzzer_enabled() (and their setters) accept
    `channel: int | None`, where an int channel checks a per-channel *NVR
    scheduling* flag and `None` checks the plain device-level aggregate
    flag instead -- confirmed via buzzer_enabled()'s source, which checks
    `"scheduleEnable"` for an int channel but the plain `"enable"` flag for
    `None`. Since this provider always targets a single standalone camera
    (never an NVR), calling these with our usual per-resource channel
    silently probes the wrong, NVR-only flag -- which is exactly what made
    a real, working setting (e.g. FTP upload, visible and working in Home
    Assistant) report as unsupported here. Home Assistant itself branches
    on `is_nvr`/`is_hub` to pick between the two; since we're standalone
    only, we always use `None`.
    """

    def get(host: Host, _channel: int) -> Any:
        if not host.supported(None, capability):
            raise UnsupportedSettingError(f"'{capability}' is not supported by this camera.")
        return getattr(host, getter_name)(None)

    return get


def _privacy_mode_getter(host: Host, channel: int) -> Any:
    # baichuan.privacy_mode() returns None when the channel hasn't reported
    # a value yet, the same "plausible but not real" ambiguity HDR/day-night
    # already guard against -- writing None into cameras.yaml would later
    # break set_privacy_mode(channel, enable=None).
    value = host.baichuan.privacy_mode(channel)
    if value is None:
        raise UnsupportedSettingError(
            f"Privacy mode has not been reported by this camera on channel {channel}."
        )
    return value


def _ai_sensitivity_getter(ai_type: str) -> Getter:
    """Build a getter for one AI detection type's sensitivity.

    ai_sensitivity(channel, ai_type) returns 0 -- a legitimate in-range
    value, not a dedicated sentinel -- when the channel hasn't reported
    that ai_type's settings yet, the same ambiguity motion_sensitivity
    already handles via `_sentinel_guarded_getter`; done manually here
    since this getter takes an extra `ai_type` argument that helper
    doesn't support.
    """

    # `get` closes over `ai_type` so each of the three AI-sensitivity
    # SETTING_ALIASES entries (animal/person/cry) gets its own getter from
    # this one factory, without needing three near-identical functions.
    def get(host: Host, channel: int) -> Any:
        value = host.ai_sensitivity(channel, ai_type)
        if value == 0:
            raise UnsupportedSettingError(
                f"AI '{ai_type}' sensitivity has not been reported by this camera "
                f"on channel {channel}."
            )
        return value

    return get


def _capability_checked_getter(capability: str, getter: Getter) -> Getter:
    """Wrap `getter` so it raises UnsupportedSettingError unless the camera
    reports `capability` as supported.

    Mirrors the check reolink-aio's own setters use internally (e.g.
    set_HDR() checks host.supported(channel, "HDR") before doing anything
    else) and the pattern Home Assistant's reolink integration uses to
    decide whether to expose a control at all. Some getters (e.g.
    HDR_state()) return a plausible-looking value even on a camera that
    can't act on it -- found on a real camera whose HDR_state() returned 0
    despite the model having no ISP HDR control, which bootstrap then
    captured and set_HDR() rejected on `pulumi up` regardless of value.
    Checking the same capability flag up front, before the getter runs,
    keeps that from being captured in the first place.
    """

    def get(host: Host, channel: int) -> Any:
        if not host.supported(channel, capability):
            raise UnsupportedSettingError(
                f"'{capability}' is not supported by this camera on channel {channel}."
            )
        return getter(host, channel)

    return get


# Single source of truth for each alias's reolink-aio capability key, cross-
# checked against the installed reolink-aio source (both its HTTP-API and
# Baichuan-protocol capability probes) rather than assumed -- also imported
# by the test suite, so a capability string only ever needs updating here.
CAPABILITY_BY_ALIAS: dict[str, str] = {
    "status_led": "status_led",
    "ir_lights": "ir_lights",
    "push_notifications": "push",
    "recording": "recording",
    "motion_sensitivity": "md_sensitivity",
    "ptz_guard_enabled": "ptz_guard",
    "ftp_recording": "ftp",
    "email_notifications": "email",
    "hdr": "HDR",
    "daynight_mode": "dayNight",
    "audio_recording": "audio",
    "privacy_mask": "privacy_mask",
    "buzzer": "buzzer",
    "speaker_volume": "volume",
    "ai_animal_sensitivity": "ai_dog_cat",
    "ai_person_sensitivity": "ai_people",
    "baby_cry_sensitivity": "ai_cry",
    "auto_tracking": "auto_track",
    "guard_return_time": "ptz_guard",
    "privacy_mode": "privacy_mode",
    "siren_on_event": "siren",
}


SETTING_ALIASES: dict[str, SettingAlias] = {
    "status_led": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["status_led"],
            lambda host, channel: host.status_led_enabled(channel),
        ),
        set=lambda host, channel, value: host.set_status_led(channel, value),
    ),
    "ir_lights": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["ir_lights"], lambda host, channel: host.ir_enabled(channel)
        ),
        set=lambda host, channel, value: host.set_ir_lights(channel, value),
    ),
    "push_notifications": SettingAlias(
        get=_device_level_getter(CAPABILITY_BY_ALIAS["push_notifications"], "push_enabled"),
        set=lambda host, channel, value: host.set_push(None, value),
    ),
    "recording": SettingAlias(
        get=_device_level_getter(CAPABILITY_BY_ALIAS["recording"], "recording_enabled"),
        set=lambda host, channel, value: host.set_recording(None, value),
    ),
    "motion_sensitivity": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["motion_sensitivity"],
            _sentinel_guarded_getter("md_sensitivity", 0, "Motion sensitivity"),
        ),
        set=lambda host, channel, value: host.set_md_sensitivity(channel, value),
    ),
    "ptz_guard_enabled": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["ptz_guard_enabled"],
            lambda host, channel: host.ptz_guard_enabled(channel),
        ),
        set=lambda host, channel, value: host.set_ptz_guard(channel, enable=value),
    ),
    "ftp_recording": SettingAlias(
        get=_device_level_getter(CAPABILITY_BY_ALIAS["ftp_recording"], "ftp_enabled"),
        set=lambda host, channel, value: host.set_ftp(None, value),
    ),
    "email_notifications": SettingAlias(
        get=_device_level_getter(CAPABILITY_BY_ALIAS["email_notifications"], "email_enabled"),
        set=lambda host, channel, value: host.set_email(None, value),
    ),
    "hdr": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["hdr"], _sentinel_guarded_getter("HDR_state", -1, "HDR")
        ),
        set=lambda host, channel, value: host.set_HDR(channel, value),
    ),
    "daynight_mode": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["daynight_mode"],
            _sentinel_guarded_getter("daynight_state", None, "Day/night mode"),
        ),
        set=lambda host, channel, value: host.set_daynight(channel, value),
    ),
    "audio_recording": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["audio_recording"],
            lambda host, channel: host.audio_record(channel),
        ),
        set=lambda host, channel, value: host.set_audio(channel, value),
    ),
    "privacy_mask": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["privacy_mask"],
            lambda host, channel: host.privacy_mask_enabled(channel),
        ),
        set=lambda host, channel, value: host.set_privacy_mask(channel, value),
    ),
    "buzzer": SettingAlias(
        get=_device_level_getter(CAPABILITY_BY_ALIAS["buzzer"], "buzzer_enabled"),
        set=lambda host, channel, value: host.set_buzzer(None, value),
    ),
    "speaker_volume": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["speaker_volume"], lambda host, channel: host.volume(channel)
        ),
        set=lambda host, channel, value: host.set_volume(channel, volume=value),
    ),
    "ai_animal_sensitivity": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["ai_animal_sensitivity"], _ai_sensitivity_getter("dog_cat")
        ),
        set=lambda host, channel, value: host.set_ai_sensitivity(channel, value, ai_type="dog_cat"),
    ),
    "ai_person_sensitivity": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["ai_person_sensitivity"], _ai_sensitivity_getter("people")
        ),
        set=lambda host, channel, value: host.set_ai_sensitivity(channel, value, ai_type="people"),
    ),
    "baby_cry_sensitivity": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["baby_cry_sensitivity"], _ai_sensitivity_getter("cry")
        ),
        set=lambda host, channel, value: host.set_ai_sensitivity(channel, value, ai_type="cry"),
    ),
    "auto_tracking": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["auto_tracking"],
            lambda host, channel: host.auto_track_enabled(channel),
        ),
        set=lambda host, channel, value: host.set_auto_tracking(channel, enable=value),
    ),
    "guard_return_time": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["guard_return_time"],
            lambda host, channel: host.ptz_guard_time(channel),
        ),
        set=lambda host, channel, value: host.set_ptz_guard(channel, time=value),
    ),
    "privacy_mode": SettingAlias(
        get=_capability_checked_getter(CAPABILITY_BY_ALIAS["privacy_mode"], _privacy_mode_getter),
        set=lambda host, channel, value: host.baichuan.set_privacy_mode(channel, enable=value),
    ),
    "siren_on_event": SettingAlias(
        get=_capability_checked_getter(
            CAPABILITY_BY_ALIAS["siren_on_event"],
            lambda host, channel: host.audio_alarm_enabled(channel),
        ),
        set=lambda host, channel, value: host.set_audio_alarm(channel, value),
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
    """Read the current value of `key` from an already-refreshed `host`.

    Catches broadly, not just ReolinkError: some reolink-aio getters raise a
    raw KeyError/AttributeError instead of a ReolinkError when a camera's
    firmware omits a field their response-parsing code assumes is always
    present (observed for push_enabled() on at least one real camera). Since
    that failure means the same thing to a caller as an unsupported setting,
    it's wrapped the same way rather than crashing the whole bootstrap/deploy.
    """
    alias = _resolve_alias(host, key)
    try:
        return alias.get(host, channel)
    except UnsupportedSettingError:
        raise
    except Exception as exc:
        raise UnsupportedSettingError(
            f"Could not read setting '{key}' from the camera: {type(exc).__name__}: {exc}"
        ) from exc


async def apply_setting(host: Host, channel: int, key: str, value: Any) -> None:
    """Apply `value` for `key` on `host`, raising UnsupportedSettingError on failure.

    Reolink-aio's setters usually validate model support and value shape
    internally and raise a descriptive ReolinkError when a setting is
    unsupported or invalid, but not always -- some raise a raw KeyError or
    similar for firmware-specific response shapes their parsing code doesn't
    expect (see read_setting). Either way, the failure is wrapped as an
    UnsupportedSettingError so IaC deployments fail with a clear explanation
    instead of a raw traceback or a silent no-op.
    """
    # Pulumi's dynamic-provider RPC layer serializes all numeric property
    # values as protobuf doubles, so an int input like `90` in cameras.yaml
    # arrives here as the float `90.0`. Several reolink-aio setters
    # validate `isinstance(value, int)` strictly and reject a float even
    # when it's numerically whole (observed on a real camera: set_volume
    # raising "volume 90.0 not integer"). Normalize a whole-number float
    # back to int before handing it to the setter.
    if isinstance(value, float) and value.is_integer():
        value = int(value)

    alias = _resolve_alias(host, key)
    try:
        await alias.set(host, channel, value)
    except Exception as exc:
        raise UnsupportedSettingError(
            f"Could not apply setting '{key}': {type(exc).__name__}: {exc}"
        ) from exc


# The provider connects to a single camera per resource; multi-channel NVRs
# are out of scope for the initial implementation, so we always target the
# NVR's own channel 0 (which is the camera itself for standalone devices).
CHANNEL = 0


async def _connect(host: str, port: int | None, username: str, password: str) -> Host:
    client = Host(host, username, password, port=port)
    await client.login()
    # Discovers the camera's channels and capabilities. Without this,
    # get_states() has no channels to iterate and every setting getter
    # silently falls back to its default (False/0) instead of the real
    # value, and every setter rejects the channel as unrecognized.
    await client.get_host_data()
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
