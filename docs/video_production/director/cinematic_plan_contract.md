# Cinematic Plan Contract (Phase 8)

- **Gate:** `VP8_DIRECTOR_FOUNDATION_VERIFIED`
- **Owner:** WindAgent Director Layer (`intelligence/windagent_intelligence/video/director/`)
- **Ratified by:** [`03_phase_08_11_director_layer.md`](../plans/03_phase_08_11_director_layer.md) §7–§10

## 1. Purpose

The Director turns a locked `VideoProductionPackage` into a provider-agnostic
`CinematicPlan` that can be validated and reviewed independently before any
rendering. The Director decides *how to tell and how to shoot*; it does NOT
submit Flow generations, does NOT mutate the locked screenplay, and does NOT
hold project/revision authority.

## 2. Port contract

`VideoDirectionPort` (`core/windagent_core/contracts/video_production/direction.py`):

```python
class VideoDirectionPort(Protocol):
    async def create_cinematic_plan(self, package: VideoProductionPackage) -> CinematicPlan: ...
    async def lock_shot_plan(self, plan: CinematicPlan) -> CinematicPlan: ...
```

`VideoDirectorService.create_cinematic_plan` implements this port exactly and
returns the immutable `CinematicPlan`. Workflows that also require planning
issues, revision proposals, and deterministic evidence use the explicit
`create_cinematic_plan_receipt` method, which returns `DirectorPlanReceipt`.

## 3. Inputs (minimum)

- package / revision ID and content hash;
- screenplay LOCKED (or explicit unlocked state via `require_locked=False`);
- entity/style bibles (characters, locations, props, style bible);
- approved reference metadata (assets with content hashes);
- target duration, aspect ratio, and release constraints
  (`creative_brief.target_duration_seconds`, `aspect_ratio`,
  `production_constraints`).

## 4. Outputs (minimum)

| Output | Representation |
|---|---|
| scene objective and beat order | `SceneObjective` records on the plan metadata (`scene_objectives`) |
| planned shots with stable IDs | `CinematicPlan.graph.shots` — deterministic `shot_id` from `StableIdFactory` |
| shot size, camera angle/movement, duration | `Shot.shot_type`, `Shot.camera_movement`, `Shot.duration_seconds`, `metadata.camera_angle` |
| dialogue/narration binding | `Shot.dialogue_line_ids` (every line bound to exactly one shot) |
| required character/location/prop references | `Shot.reference_asset_ids` (approved assets only) |
| generation mode intent | `Shot.generation_mode` |
| directorial issue / proposal | `DirectorialIssue` + `ScriptRevisionProposal` lists on the receipt |
| plan version/hash and source revision | `plan_hash`, `planner_version`, `prompt_version`, `prompt_hash`, `source_package_hash`, `revision_id` |

## 5. Structured planning

- The planner output is schema-validated `PlannerOutput` JSON — no free-text
  parsing (plan §9.4).
- Unknown entity/reference IDs **fail closed** (`ValidationFailureError`);
  a partial plan is never published.
- The planner cannot invent lead characters or locations outside the package;
  any new entity requires a `ScriptRevisionProposal`.
- Prompt/planner version is recorded on the plan.

## 6. Determinism

The same package + same deterministic model fake produce the same `plan_hash`
(plan §10 test requirement). The hash covers the canonical plan payload plus
planner/prompt/duration policy versions and the source package hash; changing
any of them yields a new hash.

## 7. Gate conditions

`VP8_DIRECTOR_FOUNDATION_VERIFIED` passes when:

1. the three package fixtures (short cartoon, two-character dialogue,
   multi-scene drama) each produce a valid plan;
2. a locked screenplay cannot be changed by planning (package hash unchanged);
3. every blocking directorial issue goes through a `ScriptRevisionProposal`.
