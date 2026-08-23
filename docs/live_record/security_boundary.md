# Security Boundary — Live Record — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN`

## 1. Two Roles, One Router

- `RECORDING_PREPARER` prepares `LiveExecutionPlan` + `artifact://` bundles.
- `LIVE_DIRECTOR` observes and selects prepared actions during recording.
- `NARRATION_TTS` generates audio post-recording.
- All resolved via existing Provider + Model Routing (credential rotation, model sync, capability detection). No separate key system.

Capability gate for `LIVE_DIRECTOR`: `live_api + video_input + text_output + function_calling` must all be true. UI requests `role=LIVE_DIRECTOR`; router selects e.g. `gemini-3.1-flash-live-preview`.

## 2. Constrained Action Gate (Critical)

Gemini NEVER gets:
```
write_file(path, content)
shell(command)
open_url(url)
click(x,y)
powershell(script)
```

Only:
```
execute_prepared_action(action_id)
```

Executor looks up `action_id` in frozen plan and executes exact `payload_ref` content. Content hash `before_hash/after_hash` verified.

## 3. Recording Engine Isolation

- Gemini disconnect → tool executor STOP, scene advancement STOP, but recorder STAYS ALIVE (Principle D).
- Every action has `execution_id + idempotency_key`; resume never replays SUCCESS actions.

## 4. Token Bootstrap

```
Desktop --Start--> WindAgent API --Resolve LIVE_DIRECTOR--> issue ephemeral token --Desktop--> Google Live API
```

- `POST /api/v3/live-record/sessions/bootstrap` → `{session_id, provider_id, model_id, token, expires_at, execution_plan_hash}`
- Token: not persisted, not logged, not returned via GET, one-session use, constrained to exact model/config.

## 5. Timeline Invariant

Every `timeline.jsonl` event is monotonic `t`. Future TTS aligns strictly on timeline:
```
{"t":12.410,"type":"SCENE_START","scene":"scene-03"}
{"t":34.554,"type":"ACTION_SUCCESS","action":"code-017"}
```

## 6. E2E Acceptance Must Prove

- 0 unapproved actions
- All source hashes correct
- All commands/browser actions came from plan
- All MKV segments valid and independently playable
- Timeline complete, lineage Episode→Plan→Take correct
