import asyncio
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from pulumi_reolink.bootstrap import (
    _prompt_password,
    append_camera,
    main,
    prompt_camera_name,
    prompt_connection_details,
    run_bootstrap,
    slugify_password_key,
)

HOST_ANSWERS = ["192.168.1.50", "admin"]
PASSWORD_ANSWERS = ["hunter2"]


def _fake_input(answers: list[str]) -> Callable[[str], str]:
    it: Iterator[str] = iter(answers)

    def input_fn(_prompt: str) -> str:
        return next(it)

    return input_fn


def test_prompt_connection_details_uses_injected_input_fns() -> None:
    details = prompt_connection_details(_fake_input(HOST_ANSWERS), _fake_input(PASSWORD_ANSWERS))

    assert details == {
        "host": "192.168.1.50",
        "username": "admin",
        "password": "hunter2",
    }


@patch("pulumi_reolink.bootstrap.pwinput")
def test_prompt_password_uses_pwinput_when_available(mock_pwinput: MagicMock) -> None:
    mock_pwinput.pwinput.return_value = "hunter2"

    assert _prompt_password("Password: ") == "hunter2"
    mock_pwinput.pwinput.assert_called_once_with("Password: ")


@patch("pulumi_reolink.bootstrap.getpass")
@patch("pulumi_reolink.bootstrap.pwinput")
def test_prompt_password_falls_back_to_getpass_when_pwinput_fails(
    mock_pwinput: MagicMock, mock_getpass: MagicMock
) -> None:
    """Regression test: pwinput raises a raw termios error on plain piped
    stdin (shell redirection) rather than falling back on its own -- see
    _prompt_password's docstring. That must degrade to getpass, not crash."""
    mock_pwinput.pwinput.side_effect = OSError("Inappropriate ioctl for device")
    mock_getpass.getpass.return_value = "hunter2"

    assert _prompt_password("Password: ") == "hunter2"
    mock_getpass.getpass.assert_called_once_with("Password: ")


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


def _run(
    mock_host_cls: MagicMock,
    host: MagicMock,
    cameras_file: Path,
    name_answer: str = "",
) -> dict[str, object]:
    mock_host_cls.return_value = host
    return run_bootstrap(
        _fake_input([*HOST_ANSWERS, name_answer]),
        cameras_file,
        _fake_input(PASSWORD_ANSWERS),
    )


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_uses_fetched_camera_name_by_default(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _fake_host(camera_name="Front Doorbell")
    cameras_file = tmp_path / "cameras.yaml"

    entry = _run(mock_host_cls, host, cameras_file)

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
def test_run_bootstrap_prints_progress(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _fake_host(camera_name="Front Doorbell")
    cameras_file = tmp_path / "cameras.yaml"

    _run(mock_host_cls, host, cameras_file)

    printed = capsys.readouterr().out
    assert "Connecting to 192.168.1.50..." in printed
    assert "Connected. Camera reports its name as 'Front Doorbell'." in printed
    assert "Saving configuration to" in printed
    assert "Saved. 'Front Doorbell' added to" in printed


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_honors_typed_name_override(mock_host_cls: MagicMock, tmp_path: Path) -> None:
    host = _fake_host(camera_name="Front Doorbell")

    entry = _run(mock_host_cls, host, tmp_path / "cameras.yaml", name_answer="Back Door")

    assert entry["name"] == "Back Door"
    assert entry["password_key"] == "back-door-password"


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_skips_unsupported_settings(mock_host_cls: MagicMock, tmp_path: Path) -> None:
    from reolink_aio.exceptions import NotSupportedError

    host = _fake_host()
    host.status_led_enabled.side_effect = NotSupportedError("not on this model")
    host.ir_enabled.return_value = True

    entry = _run(mock_host_cls, host, tmp_path / "cameras.yaml")

    assert "status_led" not in entry["settings"]
    assert entry["settings"]["ir_lights"] is True


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_reports_skipped_settings_count(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from reolink_aio.exceptions import NotSupportedError

    host = _fake_host()
    host.status_led_enabled.side_effect = NotSupportedError("not on this model")

    _run(mock_host_cls, host, tmp_path / "cameras.yaml")

    printed = capsys.readouterr().out
    assert "1 not supported by this camera and skipped" in printed


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_skips_settings_that_raise_non_reolink_errors(
    mock_host_cls: MagicMock, tmp_path: Path
) -> None:
    """Regression test for a real camera whose push_enabled() raised a raw
    KeyError('scheduleEnable') instead of a ReolinkError -- bootstrap must
    skip that setting like any other unsupported one, not crash entirely."""
    host = _fake_host()
    host.push_enabled.side_effect = KeyError("scheduleEnable")

    entry = _run(mock_host_cls, host, tmp_path / "cameras.yaml")

    assert "push_notifications" not in entry["settings"]
    assert entry["settings"]["status_led"] is True


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_shows_friendly_error_and_exits_on_connect_failure(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A wrong password (or any connection failure) must show a friendly
    message and exit, not raise a raw exception up to the caller."""
    from reolink_aio.exceptions import CredentialsInvalidError

    host = MagicMock()
    host.login = AsyncMock(side_effect=CredentialsInvalidError("invalid username/password"))
    host.logout = AsyncMock()
    mock_host_cls.return_value = host

    cameras_file = tmp_path / "cameras.yaml"
    with pytest.raises(SystemExit) as exc_info:
        run_bootstrap(_fake_input(HOST_ANSWERS), cameras_file, _fake_input(PASSWORD_ANSWERS))

    assert exc_info.value.code == 1
    printed = capsys.readouterr().out
    assert "Could not connect to 192.168.1.50" in printed
    assert "CredentialsInvalidError" in printed
    assert "Check the host/IP, username, and password" in printed
    assert not cameras_file.exists()


@patch("pulumi_reolink.bootstrap.CONNECT_TIMEOUT", 0.05)
@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_caps_total_connect_time_even_if_login_hangs(
    mock_host_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression test: reolink-aio's Host(timeout=...) only bounds each
    individual HTTP request, not the whole multi-protocol login() probe
    (HTTPS:443, then HTTP:80, then a separate Baichuan handshake) -- an
    unreachable host measured ~33s in practice against a 10s per-request
    timeout. The outer asyncio.wait_for is what actually caps the total
    wait, regardless of how long login() itself takes."""

    async def hang_forever() -> None:
        await asyncio.sleep(60)

    host = MagicMock()
    host.login = AsyncMock(side_effect=hang_forever)
    host.logout = AsyncMock()
    mock_host_cls.return_value = host

    with pytest.raises(SystemExit) as exc_info:
        run_bootstrap(
            _fake_input(HOST_ANSWERS), tmp_path / "cameras.yaml", _fake_input(PASSWORD_ANSWERS)
        )

    assert exc_info.value.code == 1
    assert "TimeoutError" in capsys.readouterr().out


@patch("pulumi_reolink.bootstrap.Host")
def test_run_bootstrap_logs_out_when_post_login_step_fails(
    mock_host_cls: MagicMock, tmp_path: Path
) -> None:
    """A failure after a successful login (e.g. get_host_data) must not leak
    the session -- repeated failed attempts could otherwise hit the camera's
    max-session limit."""
    host = MagicMock()
    host.login = AsyncMock()
    host.logout = AsyncMock()
    host.get_host_data = AsyncMock(side_effect=RuntimeError("boom"))
    mock_host_cls.return_value = host

    with pytest.raises(SystemExit):
        run_bootstrap(
            _fake_input(HOST_ANSWERS), tmp_path / "cameras.yaml", _fake_input(PASSWORD_ANSWERS)
        )

    host.logout.assert_awaited_once()


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
