# Continuity Rule Catalog (Phase 10)

- **Gate:** `VP10_CONTINUITY_LEDGER_VERIFIED`
- **Owner:** `ContinuityLedgerValidator` in
  `core/windagent_core/domain/video_production/continuity.py`
- **Ratified by:** [`03_phase_08_11_director_layer.md`](../plans/03_phase_08_11_director_layer.md) §18-§20

`ContinuityLedgerValidator` is the deterministic rule engine. Blocking defects
fail closed: a revision with a blocking continuity issue cannot be rendered
until the defect is resolved (screenplay revision) or an audited human
override is recorded.

## 1. Rules

| Code | Condition | Severity |
|---|---|---|
| `CHANGE_OUTSIDE_ALLOWED` | a planned change targets a field not in the shot's `allowed_changes` | **BLOCKING** |
| `PROP_UNEXPLAINED_CHANGE` | a `prop:*` change whose source is not `SCREENPLAY_FACT` (no on-screen action) | **BLOCKING** |
| `IDENTITY_HASH_MISMATCH` | `identity:*` / `reference:*` required value missing or incoming ≠ approved reference | **BLOCKING** |
| `CAMERA_SIDE_VIOLATION` | camera side flips `SIDE_A` ↔ `SIDE_B` inside a scene (180-degree rule) | **BLOCKING** |
| `PARALLEL_CONFLICT` | two parallel shots (no blocking edge) write conflicting values to the same canonical field | **BLOCKING** |
| `MISSING_REQUIRED_STATE` | a required identity/reference field has no value — never guessed (plan §19.1) | **WARNING** |

## 2. Escape hatch

Planned changes whose source is `HUMAN_OVERRIDE` are **exempt** from
`CHANGE_OUTSIDE_ALLOWED` and `PROP_UNEXPLAINED_CHANGE` — an approved override
is exactly the mechanism to change a field that would otherwise be a defect
(plan §19.3). Overrides never bypass `IDENTITY_HASH_MISMATCH` for missing
references, and they never rewrite retroactive evidence.

## 3. Parallel conflict semantics

Two shots are *parallel* when neither reaches the other through **blocking**
edges of the shot graph. If parallel shots both propose a change to the same
canonical field with **different** values, the validator emits
`PARALLEL_CONFLICT` unless a merge rule is provided. Consistent (identical)
redundant changes are not conflicts. The validator requires the
`ShotDependencyGraph` to compute real blocking reachability; without a graph
the parallel rule is skipped (the service always passes the graph).

## 4. Allowed-change derivation

`ContinuityLedgerService._allowed_changes` derives per-shot allowed fields:

- `camera_side` — always allowed (director decision; the 180-degree rule
  still blocks bad flips);
- `appearance:{char}:emotion` — director decisions for scene characters;
- `appearance:{char}:clothing` — only when the scene/shot/dialogue action
  contains wardrobe keywords (`change`, `wears`, `takes off`, `jacket`, …);
- `prop:*` possession/state — only when the action contains prop keywords
  (`takes`, `grabs`, `holds`, `gives`, `passes`, `drops`, …).

Callers may override the derived set explicitly via the `allowed_changes`
parameter, which replaces the derived set for that shot.
