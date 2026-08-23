# Gemini Tool Contract — Constrained Manifest — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN` | Code: `frontend/app/src/features/live-record/contracts/directorTools.ts`

## Allowlist (exposed to Gemini Live)

- `advance_cue(cue_id)`
- `execute_prepared_action(action_id)` — **payload is `artifact://`, not inline code**
- `verify_visual_state(state_id)`
- `pause_recording()`
- `resume_recording()`
- `create_marker(marker_type)`
- `retry_action(action_id)` — only if `retry_allowed=true`
- `request_operator(reason)`

## Denylist (NEVER exposed)

`sell` / `write_file` / `open_url` / `click(x,y)` / `powershell` / `run_command_raw` / `browser_navigate_raw` etc.

Any tool outside allowlist throws `DIRECTOR_TOOL_DENIED`.

## Dispatch Invariants

1. Every call carries `idempotency_key` + `execution_id`; success actions are never replayed on resume.
2. `action_id` must exist in `LiveExecutionPlan.actions[]`; otherwise `ACTION_NOT_IN_PLAN`.
3. `state_id` must exist in `ExpectedVisualState`; otherwise `STATE_NOT_IN_PLAN`.
4. Deterministic executor validates `before_hash`/`after_hash` around `CODE_PLAYBACK` (verify → type/paste → save → verify).
5. Two playback modes: `TYPE` (15–40 chars/s) and `PASTE`.

## Session Context (per cycle)

```
system instruction + frozen plan summary + allowed tools + current scene
  ↓ each cycle
current cue + expected state + latest frame + last tool result + elapsed
  ↓
Observe → Compare → Select approved action → Execute → Observe
```
