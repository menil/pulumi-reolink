from pathlib import Path
from typing import Any

import pulumi
import yaml

from pulumi_reolink import ReolinkDevice, import_opts

CAMERAS_FILE = Path(__file__).parent / "cameras.yaml"
REQUIRED_CAMERA_KEYS = ("name", "host", "username", "password_key")


def _load_cameras() -> list[dict[str, Any]]:
    if not CAMERAS_FILE.exists():
        raise FileNotFoundError(
            f"{CAMERAS_FILE} not found. Run 'python -m pulumi_reolink.bootstrap' "
            "from this directory to add a camera first."
        )
    data = yaml.safe_load(CAMERAS_FILE.read_text()) or {}
    cameras: list[dict[str, Any]] = data.get("cameras") or []
    for camera in cameras:
        missing = [key for key in REQUIRED_CAMERA_KEYS if key not in camera]
        if missing:
            raise ValueError(
                f"Camera entry {camera!r} in {CAMERAS_FILE} is missing required "
                f"key(s): {', '.join(missing)}"
            )
    return cameras


def main() -> None:
    config = pulumi.Config()
    for camera in _load_cameras():
        ReolinkDevice(
            camera["name"],
            host=camera["host"],
            username=camera["username"],
            password=config.require_secret(camera["password_key"]),
            settings=camera.get("settings") or {},
            port=camera.get("port"),
            opts=import_opts(camera),
        )


main()
