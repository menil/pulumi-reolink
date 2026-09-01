# pulumi-reolink

[![CI](https://github.com/menil/pulumi-reolink/actions/workflows/ci.yml/badge.svg)](https://github.com/menil/pulumi-reolink/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pulumi-reolink)](https://pypi.org/project/pulumi-reolink/)
[![Python versions](https://img.shields.io/pypi/pyversions/pulumi-reolink)](https://pypi.org/project/pulumi-reolink/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Manage your Reolink camera and doorbell settings as Infrastructure as Code with Pulumi — declarative, versioned, and drift-corrected. It connects directly to your cameras/doorbells over HTTP using [`reolink-aio`](https://github.com/starkillerOG/reolink-aio) — the same library that powers Home Assistant's official Reolink integration.

See [`specs/spec.md`](specs/spec.md) for the full technical specification.

---

## Installation

```bash
pip install pulumi-reolink
```

---

## Getting Started

### 1. Bootstrap your existing cameras

From your Pulumi project directory, run the interactive bootstrap CLI against each camera you want to manage:

```bash
python -m pulumi_reolink.bootstrap
```

You'll be prompted for the camera's host/IP, admin username, and admin password. It connects once to query the camera's current settings and its own configured name, then prompts for **Camera Name** with that name pre-filled — press Enter to accept it, or type a different one. The secret config key isn't prompted for; it's derived automatically from the name (e.g. `front-doorbell-password`).

The tool appends an entry to `cameras.yaml` in the current directory and prints the command to store the password securely:

```bash
pulumi config set --secret front-doorbell-password "<password>"
```

The plaintext password is only held in memory long enough to connect and print that command — it is never written to `cameras.yaml` or to disk.

### 2. Load cameras in your Pulumi program

```python
import pulumi
import yaml
from pulumi_reolink import ReolinkDevice

config = pulumi.Config()
with open("cameras.yaml") as f:
    cameras = yaml.safe_load(f)["cameras"]

for camera in cameras:
    ReolinkDevice(
        camera["name"],
        host=camera["host"],
        username=camera["username"],
        password=config.require_secret(camera["password_key"]),
        settings=camera.get("settings", {}),
    )
```

See [`example/`](example/) for a complete, runnable Pulumi project built this way.

### 3. Preview and deploy

```bash
pulumi preview
pulumi up
```

### 4. Detect and correct drift

If a setting was changed out-of-band (e.g. via the Reolink phone/desktop app), refresh Pulumi's state and re-apply your desired configuration:

```bash
pulumi refresh
pulumi up
```

---

## Limitations & Out-of-Scope Configurations

To prevent network lockouts and state desynchronization, the following must be managed out-of-band, not through this provider:

* **Initial network onboarding** — join factory-reset/new cameras to your network and set their initial admin credentials with the official Reolink app first.
* **Active network settings** — changing the Wi-Fi SSID, Wi-Fi password, or subnet configuration via Pulumi is not supported; it can drop the camera's connection mid-transaction.
* **Admin password rotation** — rotate admin passwords out-of-band; a failed in-band rotation risks locking the provider out of the device.
* **Firmware updates** — flashing firmware is a long-running, connectivity-disrupting operation and is not supported.
* **Battery-powered cameras** (e.g. the Argus series) — these sleep to conserve power and disable their local HTTP API. Only plugged-in (PoE or DC-powered) cameras and doorbells are supported.

---

## FAQ

**Does this require Home Assistant?**
No — it connects directly to your camera over its local HTTP API via `reolink-aio`, the same library Home Assistant's integration uses, but entirely standalone.

**Why not use Pulumi's generic REST API provider?**
Reolink's API is a single `POST /cgi-bin/api.cgi` RPC endpoint with stateful session-token authentication — a `Login` command returns a token that must be appended to every subsequent request, then a `Logout` command releases it — not RESTful resource paths. A generic REST provider has no way to model that session lifecycle, so this uses a custom Pulumi Dynamic Provider instead.

**Does this support NVRs or multiple cameras behind one host?**
Not yet. Each `ReolinkDevice` manages a single camera (channel 0); multi-channel NVR support is out of scope for now.

**Does this work with battery-powered cameras (e.g. the Argus series)?**
No — they sleep to conserve power and disable their local HTTP API while asleep, so there's nothing to connect to. Only plugged-in (PoE or DC-powered) cameras and doorbells are supported.

**Can I change Wi-Fi settings or rotate the admin password through this?**
No, deliberately. Both carry a real risk of locking the provider out of the device mid-deployment — manage them out-of-band via the Reolink app instead.

**What happens if I remove a camera from my Pulumi program?**
Nothing on the camera itself. `delete` is a no-op by design — removing a `ReolinkDevice` from your code stops Pulumi from managing it, but never mutates or resets the physical device.

The same applies at the individual setting level: removing a key from a `ReolinkDevice`'s `settings` dict (while keeping the resource itself) stops Pulumi from managing that one setting, but leaves its last-applied value in place on the camera rather than reverting it to any prior state.

**What happens if a setting is changed outside Pulumi (e.g. via the Reolink app)?**
Run `pulumi refresh` to detect the drift, then `pulumi up` to re-apply your declared configuration.

**Which settings can I manage?**
A stable set of built-in names, plus best-effort support for others via runtime reflection on the connected camera's API. An unknown or model-unsupported setting fails the deployment with a clear error rather than silently doing nothing. The built-in names:

- `status_led`
- `ir_lights`
- `push_notifications`
- `recording`
- `motion_sensitivity`
- `ptz_guard_enabled`
- `ftp_recording`
- `email_notifications`
- `hdr`
- `daynight_mode`
- `audio_recording`
- `privacy_mask`
- `buzzer`
- `speaker_volume`
- `ai_animal_sensitivity`
- `ai_person_sensitivity`
- `baby_cry_sensitivity`
- `auto_tracking`
- `guard_return_time`
- `privacy_mode`
- `siren_on_event`

**Is this affiliated with or endorsed by Reolink?**
No — this is an independent, community project built on Reolink's local HTTP API, not an official Reolink product.

---

## Development Environment

### Nix Shell
Activate the Nix developer shell to load project tools: Python, `uv`, `pulumi`, `just`, `git`, and `gh`. It also runs `uv sync` and activates the resulting `.venv`, so `pulumi_reolink`, `pulumi`, and `pyyaml` are immediately importable. [`example/`](example/) relies on this shell's environment rather than managing its own dependencies:
```bash
nix-shell
```

### Task Runner (`Justfile`)
- `just`: List all available tasks.
- `just format`: Format code with `ruff format`.
- `just lint`: Lint code with `ruff check`.
- `just typecheck`: Type-check `pulumi_reolink` with `mypy`.
- `just test`: Run the unit test suite with coverage enforcement (`pytest --cov-fail-under=90`).
- `just validate`: Run the full pipeline (format check, lint, type check, tests).
