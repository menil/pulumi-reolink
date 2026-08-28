from unittest.mock import AsyncMock, MagicMock

import pytest
from reolink_aio.exceptions import NotSupportedError

from pulumi_reolink.provider import UnsupportedSettingError, apply_setting, read_setting

GETTER_CASES = {
    "status_led": "status_led_enabled",
    "ir_lights": "ir_enabled",
    "push_notifications": "push_enabled",
    "recording": "recording_enabled",
    "motion_sensitivity": "md_sensitivity",
    "ptz_guard_enabled": "ptz_guard_enabled",
}


@pytest.mark.parametrize(("alias", "getter_attr"), GETTER_CASES.items())
def test_read_setting_known_alias_calls_getter(alias: str, getter_attr: str) -> None:
    host = MagicMock()
    getattr(host, getter_attr).return_value = "sentinel"

    assert read_setting(host, 3, alias) == "sentinel"

    getattr(host, getter_attr).assert_called_once_with(3)


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


def test_read_setting_wraps_non_reolink_error() -> None:
    host = MagicMock()
    host.status_led_enabled.side_effect = KeyError("scheduleEnable")

    with pytest.raises(UnsupportedSettingError, match="KeyError"):
        read_setting(host, 0, "status_led")
