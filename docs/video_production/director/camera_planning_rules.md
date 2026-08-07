# Camera Planning Rules (Phase 9)

- **Gate:** `VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED`
- **Owner:** `intelligence/windagent_intelligence/video/shot_planner/camera.py`
- **Ratified by:** [`03_phase_08_11_director_layer.md`](../plans/03_phase_08_11_director_layer.md) §14.2

## 1. Decision rules

Camera decisions are deterministic and derived from the shot specification.
Every decision carries a `reason_code` — never just prose:

| Shot type | Camera | reason_code |
|---|---|---|
| `ESTABLISHING` | wide, high angle, static, neutral side | `ESTABLISH_GEOGRAPHY` |
| `MASTER` | full scene, eye level, `SIDE_A` | `SPATIAL_CONTINUITY` |
| `MEDIUM` | medium, eye level, `SIDE_A` | `DIALOGUE_ALIGNMENT` / `ACTION_FOLLOW` |
| `CLOSE_UP` | close, eye level, `SIDE_A` | `DIALOGUE_ALIGNMENT` / `EMOTIONAL_BEAT` |
| `EXTREME_CLOSE_UP` | macro ECU, `SIDE_A` | `EMOTIONAL_BEAT` |
| `OVER_SHOULDER` | OS of partner, `SIDE_A` | `DIALOGUE_ALIGNMENT` |
| `POV` | subject eye line, handheld, neutral | `POV_SUBJECTIVE` |
| `INSERT` | macro detail, neutral | `INSERT_DETAIL` |
| `REACTION` | OS of listener, `SIDE_A` | `REACTION_BEAT` |
| `TRANSITION` | neutral endpoint | `TRANSITION_ENDPOINT` |

## 2. Constraints (validated, non-blocking warnings)

- **Establish geography before coverage** — establishing shots anchor spatial
  continuity; coverage composes from them (`VISUAL_REFERENCE` edges).
- **180-degree rule** — coverage shots stay on ONE side of the scene action
  line; a flip without justification is a `CAMERA_SIDE_VIOLATION`.
- **Screen direction** — stays consistent within a scene; a flip is a
  `SCREEN_DIRECTION_FLIP`.
- **Movement fits duration** — declared camera movement on a shot shorter
  than `MIN_MOVEMENT_DURATION_SECONDS` (1.5s) is `MOVEMENT_TOO_SHORT`.
- **Reaction needs a source** — a `REACTION` shot that is the first shot of a
  scene has nothing to react to (`REACTION_MISSING_SOURCE`).

Camera warnings never block publish — they are returned on the receipt so a
workflow can review them, but a structurally valid graph always publishes.
