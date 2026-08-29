from unittest.mock import AsyncMock, MagicMock

import pytest
from reolink_aio.exceptions import NotSupportedError

from pulumi_reolink.provider import (
    CAPABILITY_BY_ALIAS,
    UnsupportedSettingError,
    apply_setting,
    read_setting,
)

GETTER_CASES = {
    "status_led": "status_led_enabled",
    "ir_lights": "ir_enabled",
    "push_notifications": "push_enabled",
    "recording": "recording_enabled",
    "motion_sensitivity": "md_sensitivity",
    "ptz_guard_enabled": "ptz_guard_enabled",
    "ftp_recording": "ftp_enabled",
    "email_notifications": "email_enabled",
    "hdr": "HDR_state",
    "daynight_mode": "daynight_state",
    "audio_recording": "audio_record",
    "privacy_mask": "privacy_mask_enabled",
    "buzzer": "buzzer_enabled",
    "speaker_volume": "volume",
}


@pytest.mark.parametrize(("alias", "getter_attr"), GETTER_CASES.items())
def test_read_setting_known_alias_calls_getter(alias: str, getter_attr: str) -> None:
    host = MagicMock()
    getattr(host, getter_attr).return_value = "sentinel"

    assert read_setting(host, 3, alias) == "sentinel"

    getattr(host, getter_attr).assert_called_once_with(3)


@pytest.mark.parametrize(("alias", "capability"), CAPABILITY_BY_ALIAS.items())
def test_read_setting_raises_unsupported_when_capability_not_reported(
    alias: str, capability: str
) -> None:
    """Found on real hardware: HDR_state() returned a plausible value (0)
    even though the camera model has no ISP HDR control at all, which
    set_HDR() then rejected on `pulumi up` regardless of value. Checking
    host.supported(channel, capability) up front -- the same check set_HDR()
    itself uses, and the pattern Home Assistant's reolink integration uses
    to decide whether to expose a control at all -- keeps an unsupported
    setting from being read (and so captured by bootstrap) in the first
    place."""
    host = MagicMock()
    host.supported.return_value = False

    with pytest.raises(UnsupportedSettingError):
        read_setting(host, 0, alias)

    host.supported.assert_called_once_with(0, capability)


def test_read_setting_returns_value_when_capability_reported_supported() -> None:
    host = MagicMock()
    host.supported.return_value = True
    host.status_led_enabled.return_value = True

    assert read_setting(host, 0, "status_led") is True


async def test_apply_setting_status_led_forwards_value_positionally() -> None:
    host = MagicMock()
    host.set_status_led = AsyncMock()

    await apply_setting(host, 1, "status_led", "Auto")

    host.set_status_led.assert_awaited_once_with(1, "Auto")


async def test_apply_setting_ir_lights_forwards_value_positionally() -> None:
    host = MagicMock()
    host.set_ir_lights = AsyncMock()

    await apply_setting(host, 1, "ir_lights", True)

    host.set_ir_lights.assert_awaited_once_with(1, True)


async def test_apply_setting_push_notifications_forwards_value_positionally() -> None:
    host = MagicMock()
    host.set_push = AsyncMock()

    await apply_setting(host, 1, "push_notifications", False)

    host.set_push.assert_awaited_once_with(1, False)


async def test_apply_setting_recording_forwards_value_positionally() -> None:
    host = MagicMock()
    host.set_recording = AsyncMock()

    await apply_setting(host, 1, "recording", True)

    host.set_recording.assert_awaited_once_with(1, True)


async def test_apply_setting_motion_sensitivity_forwards_value_positionally() -> None:
    host = MagicMock()
    host.set_md_sensitivity = AsyncMock()

    await apply_setting(host, 1, "motion_sensitivity", 25)

    host.set_md_sensitivity.assert_awaited_once_with(1, 25)


async def test_apply_setting_ptz_guard_uses_enable_keyword() -> None:
    host = MagicMock()
    host.set_ptz_guard = AsyncMock()

    await apply_setting(host, 1, "ptz_guard_enabled", True)

    host.set_ptz_guard.assert_awaited_once_with(1, enable=True)


@pytest.mark.parametrize(
    ("alias", "setter_attr", "value", "expected_kwargs"),
    [
        ("ftp_recording", "set_ftp", True, {}),
        ("email_notifications", "set_email", False, {}),
        ("hdr", "set_HDR", True, {}),
        ("daynight_mode", "set_daynight", "Auto", {}),
        ("audio_recording", "set_audio", True, {}),
        ("privacy_mask", "set_privacy_mask", True, {}),
        ("buzzer", "set_buzzer", False, {}),
        ("speaker_volume", "set_volume", 50, {"volume": 50}),
    ],
)
async def test_apply_setting_forwards_new_settings_correctly(
    alias: str, setter_attr: str, value: object, expected_kwargs: dict[str, object]
) -> None:
    host = MagicMock()
    setattr(host, setter_attr, AsyncMock())

    await apply_setting(host, 1, alias, value)

    if expected_kwargs:
        getattr(host, setter_attr).assert_awaited_once_with(1, **expected_kwargs)
    else:
        getattr(host, setter_attr).assert_awaited_once_with(1, value)


def test_read_setting_reflection_fallback_uses_bare_getter() -> None:
    host = MagicMock(spec=["set_custom_thing", "custom_thing"])
    host.custom_thing.return_value = 42

    assert read_setting(host, 0, "custom_thing") == 42

    host.custom_thing.assert_called_once_with(0)


async def test_apply_setting_reflection_fallback_uses_set_prefixed_method() -> None:
    host = MagicMock(spec=["set_custom_thing"])
    host.set_custom_thing = AsyncMock()

    await apply_setting(host, 0, "custom_thing", "value")

    host.set_custom_thing.assert_awaited_once_with(0, "value")


def test_read_setting_reflection_fallback_without_getter_raises() -> None:
    """A setter-only fallback (e.g. a write-only action like `siren`) must
    still work for apply_setting, but reading it must fail loudly instead of
    fabricating a None value."""
    host = MagicMock(spec=["set_custom_thing"])

    with pytest.raises(UnsupportedSettingError):
        read_setting(host, 0, "custom_thing")


def test_read_setting_unknown_key_raises_unsupported() -> None:
    host = MagicMock(spec=[])

    with pytest.raises(UnsupportedSettingError):
        read_setting(host, 0, "totally_unknown")


async def test_apply_setting_unknown_key_raises_unsupported() -> None:
    host = MagicMock(spec=[])

    with pytest.raises(UnsupportedSettingError):
        await apply_setting(host, 0, "totally_unknown", "value")


async def test_apply_setting_wraps_reolink_error() -> None:
    host = MagicMock()
    host.set_status_led = AsyncMock(side_effect=NotSupportedError("nope"))

    with pytest.raises(UnsupportedSettingError):
        await apply_setting(host, 0, "status_led", True)


def test_read_setting_wraps_reolink_error() -> None:
    host = MagicMock()
    host.status_led_enabled.side_effect = NotSupportedError("nope")

    with pytest.raises(UnsupportedSettingError):
        read_setting(host, 0, "status_led")


async def test_apply_setting_wraps_non_reolink_error() -> None:
    """Regression test: some reolink-aio setters/getters raise a raw KeyError
    or similar (not a ReolinkError) for firmware-specific response shapes
    their parsing code doesn't expect -- observed for push_enabled() on a
    real camera missing a 'scheduleEnable' field. That must still surface as
    a clear UnsupportedSettingError, not an unhandled traceback."""
    host = MagicMock()
    host.set_status_led = AsyncMock(side_effect=KeyError("scheduleEnable"))

    with pytest.raises(UnsupportedSettingError, match="KeyError"):
        await apply_setting(host, 0, "status_led", True)


def _value_passed_to_setter(await_args: object) -> object:
    """Extract the setting value from a mocked setter's recorded call,
    regardless of whether the setter takes it positionally (e.g.
    set_md_sensitivity(channel, value)) or as a keyword (e.g.
    set_volume(channel, volume=value))."""
    if await_args.kwargs:
        return next(iter(await_args.kwargs.values()))
    return await_args.args[-1]


@pytest.mark.parametrize(
    ("alias", "setter_attr"),
    [
        ("speaker_volume", "set_volume"),
        ("motion_sensitivity", "set_md_sensitivity"),
    ],
)
async def test_apply_setting_normalizes_whole_number_float_to_int(
    alias: str, setter_attr: str
) -> None:
    """Found on real hardware: Pulumi's dynamic-provider RPC layer
    serializes all numbers as protobuf doubles, so an int in cameras.yaml
    (e.g. speaker_volume: 90) arrives here as 90.0, which set_volume()
    rejects with "volume 90.0 not integer" since it strictly checks
    isinstance(value, int)."""
    host = MagicMock()
    setattr(host, setter_attr, AsyncMock())

    await apply_setting(host, 1, alias, 90.0)

    passed_value = _value_passed_to_setter(getattr(host, setter_attr).await_args)
    assert passed_value == 90
    assert isinstance(passed_value, int)


async def test_apply_setting_leaves_non_whole_float_unchanged() -> None:
    """None of our current settings are legitimately fractional, but the
    coercion must not corrupt a value that genuinely isn't a whole number."""
    host = MagicMock()
    host.set_volume = AsyncMock()

    await apply_setting(host, 1, "speaker_volume", 90.5)

    host.set_volume.assert_awaited_once_with(1, volume=90.5)


def test_read_setting_wraps_non_reolink_error() -> None:
    host = MagicMock()
    host.status_led_enabled.side_effect = KeyError("scheduleEnable")

    with pytest.raises(UnsupportedSettingError, match="KeyError"):
        read_setting(host, 0, "status_led")


@pytest.mark.parametrize(
    ("alias", "getter_attr", "sentinel", "real_value"),
    [
        ("motion_sensitivity", "md_sensitivity", 0, 25),
        ("hdr", "HDR_state", -1, 2),
        ("daynight_mode", "daynight_state", None, "Auto"),
    ],
)
def test_read_setting_treats_getter_sentinel_as_unsupported(
    alias: str, getter_attr: str, sentinel: object, real_value: object
) -> None:
    """Found on real hardware: HDR_state() returned -1, later rejected by
    set_HDR()'s validation on `pulumi up`."""
    host = MagicMock()
    getattr(host, getter_attr).return_value = sentinel

    with pytest.raises(UnsupportedSettingError):
        read_setting(host, 0, alias)

    # A real, in-range value must still pass through untouched.
    getattr(host, getter_attr).return_value = real_value
    assert read_setting(host, 0, alias) == real_value


def test_read_setting_does_not_double_wrap_unsupported_setting_error() -> None:
    host = MagicMock()
    host.HDR_state.return_value = -1

    with pytest.raises(UnsupportedSettingError) as exc_info:
        read_setting(host, 0, "hdr")

    assert "Could not read setting" not in str(exc_info.value)
