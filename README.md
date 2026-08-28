# pulumi-reolink

A reusable Pulumi package and CLI utility to configure and back up Reolink camera settings locally, without depending on Home Assistant. It connects directly to your cameras/doorbells over HTTP using [`reolink-aio`](https://github.com/starkillerOG/reolink-aio) — the same library that powers Home Assistant's official Reolink integration.

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

You'll be prompted for the camera's name, host/IP, admin username, admin password, and a secret config key. The tool connects once to query the camera's current settings, appends an entry to `cameras.yaml` in the current directory, and prints the command to store the password securely:

```bash
pulumi config set --secret front-doorbell-password "YourSuperSecretPassword"
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

### Git Hook Checks
The project automatically configures local Git hooks:
- **`commit-msg`**: Validates that all commit titles adhere to the [Conventional Commits](https://www.conventionalcommits.org/) standard (e.g. `feat: add database support`).
- **`pre-commit`**: Automatically runs `just validate` before allowing a commit. If any check fails, the commit is aborted.

### AI Agent Ignore Files
`.agentignore` at the repo root is the canonical, gitignore-syntax list of paths AI coding agents shouldn't read (dependencies, build output, secrets, caches, etc.). Agent-specific ignore files are symlinks to it, so the pattern list never drifts:

- **Claude Code**: `.claudeignore` → `.agentignore`
- **Google Antigravity**: `.antigravityignore` → `.agentignore`
- **OpenCode**: has no native ignore-file support yet. The closest option is the community [`opencode-ignore`](https://github.com/lgladysz/opencode-ignore) plugin, which you install via `opencode.json` and which reads a `.ignore` file. If you adopt it, symlink `.ignore` to `.agentignore` the same way.

To update the pattern list, edit `.agentignore` — the symlinked files pick up the change automatically.
