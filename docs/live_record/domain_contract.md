# Domain Contract — Live Record — Phase 0 Frozen

> Gate: `LIVE_RECORD_P0_ARCHITECTURE_FROZEN` | Code: `frontend/app/src/features/live-record/domain/types.ts`

## 1. Lineage

```
Episode
→ Recording Preparation
→ LiveExecutionPlan revision (hash + version + approval)
→ RecordingTake
```

`LiveExecutionPlan` is immutable after `FROZEN`. Any mutation invalidates `plan_hash`.

## 2. Core Entities

| Entity | Key Fields | Notes |
|---|---|---|
| `LiveExecutionPlan` | `id`, `episode_id`, `episode_revision_id`, `plan_hash`, `status`, `frozen_at`, `director_role`, `scenes[]`, `actions[]`, `source_workspace_hash` | `status ∈ {DRAFT,PREPARED,VALIDATED,FROZEN,STALE,INVALID}` |
| `RecordingScene` | `scene_id`, `title`, `narration_source`, `cues[]`, `action_ids[]` | Derived from Episode Workspace `Prepare Recording` |
| `RecordingCue` | `cue_id`, `action_ids[]`, `expected_state` | One Gemini decision ≈ one cue |
| `PreparedAction` | `action_id`, `type`, `payload_ref`, `before_hash/after_hash`, `idempotency_key` | Payload is `artifact://`, never inline code |
| `ExpectedVisualState` | `state_id`, `url_contains`, `file_should_contain_hash`, `test_should_pass` | Used by `verify_visual_state` |
| `DirectorSession` | `session_id`, `execution_plan_hash`, `provider_id`, `model_id` | Ephemeral token bound to exact model |
| `RecordingTake/Segment/Event` | `take_id`, `timeline.jsonl` | Every event timestamped for post TTS alignment |

## 3. Plan Status Lifecycle

```
DRAFT → PREPARED → VALIDATED → FROZEN (immutable)
Any stale → STALE | INVALID
```

## 4. Staleness Rule

```
if episode_revision != execution_plan.episode_revision → RECORDING_PLAN_STALE → BLOCKED (no Start)
```

## 5. Code Type Completeness

See `domain/types.ts` for canonical TypeScript definitions. The markdown is narrative; the `.ts` file is the executable contract.
