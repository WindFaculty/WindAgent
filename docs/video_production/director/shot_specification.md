# Shot Specification (Phase 9)

- **Gate:** `VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED`
- **Owner:** WindAgent Director Layer (`intelligence/windagent_intelligence/video/shot_planner/`)
- **Ratified by:** [`03_phase_08_11_director_layer.md`](../plans/03_phase_08_11_director_layer.md) §14.1

## 1. Purpose

Every planned shot is described by a full `ShotSpecification` (core model
`core/windagent_core/domain/video_production/shot_graph.py`) so downstream
compilers (Phase 11) and reviewers can work from structured data — never from
prose. The LLM proposed the shot plan in Phase 8; Phase 9 derives the spec
deterministically and validates it before publish.

## 2. Fields

| Field | Meaning |
|---|---|
| `spec_id` | stable spec id, one-to-one with `shot_id` |
| `scene_id` / `sequence` / `ordinal` | scene, sequence and in-sequence ordinal |
| `narrative_purpose` | why this shot exists (from planner) |
| `shot_type` | canonical catalog (below) |
| `subjects` | character / location / prop ids in frame |
| `action` | the action the shot covers |
| `camera` | `CameraDecision` — position, angle, movement, lens intent, camera side, screen direction, `reason_code` |
| `composition` / `screen_direction` | framing + consistent screen direction |
| `duration_seconds` / `frame_rate` / `aspect_ratio` | duration + format intent |
| `dialogue_line_ids` / `narration_range` | audio binding |
| `required_inputs` / `expected_outputs` | inputs (dialogue, assets) and outputs (clip, tail frame) |
| `generation_mode` | `GenerationModeDecision` — preferred + fallbacks + reason |
| `retry_policy` | max attempts, acceptable fallback modes, retry boundary |

## 3. Shot type catalog

`ESTABLISHING, MASTER, MEDIUM, CLOSE_UP, EXTREME_CLOSE_UP, OVER_SHOULDER,
POV, INSERT, REACTION, TRANSITION`

Each shot type maps to a deterministic `CameraDecision` with a
machine-readable `reason_code` (see `camera_planning_rules.md`).

## 4. Determinism

The same shot + same package produce the same `ShotSpecification` (stable
IDs from `StableIdFactory`). Phase 9 never calls a model port: it is a pure
rules layer over the Phase 8 plan.
