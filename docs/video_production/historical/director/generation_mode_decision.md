# Generation Mode Decision (Phase 9)

- **Gate:** `VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED`
- **Owner:** `intelligence/windagent_intelligence/video/shot_planner/generation_mode.py`
- **Ratified by:** [`03_phase_08_11_director_layer.md`](../plans/03_phase_08_11_director_layer.md) §14.3

## 1. Decision matrix

The Director records a **preferred mode** plus **acceptable fallbacks** with a
machine-readable `reason_code`. The mode must be inside the runtime
provider's capability set — the Director never calls the provider.

| Condition | Preferred mode | reason_code |
|---|---|---|
| `TRANSITION` shot (transforms two endpoint clips) | `VIDEO_TO_VIDEO` | `CLIP_TRANSFORMATION` |
| Mandatory character identity reference bound | `IMAGE_TO_VIDEO` | `IDENTITY_REFERENCE_REQUIRED` |
| Defined start/end frames needed (TRANSITION dep / FRAMES) | `FRAMES_TO_VIDEO` | `FRAMES_REQUIRED` |
| Blocking motion/scene continuation (tail frame) | `VIDEO_EXTENSION` | `MOTION_CONTINUATION` |
| Mandatory location reference on coverage shot | `IMAGE_TO_VIDEO` | `LOCATION_REFERENCE_REQUIRED` |
| Independent shot, no mandatory reference | `TEXT_TO_VIDEO` | `NO_MANDATORY_REFERENCE` |

Priority is first-match-wins; identity fidelity outranks motion continuation.

## 2. Fallback policy

- Identity/location reference shots fall back to `INGREDIENTS_TO_VIDEO`.
- Transition/continuation shots fall back to `FRAMES_TO_VIDEO` /
  `IMAGE_TO_VIDEO`.
- `TEXT_TO_VIDEO` has no fallback (nothing to bind).

The retry policy on each `ShotSpecification` mirrors the acceptable fallback
list and scopes retries to the `sequence` boundary.

## 3. Determinism

The same shot + same incoming dependency edges + same scene asset sets always
produce the same `GenerationModeDecision`. Mode decisions are recorded on the
shot spec and the graph hash covers them, so changing a reference, dependency,
or parameter yields a new graph hash (plan §24.5 semantics).
