# Shot Dependency Graph (Phase 9)

- **Gate:** `VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED`
- **Owner:** `core/windagent_core/domain/video_production/shot_graph.py` (models +
  validator) and `intelligence/windagent_intelligence/video/shot_planner/graph.py`
  (builder)
- **Ratified by:** `../../intelligence/windagent_intelligence/video/director/` (plan 03 đã retired) §13

## 1. Edge semantics

Each `ShotDependency` edge records:

```text
dependency_id
predecessor_shot_id
successor_shot_id
dependency_type
required_artifact_type
reason
blocking
```

Dependency types (plan §13):

| Type | Semantics | Required artifact | Blocking |
|---|---|---|---|
| `TEMPORAL` | in-scene shot order | `NONE` | no (advisory order) |
| `DIALOGUE` | dialogue flow; successor reacts to delivered line | `FULL_CLIP` | yes |
| `CONTINUITY` | shared subject keeps identity/motion continuity | `TAIL_FRAME` | yes |
| `TRANSITION` | non-CUT transition needs both endpoints | `FULL_CLIP` | yes |
| `VISUAL_REFERENCE` | coverage composes from established geography | `REFERENCE_IMAGE` | no |
| `ASSET` | shared approved reference asset binding | `REFERENCE_IMAGE` | no |

## 2. Validation (fail closed)

`ShotDependencyGraphValidator` runs BEFORE publish and raises blocking issues
for (plan §13):

- duplicate node / edge IDs;
- predecessor / successor shot missing;
- self-edge;
- cycle in the **blocking** subgraph (fail closed — never publish);
- `TEMPORAL` edge crossing scenes (invalid scene/sequence boundary).

Topological order is deterministic (Kahn with stable `(scene, order)` keys) so
scheduling is reproducible. Camera/creative findings are returned as
non-blocking warnings and never block publish.

## 2.1 Known boundary — cross-scene edge semantics

`ShotDependencyGraphValidator` rejects a `TEMPORAL` edge that crosses
scenes (invalid scene/sequence boundary). The other edge types
(`CONTINUITY` / `TRANSITION` / `DIALOGUE` / `VISUAL_REFERENCE` / `ASSET`)
are allowed to cross scene boundaries and their *forward-in-time* semantics
are NOT enforced by the Phase 9 validator — that is a known, documented
boundary handed off to **Phase 10 (Continuity Ledger)**, which traces state
across shots/scenes and blocks invalid cross-scene transitions. Phase 9
only guarantees the blocking subgraph is acyclic and the structural rules
above, so a plan that publishes here is structurally valid even if a
cross-scene continuity edge still needs Phase 10 review.

## 3. Scheduling metadata (plan §14.4)

`ShotScheduling` records per shot:

- `parallel_capable` — no blocking predecessor (may run in parallel);
- `concurrency_hint` — parallel-capable count in the sequence, capped by the
  production constraint (orchestration keeps final authority);
- `sequence_retry_boundary` — the scene/sequence id;
- `waits_for_artifact_types` — artifacts the shot must wait for.

## 4. Hash & traceability

`compute_graph_hash` produces a deterministic SHA-256 over the canonical
graph payload + graph version + source plan/package hashes. Same input → same
hash; any change to shots, edges, versions, or sources → new hash.
