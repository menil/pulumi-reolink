from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from pulumi_reolink.bootstrap import append_camera, main, prompt_camera_details, run_bootstrap

PROMPT_ANSWERS = {
    "Camera Name: ": "front-doorbell",
    "Host/IP: ": "192.168.1.50",
    "Username: ": "admin",
    "Password: ": "hunter2",
    "Secret Config Key: ": "front-doorbell-password",
}


def _fake_input(answers: dict[str, str]) -> Any:
    def input_fn(prompt: str) -> str:
        return answers[prompt]

    return input_fn


def test_prompt_camera_details_uses_injected_input_fn() -> None:
    details = prompt_camera_details(_fake_input(PROMPT_ANSWERS))

    assert details == {
        "name": "front-doorbell",
        "host": "192.168.1.50",
        "username": "admin",
        "password": "hunter2",
        "password_key": "front-doorbell-password",
    }


def test_append_camera_creates_file_when_missing(tmp_path: Path) -> None:
    cameras_file = tmp_path / "cameras.yaml"

    append_camera(cameras_file, {"name": "cam-1", "host": "10.0.0.1"})

    assert yaml.safe_load(cameras_file.read_text()) == {
        "cameras": [{"name": "cam-1", "host": "10.0.0.1"}]
    }


def test_append_camera_preserves_existing_entries(tmp_path: Path) -> None:
    cameras_file = tmp_path / "cameras.yaml"
    cameras_file.write_text(yaml.safe_dump({"cameras": [{"name": "cam-1"}]}))

    append_camera(cameras_file, {"name": "cam-2"})

    assert yaml.safe_load(cameras_file.read_text()) == {
        "cameras": [{"name": "cam-1"}, {"name": "cam-2"}]
    }


def test_append_camera_raises_clear_error_on_invalid_yaml(tmp_path: Path) -> None:
    cameras_file = tmp_path / "cameras.yaml"
    cameras_file.write_text("cameras: [unterminated")

    with pytest.raises(ValueError, match="invalid YAML"):
        append_camera(cameras_file, {"name": "cam-1"})


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_queries_settings_and_writes_camera(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = MagicMock()
    host.login = AsyncMock()
    host.logout = AsyncMock()
    host.get_states = AsyncMock()
    host.status_led_enabled.return_value = True
    host.ir_enabled.return_value = False
    host.push_enabled.return_value = True
    host.recording_enabled.return_value = True
    host.md_sensitivity.return_value = 30
    host.ptz_guard_enabled.return_value = False
    mock_host_cls.return_value = host

    cameras_file = tmp_path / "cameras.yaml"

    entry = run_bootstrap(_fake_input(PROMPT_ANSWERS), cameras_file)

    host.login.assert_awaited_once()
    host.get_states.assert_awaited_once()
    host.logout.assert_awaited_once()

    assert entry["name"] == "front-doorbell"
    assert entry["password_key"] == "front-doorbell-password"
    assert "password" not in entry
    assert entry["settings"]["status_led"] is True
    assert entry["settings"]["ir_lights"] is False

    on_disk = yaml.safe_load(cameras_file.read_text())
    assert on_disk == {"cameras": [entry]}

    printed = capsys.readouterr().out
    assert 'pulumi config set --secret front-doorbell-password "<password>"' in printed
    assert "hunter2" not in printed


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_skips_unsupported_settings(mock_host_cls: MagicMock, tmp_path: Path) -> None:
    from reolink_aio.exceptions import NotSupportedError

    host = MagicMock()
    host.login = AsyncMock()
    host.logout = AsyncMock()
    host.get_states = AsyncMock()
    host.status_led_enabled.side_effect = NotSupportedError("not on this model")
    host.ir_enabled.return_value = True
    host.push_enabled.return_value = True
    host.recording_enabled.return_value = True
    host.md_sensitivity.return_value = 30
    host.ptz_guard_enabled.return_value = False
    mock_host_cls.return_value = host

    entry = run_bootstrap(_fake_input(PROMPT_ANSWERS), tmp_path / "cameras.yaml")

    assert "status_led" not in entry["settings"]
    assert entry["settings"]["ir_lights"] is True


@patch("pulumi_reolink.bootstrap.run_bootstrap")
def test_main_delegates_to_run_bootstrap(mock_run_bootstrap: MagicMock) -> None:
    main()

    mock_run_bootstrap.assert_called_once_with()
