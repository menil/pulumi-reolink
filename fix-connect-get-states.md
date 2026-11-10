# AI Decision Record: Populate Device States in Provider Connect

## Context & Goal
During initial resource creation (`pulumi up`) against physical Reolink cameras (Patio, Living Room, Front Door), the operation failed with errors such as:
```
UnsupportedSettingError: Could not apply setting 'ai_person_sensitivity': NotSupportedError: set_ai_sensitivity: ai sensitivity on camera Patio is not available
```
and:
```
UnsupportedSettingError: Could not apply setting 'ai_animal_delay': NotSupportedError: set_ai_delay: ai delay on camera Living Room is not available
```
The goal is to ensure device state caches required by `reolink-aio` setters are initialized immediately upon connection, before any setting modifications are attempted.

## Architecture & Key Decisions
1. **Root Cause Identification**:
   - `reolink_aio.api.Host` setters for AI sensitivity (`set_ai_sensitivity`) and AI delay (`set_ai_delay`) guard execution with `if channel not in self._ai_alarm_settings: raise NotSupportedError(...)`.
   - `_connect()` in `provider.py` invoked `await client.login()` and `await client.get_host_data()`, but omitted `await client.get_states()`.
   - In `_ReolinkDeviceProvider.create()`, `_apply_settings()` executes before `_read_settings()`. Because `_ai_alarm_settings` was unpopulated, every AI setter call failed on supported hardware.

2. **Populate States in `_connect()` with Session Guard**:
   - Added `await client.get_states()` inside `_connect()` immediately following `get_host_data()`.
   - Wrapped initial discovery calls in `try ... except Exception: await client.logout(); raise` to ensure logged-in sessions are not leaked if post-login discovery fails.

3. **Post-Mutation State Refresh**:
   - In `create()` and `update()`, if settings were applied, `await client.get_states()` is invoked to refresh cached states from the physical device.
   - Simplified `_read_settings()` to a synchronous extraction helper using `read_setting()`.

4. **Hardware Verification**:
   - Verified live with `pulumi up` against Patio (`10.10.30.10`), Living Room (`10.10.30.12`), and Front Door (`10.10.30.14`). All 3 devices successfully initialized and applied desired configurations.

## Alternatives Considered & Rejected
- **Per-Setter Guard Bypasses / Workarounds**: Overriding internal checks in `reolink-aio` was rejected; `reolink-aio`'s design expects `get_states()` to have populated device configuration prior to invoking mutations.
- **Calling `get_states()` Only in Setters**: Triggering ad-hoc state queries per setter invocation would incur redundant network round-trips for every property applied. Calling `get_states()` once during connection and once after batch application is optimal.
