# AI Decision Record: Camera Feature Expansion (Spotlight, AI Delays, ISP, Auto-Tracking)

## Context & Goal
`pulumi-reolink` previously supported 28 camera settings. However, modern Reolink cameras (including outdoor PTZ cameras with spotlights, smart doorbells, and indoor PTZ devices) offer deeper capabilities through `reolink-aio`:
- AI stay/delay confirmation times to filter transient false alerts.
- Spotlight operating modes and brightness levels.
- Low-light switching threshold (`dayNightThreshold`) and backlight compensation (`backLight`).
- Post-motion recording buffers.
- PTZ auto-tracking disappearance and stop timeout limits.

The goal is to expose these settings cleanly in IaC through `SETTING_ALIASES`, with robust capability gating and sentinel value detection, and verify them against live physical hardware without regressions.

## Architecture & Key Decisions
1. **Model-Specific Capability Gating (`_capability_checked_getter`)**:
   - Camera capabilities vary dramatically between models (e.g. Doorbells have package AI and HDR, outdoor cameras have spotlights and vehicle AI, indoor cameras have privacy mode).
   - Each setting maps to its underlying `reolink-aio` capability key in `CAPABILITY_BY_ALIAS`. Settings are checked via `host.supported(channel, capability)` before executing getters to prevent unhandled errors and avoid polluting `cameras.yaml` during bootstrap.

2. **Dedicated AI Delay Helper (`_ai_delay_getter`)**:
   - `ai_delay` returns `0` when unreported or when the stay time is genuinely 0 seconds.
   - We verify both the specific detection type capability (`ai_people`, `ai_vehicle`, `ai_dog_cat`) and `_ai_alarm_settings` presence before returning `host.ai_delay()`, allowing legitimate 0-second delays while catching unsupported types.

3. **Sentinel Guarding for ISP & Tracking Getters**:
   - Reolink firmware returns sentinel values when certain features are uninitialized or not present:
     - `daynight_threshold`: returns `None`.
     - `backlight_mode`: returns `None`.
     - `post_recording_time`: returns `""`.
     - `whiteled_mode` / `whiteled_brightness`: returns `None`.
     - `auto_track_disappear_time` / `auto_track_stop_time`: returns `-1`.
   - Wrapping these with `_sentinel_guarded_getter` ensures uninitialized or unsupported values raise `UnsupportedSettingError` cleanly rather than producing invalid YAML or corrupting drift detection.

4. **Live Verification Against Real Hardware**:
   - Verified across three physical devices:
     - Patio (Outdoor PTZ with spotlights): successfully discovered custom `daynight_threshold: 78`, `spotlight_*`, and AI delays.
     - Living Room (Indoor PTZ): successfully discovered `auto_track_*` timeouts, `daynight_threshold: 50`, and animal/person delays.
     - Front Door (Video Doorbell): successfully discovered AI delays and image thresholds.
     - Capability isolation verified: spotlights and vehicle delays were correctly omitted from the indoor camera.

## Alternatives Considered & Rejected
- **Dynamic Reflection Only**: Relying solely on `_resolve_alias` reflection fallback was rejected because methods like `set_whiteled` and `set_auto_tracking` require specific keyword arguments (`state=`, `mode=`, `brightness=`, `disappear_time=`, `stop_time=`) that reflection cannot infer from names alone.
- **Combined Spotlight Dict**: Grouping spotlight state, mode, and brightness into a nested dictionary was rejected to keep setting management flat and consistent with the existing IaC schema (`status_led`, `ir_lights`, `speaker_volume`).
