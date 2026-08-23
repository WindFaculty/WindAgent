# State Machine — Live Record — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN` | Code: `frontend/app/src/features/live-record/domain/stateMachine.ts`

```
IDLE
 ↓
PREPARING
 ↓
PREFLIGHT
 ↓
READY
 ↓
RECORDING
 ├─ PAUSED
 ├─ DIRECTOR_DEGRADED
 └─ RECOVERING
 ↓
FINALIZING
 ↓
COMPLETED
```

Fail variants: `FAILED`, `BLOCKED`.

## Allowed Transitions

| From | To |
|---|---|
| IDLE | PREPARING |
| PREPARING | PREFLIGHT, FAILED, BLOCKED |
| PREFLIGHT | READY, BLOCKED, FAILED |
| READY | RECORDING, BLOCKED, FAILED |
| RECORDING | PAUSED, DIRECTOR_DEGRADED, RECOVERING, FINALIZING, FAILED |
| PAUSED | RECORDING, FINALIZING, FAILED |
| DIRECTOR_DEGRADED | RECOVERING, PAUSED, FINALIZING, FAILED |
| RECOVERING | RECORDING, DIRECTOR_DEGRADED, PAUSED, FAILED |
| FINALIZING | COMPLETED, FAILED |
| COMPLETED | IDLE |
| FAILED | IDLE, PREPARING |
| BLOCKED | PREPARING, IDLE |

Any unlisted transition throws `LIVE_RECORD_STATE_TRANSITION_REJECTED`.

## Preflight — 13 Guards to READY

All must pass:

1. `episodeRevisionOk`
2. `planFrozen`
3. `!planStale`
4. `workspaceHashOk`
5. `artifactsPresent`
6. `actionsUntampered`
7. `providerResolved`
8. `credentialValid`
9. `liveConnectivityOk`
10. `recorderHealthy`
11. `wgcAvailable`
12. `nvencAvailable`
13. `diskSufficient` + `outputWritable`

See `evaluatePreflight()` for blocker codes.

## Failure Policy

- **RECOVERABLE** → `RETRY_RESUME`
- **OPERATOR_REQUIRED** → `PAUSE` + `request_operator`
- **FATAL** → `STOP_FINALIZE` on current segment
