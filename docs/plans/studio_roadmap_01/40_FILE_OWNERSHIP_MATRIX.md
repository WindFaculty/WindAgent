# File Ownership Matrix

## Rules

There are exactly three execution plans. Ownership is exclusive for material edits during parallel waves. Reading and adding consumer tests outside an owned production module are allowed only when the owning plan approves the path. A “shared/serialized” row has one named editor at a time and an explicit handoff order; it is never an invitation for concurrent edits.

New files follow the same ownership as their nearest listed directory. If a proposed file fits two rows, stop and resolve ownership at the integration gate before creating it.

| Path/pattern | Owner | Expected Roadmap 1 change | Other plans may | Other plans must not |
|---|---|---|---|---|
| `docs/plans/studio_roadmap_01/**` | Integration owner; contract sections co-approved A/B/C | Planning/contracts/gates only | Review and propose edits | Change frozen contract unilaterally |
| `core/windagent_core/domain/studio/**` | A | Series/Episode/revision lifecycle, approval, envelope refs | Import frozen public API; add consumer tests elsewhere | Add Story content rules or UI/API fields directly |
| `core/windagent_core/contracts/studio/**` | A | Ports, tasks/results, events, errors, capabilities, app commands | Consume and add contract fixtures | Fork/duplicate contracts |
| `core/windagent_core/domain/story/**` | B | Story artifact content, review/finding/diff/package models | A wraps in envelope; C generates/consumes schema | Add SQL/API/provider dependencies |
| `core/.../domain/video_production/project.py` and Studio compatibility exports | A | Narrow additive compatibility/migration | B/C add tests or request adapter | Concurrent material edit |
| `core/.../domain/video_production/screenplay.py` | B, after A2 contract freeze | Narrow compatibility adapters/re-exports | A/C add tests | Redefine aggregate/hash/lock authority |
| `core/.../domain/video_production/episode.py` and VP3D domain | A only for boundary/compat; otherwise protected | Avoid naming collision; regression-only unless approved | B/C read and test | Broad redesign or rename |
| `core/windagent_core/events/catalog.py` | A sole catalog editor | Add versioned Studio taxonomy | B proposes payloads in contract; C consumes | Direct edit during parallel work |
| Existing core command/query handlers that import storage | A | Boundary inversion/compat exports | B/C consumer tests | Concurrent refactor |
| `intelligence/windagent_intelligence/story/**` | B | Prompts, schemas/parsers, stages, validators, reviewers, handlers | A registers handlers via public seam; C fixtures | Add orchestration/storage/API composition |
| `intelligence/windagent_intelligence/video/**` | B for narrow story compatibility; VP3D areas protected | Incremental wrapper/extraction only | A/C regression tests | Bulk moves or director/IR rewrite |
| `orchestration/windagent_orchestration/studio/**` | A | Studio run/DAG, durable dispatch/reconcile | B supplies handlers; C calls app port | Add HTTP or Story prompt logic |
| `orchestration/.../orchestrator_service.py` | A hotspot | Narrow extension seam | B/C consumer tests | Direct edit |
| `orchestration/.../workflow_engine/**` | A boundary owner | Deprecation/guard only | B/C regression tests | Any Story dependency |
| `orchestration/.../production/**` | A boundary owner; otherwise protected | Guard/deprecation/capability boundary only | B/C regression tests | Story workflow or broad refactor |
| `storage/windagent_storage/studio/**` | A | Repositories/UoW/models/read models | B/C contract tests through ports/API | Direct imports or edits |
| `storage/.../video_production/**` | A | Additive compatibility persistence | B/C tests | Concurrent schema/repository edits |
| `storage/.../queue/**`, `services/task_finalizer.py`, outbox/UoW | A hotspot | Versioned Studio envelope/finalization/reconcile metadata | B handler contract tests; C E2E | Direct edits |
| `storage/.../migrations/**` | A sole migration owner | One ordered expand/backfill/validate migration | B/C supply data fixtures before freeze | Add migration or edit migration head/registry |
| `providers/**` | A for Studio adapter/composition seam | Real provider-neutral adapter/error/provenance mapping | B consumes `PreproductionModelPort`; C reads capability | Put prompts or UI behavior here |
| `execution/windagent_execution/registry.py` | A hotspot | Studio runtime adapter registration seam | B supplies public handlers | Direct concurrent registration edit |
| `apps/worker/windagent_worker/**` | A | Studio runtime/capability/fake guards | B integration tests through registry | Direct edit |
| `apps/api/windagent_api/routers/v3/studio/**` | C | Modular V3 routes/mapping/dependencies | A/B contract tests | Domain/orchestration implementation |
| `apps/api/windagent_api/main.py` | C, after A composition handoff | One V3 aggregator include | A reviews integration | Competing include/composition edit |
| `apps/api/windagent_api/composition.py` | Serialized: A first, C second | A exposes providers/services; C wires router dependencies only if unavoidable | Add tests, propose split modules | Concurrent edits or mixed domain/router logic |
| Existing V2 routers | C for deprecation metadata; otherwise protected | Additive headers/docs and regression tests | A/B provide compatibility adapters/tests | Delete, redirect, or semantic rewrite |
| `frontend/packages/studio-*/**` | C | Contracts/client/state/platform/UI | B supplies schemas/fixtures | Add domain source of truth |
| Existing `frontend/packages/production-*/**` | C | Narrow reuse adapters/test setup repairs | A/B supply fixtures | Parallel edits |
| `apps/desktop/src/**` | C | Studio routes/pages/composition; remove production fake/sample path | A/B inspect E2E results | Direct edit |
| frontend workspace manifests/root lockfiles | C sole lockfile owner | Add packages/dependencies deterministically | A/B request dependency through C | Regenerate/edit concurrently |
| Architecture/evidence checker scripts | A until A handoff; C invokes at final | A defines truth checks; C integrates commands | B add separate Story checker with approval | Overwrite ownership or loosen checks |
| `.github/workflows/ci.yaml` | C sole editor during final wave | Invoke frozen A/B/C commands and upload evidence | A/B provide commands/manifests | Direct edit during parallel waves |
| VP3D/Blender/production engine implementation | Protected; A boundary owner only | Regression/capability metadata, not redesign | All plans run tests | Roadmap 1 feature work |
| `road_map.md`, `road_map_v2_implementation_plan.md` | User-owned dirty state | No plan edit | Read only | Stage, restore, regenerate, or delete |

## Hotspot handoff order

| Hotspot | First editor | Handoff evidence | Second editor |
|---|---|---|---|
| API composition | A adds narrow Studio service providers and tests | `PLAN_A_HANDOFF_GATE` commit + dependency signatures | C injects providers into V3 dependencies; preferably new module, minimal central diff |
| Package exports | A publishes Studio kernel exports | A2 consumer fixture tag | B publishes Story exports through separate package; C consumes schemas |
| Existing screenplay compatibility | A freezes envelope/hash/lock authority without editing content behavior | `STUDIO_DOMAIN_INTEGRATION_GATE` | B adds content conversion/re-exports |
| Runtime registry/worker composition | A creates registration seam | `STORY_WORKER_GATE` fixture registry | B supplies handlers through seam; no direct composition edit |
| CI workflow | A/B publish stable commands/manifests | both handoff gates | C adds final jobs/uploads once |
| Root lockfiles | C throughout | one dependency batch per reviewed commit | No second owner |

## Conflict protocol

1. Stop editing the conflicting file; do not resolve by taking an entire side.
2. Identify the owner and the contract/gate that required the change.
3. Owner rebases onto the latest integration-gate commit and applies the smallest semantic diff.
4. Both affected plan owners rerun consumer contracts and the file’s focused tests.
5. Record the resolution in the merge manifest. A conflict that changes a frozen schema reopens `CONTRACT_FREEZE_GATE`.

## Ownership acceptance

The matrix passes bootstrap only when every new planned file maps to one owner, migrations/event catalog/lockfiles/CI each have one editor, and no branch plans to touch the user-owned roadmap changes.
