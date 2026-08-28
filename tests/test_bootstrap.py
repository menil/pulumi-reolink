import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from pulumi_reolink.bootstrap import (
    append_camera,
    main,
    prompt_camera_name,
    prompt_connection_details,
    run_bootstrap,
    slugify_password_key,
)

CONNECTION_ANSWERS = ["192.168.1.50", "admin", "hunter2"]


def _fake_input(answers: list[str]) -> Callable[[str], str]:
    it: Iterator[str] = iter(answers)

    def input_fn(_prompt: str) -> str:
        return next(it)

    return input_fn


def test_prompt_connection_details_uses_injected_input_fn() -> None:
    details = prompt_connection_details(_fake_input(CONNECTION_ANSWERS))

    assert details == {
        "host": "192.168.1.50",
        "username": "admin",
        "password": "hunter2",
    }


def test_prompt_camera_name_accepts_typed_override() -> None:
    name = prompt_camera_name("Front Doorbell", _fake_input(["Back Door"]))

    assert name == "Back Door"


def test_prompt_camera_name_falls_back_to_default_on_empty_input() -> None:
    name = prompt_camera_name("Front Doorbell", _fake_input([""]))

    assert name == "Front Doorbell"


def test_prompt_camera_name_shows_default_in_prompt_text() -> None:
    seen_prompts = []

    def input_fn(prompt: str) -> str:
        seen_prompts.append(prompt)
        return ""

    prompt_camera_name("Front Doorbell", input_fn)

    assert seen_prompts == ["Camera Name [Front Doorbell]: "]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Front Doorbell", "front-doorbell-password"),
        ("  Back Yard Cam  ", "back-yard-cam-password"),
        ("Cam #1 (2nd Floor)", "cam-1-2nd-floor-password"),
        ("!!!", "camera-password"),
    ],
)
def test_slugify_password_key(name: str, expected: str) -> None:
    assert slugify_password_key(name) == expected


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


def _fake_host(camera_name: str = "Front Doorbell") -> MagicMock:
    host = MagicMock()
    host.login = AsyncMock()
    host.logout = AsyncMock()
    host.get_host_data = AsyncMock()
    host.get_states = AsyncMock()
    host.camera_name.return_value = camera_name
    host.status_led_enabled.return_value = True
    host.ir_enabled.return_value = False
    host.push_enabled.return_value = True
    host.recording_enabled.return_value = True
    host.md_sensitivity.return_value = 30
    host.ptz_guard_enabled.return_value = False
    return host


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_uses_fetched_camera_name_by_default(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _fake_host(camera_name="Front Doorbell")
    mock_host_cls.return_value = host

    cameras_file = tmp_path / "cameras.yaml"
    # host, username, password, then an empty camera-name answer (accept fetched default)
    entry = run_bootstrap(_fake_input([*CONNECTION_ANSWERS, ""]), cameras_file)

    host.login.assert_awaited_once()
    host.get_host_data.assert_awaited_once()
    host.get_states.assert_awaited_once()
    host.camera_name.assert_called_once_with(0)
    host.logout.assert_awaited_once()

    assert entry["name"] == "Front Doorbell"
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
def test_run_bootstrap_honors_typed_name_override(mock_host_cls: MagicMock, tmp_path: Path) -> None:
    host = _fake_host(camera_name="Front Doorbell")
    mock_host_cls.return_value = host

    entry = run_bootstrap(
        _fake_input([*CONNECTION_ANSWERS, "Back Door"]), tmp_path / "cameras.yaml"
    )

    assert entry["name"] == "Back Door"
    assert entry["password_key"] == "back-door-password"


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_skips_unsupported_settings(mock_host_cls: MagicMock, tmp_path: Path) -> None:
    from reolink_aio.exceptions import NotSupportedError

    host = _fake_host()
    host.status_led_enabled.side_effect = NotSupportedError("not on this model")
    host.ir_enabled.return_value = True
    mock_host_cls.return_value = host

    entry = run_bootstrap(_fake_input([*CONNECTION_ANSWERS, ""]), tmp_path / "cameras.yaml")

    assert "status_led" not in entry["settings"]
    assert entry["settings"]["ir_lights"] is True


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_skips_settings_that_raise_non_reolink_errors(
    mock_host_cls: MagicMock, tmp_path: Path
) -> None:
    """Regression test for a real camera whose push_enabled() raised a raw
    KeyError('scheduleEnable') instead of a ReolinkError -- bootstrap must
    skip that setting like any other unsupported one, not crash entirely."""
    host = _fake_host()
    host.push_enabled.side_effect = KeyError("scheduleEnable")
    mock_host_cls.return_value = host

    entry = run_bootstrap(_fake_input([*CONNECTION_ANSWERS, ""]), tmp_path / "cameras.yaml")

    assert "push_notifications" not in entry["settings"]
    assert entry["settings"]["status_led"] is True


@patch("pulumi_reolink.bootstrap.run_bootstrap")
def test_main_delegates_to_run_bootstrap(mock_run_bootstrap: MagicMock) -> None:
    main()

    mock_run_bootstrap.assert_called_once_with()


def test_running_as_module_invokes_main_without_warning() -> None:
    """Regression test for `python -m pulumi_reolink.bootstrap`.

    It previously did nothing at all (no `if __name__ == "__main__"` guard)
    and, once one was added the naive way, triggered runpy's sys.modules
    collision RuntimeWarning (because pulumi_reolink/__init__.py used to
    re-export bootstrap.main under the same name as the submodule). Feeding
    empty stdin makes the first prompt raise EOFError immediately, proving
    main() actually ran rather than silently exiting.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pulumi_reolink.bootstrap"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "RuntimeWarning" not in result.stderr
    # EOFError in stderr is the signal that main() actually ran and reached
    # the first input() prompt, rather than silently exiting like it used to.
    assert "EOFError" in result.stderr
