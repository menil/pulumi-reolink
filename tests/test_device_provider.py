from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pulumi
from pulumi.runtime import mocks

from pulumi_reolink.provider import ReolinkDevice, _ReolinkDeviceProvider, import_opts, resource_id

BASE_PROPS = {
    "host": "10.0.0.5",
    "port": None,
    "username": "admin",
    "password": "secret",
}


def _fake_host() -> MagicMock:
    host = MagicMock()
    host.login = AsyncMock()
    host.logout = AsyncMock()
    host.get_host_data = AsyncMock()
    host.get_states = AsyncMock()
    host.status_led_enabled.return_value = True
    host.set_status_led = AsyncMock()
    host.ir_enabled.return_value = True
    host.set_ir_lights = AsyncMock()
    return host


def test_resource_id_uses_host_and_port() -> None:
    assert resource_id("10.0.0.5", 443) == "10.0.0.5:443"


def test_resource_id_defaults_port_when_unset() -> None:
    assert resource_id("10.0.0.5", None) == "10.0.0.5:default"


def test_import_opts_builds_import_option_from_camera_marked_for_import() -> None:
    camera = {"host": "10.0.0.5", "port": 443, "import": True}

    opts = import_opts(camera)

    assert opts is not None
    assert opts.import_ == "10.0.0.5:443"


def test_import_opts_returns_none_when_import_flag_absent() -> None:
    assert import_opts({"host": "10.0.0.5"}) is None


def test_import_opts_returns_none_when_import_flag_false() -> None:
    assert import_opts({"host": "10.0.0.5", "import": False}) is None


@patch("pulumi_reolink.provider.Host")
def test_create_applies_settings_logs_in_and_out(mock_host_cls: MagicMock) -> None:
    host = _fake_host()
    mock_host_cls.return_value = host

    provider = _ReolinkDeviceProvider()
    result = provider.create({**BASE_PROPS, "settings": {"status_led": False}})

    host.login.assert_awaited_once()
    host.get_host_data.assert_awaited_once()
    host.set_status_led.assert_awaited_once_with(0, False)
    host.logout.assert_awaited_once()
    assert result.id == "10.0.0.5:default"
    assert result.outs is not None
    assert result.outs["settings"] == {"status_led": True}


@patch("pulumi_reolink.provider.Host")
def test_read_returns_current_settings(mock_host_cls: MagicMock) -> None:
    host = _fake_host()
    mock_host_cls.return_value = host

    provider = _ReolinkDeviceProvider()
    result = provider.read("10.0.0.5:default", {**BASE_PROPS, "settings": {"status_led": True}})

    host.get_states.assert_awaited_once()
    assert result.outs is not None
    assert result.outs["settings"] == {"status_led": True}


@patch("pulumi_reolink.provider.Host")
def test_update_only_applies_changed_settings(mock_host_cls: MagicMock) -> None:
    host = _fake_host()
    mock_host_cls.return_value = host

    provider = _ReolinkDeviceProvider()
    result = provider.update(
        "10.0.0.5:default",
        {**BASE_PROPS, "settings": {"status_led": True, "ir_lights": False}},
        {**BASE_PROPS, "settings": {"status_led": True, "ir_lights": True}},
    )

    host.set_ir_lights.assert_awaited_once_with(0, True)
    host.set_status_led.assert_not_awaited()
    assert result.outs is not None
    assert result.outs["settings"] == {"status_led": True, "ir_lights": True}


def test_delete_is_a_noop() -> None:
    provider = _ReolinkDeviceProvider()
    assert provider.delete("id", {}) is None


def test_diff_flags_host_change_as_replace() -> None:
    provider = _ReolinkDeviceProvider()
    result = provider.diff(
        "id",
        {**BASE_PROPS, "settings": {}},
        {**BASE_PROPS, "host": "10.0.0.6", "settings": {}},
    )
    assert result.changes is True
    assert result.replaces == ["host"]


def test_diff_flags_settings_change_without_replace() -> None:
    provider = _ReolinkDeviceProvider()
    result = provider.diff(
        "id",
        {**BASE_PROPS, "settings": {"status_led": True}},
        {**BASE_PROPS, "settings": {"status_led": False}},
    )
    assert result.changes is True
    assert result.replaces == []


def test_diff_reports_no_changes_for_identical_props() -> None:
    provider = _ReolinkDeviceProvider()
    props = {**BASE_PROPS, "settings": {"status_led": True}}
    result = provider.diff("id", props, dict(props))
    assert result.changes is False


class _RecordingMocks(mocks.Mocks):
    def __init__(self) -> None:
        self.seen_inputs: dict[str, Any] = {}

    def new_resource(self, args: mocks.MockResourceArgs) -> tuple[str, dict[str, Any]]:
        self.seen_inputs = args.inputs
        return f"{args.name}_id", args.inputs

    def call(self, args: mocks.MockCallArgs) -> tuple[dict[str, Any], None]:
        return {}, None


@pulumi.runtime.test
def test_reolink_device_registers_with_expected_inputs() -> pulumi.Output[Any]:
    my_mocks = _RecordingMocks()
    pulumi.runtime.set_mocks(my_mocks)
    device = ReolinkDevice("cam", host="10.0.0.5", username="admin", password="secret")

    def check(host: str) -> None:
        assert host == "10.0.0.5"
        assert my_mocks.seen_inputs["host"] == "10.0.0.5"
        assert my_mocks.seen_inputs["username"] == "admin"

    return device.host.apply(check)
