# WindAgent Studio Roadmap 1 — Current Codebase Findings

## Audit frame

- Audit date: 2026-08-09 (Asia/Saigon).
- Required baseline: `9a09375700db02a64315068f008b15e43ba5f42d`.
- Observed `HEAD`: `9a09375700db02a64315068f008b15e43ba5f42d` — exact match.
- Observed branch: `chore/cleanup-stale-md-docs`.
- Preserved pre-existing worktree changes: modified `road_map.md`; deleted `road_map_v2_implementation_plan.md`.
- Roadmap source: the complete modified `road_map.md`, read end-to-end. This planning pass does not alter it.
- Scope: Roadmap 1, S0–S15, from Studio foundation through a locked short screenplay. Production rendering remains a protected downstream capability, not a Roadmap 1 deliverable.

Evidence labels used throughout this plan set:

- **OBSERVED** — directly verified in the current tree, graph, or a command run at the baseline.
- **INFERRED** — conclusion drawn from multiple observed facts; it must be rechecked when implementation reaches the affected seam.
- **PROPOSED** — target design or execution choice; it is not current behavior.
- **BLOCKED** — cannot be asserted or completed without a named decision or external prerequisite.

The assumption-status column below intentionally uses only the required values: `CONFIRMED`, `PARTIALLY_TRUE`, `OUTDATED`, `INCORRECT`, and `NEEDS_DECISION`.

## Assumption verification table

| ID | Roadmap/current-code assumption | Status | Evidence and implementation consequence |
|---|---|---|---|
| F-01 | The requested baseline is the current commit. | CONFIRMED | **OBSERVED:** `git rev-parse HEAD` returned the exact required SHA. Existing dirty files belong to the user and must remain untouched. |
| F-02 | `VideoProject` and `ProductionRevision` already provide a useful migration base. | CONFIRMED | **OBSERVED:** immutable Pydantic models and `RevisionService` exist in `core/.../domain/video_production/project.py`; SQL models, repositories, and UoW exist under `storage/.../video_production/`. Extend/migrate these seams; do not create parallel project/revision stores. |
| F-03 | A Studio `SeriesProject` aggregate exists. | INCORRECT | **OBSERVED:** no production definition exists. Plan A introduces it as the canonical Studio project while retaining a compatibility path for `VideoProject` IDs and rows. |
| F-04 | An `Episode` aggregate does not exist and can be added without collision. | PARTIALLY_TRUE | **OBSERVED:** `episode.py` contains VP3D render/runtime fixtures such as `EpisodeFixture`, not a creative Studio aggregate. Plan A adds a distinct Studio `Episode` and protects existing VP3D names. |
| F-05 | Approval primitives can be reused unchanged for Studio policy. | PARTIALLY_TRUE | **OBSERVED:** `ReviewResult`, `ApprovalDecision`, and `ApprovalState` exist, but `ApprovalPolicy` and Roadmap checkpoint modes do not. Reuse hash-bound decision semantics and add policy/checkpoint contracts. |
| F-06 | `OrchestratorService` is already the only orchestration authority. | INCORRECT | **OBSERVED:** it is the current multi-agent DAG authority, while `WorkflowEngine` remains composed and `ProductionWorkflowEngine` owns a separate file-backed production workflow. Plan A must establish authority boundaries and deprecation fences before story wiring. |
| F-07 | `OrchestratorService` already executes through the durable worker queue. | INCORRECT | **OBSERVED:** it dispatches directly through `ExecutionRuntimeRegistry`; `ProductionWorker` separately claims `SqlDurableTaskQueue`. Plan A must bridge canonical orchestration decisions to durable submission and worker completion. |
| F-08 | The durable execution foundation is real rather than a test stub. | CONFIRMED | **OBSERVED:** SQL submission, atomic claim, lease renewal, fencing, runtime dispatch, result persistence, CAS finalization, and an outbox path exist. Story task envelopes and orchestration reconciliation are missing. |
| F-09 | Current durable task payloads are sufficient for Studio workflow identity and artifact provenance. | INCORRECT | **OBSERVED:** `WorkSubmission` carries `prompt`, `workflow_name`, `tool_name`, and generic parameters; queue facts mirror that shape. Add a versioned Studio task envelope compatibly. |
| F-10 | Story-intelligence capabilities are wholly absent. | PARTIALLY_TRUE | **OBSERVED:** brief expansion, outlining, screenplay writing, narration, entity extraction, continuation, assembly, and director utilities exist under `intelligence/.../video`. Required bibles, canon, creative outline, review report, revision loop, and locked receipt are absent. |
| F-11 | The existing story chain is integrated into a production application path. | INCORRECT | **OBSERVED:** no production callers were found for the complete chain. It is reusable source material, not a live pipeline. |
| F-12 | Existing idea generation produces and scores 3–5 candidates. | INCORRECT | **OBSERVED:** the current outliner returns one `StoryConcept`; no canonical multi-candidate scoring/selection/lock pipeline exists. |
| F-13 | All existing model outputs are structured and schema-validated. | PARTIALLY_TRUE | **OBSERVED:** brief/outliner paths parse JSON; screenplay writing requests canonical text and uses tolerant parsing. Roadmap 1 needs versioned structured screenplay output with explicit validation and repair rules. |
| F-14 | Prompts are versioned and hashed. | CONFIRMED | **OBSERVED:** `PromptSpec` and provenance patterns exist. Prompts are inline across Python modules, so Plan B extracts a catalog incrementally while keeping compatibility exports. |
| F-15 | Story model invocation has a production adapter. | INCORRECT | **OBSERVED:** `PreproductionModelPort` has test fakes but no production implementation was found. The provider layer already has route locking and coordinated endpoint execution; Plan A supplies the infrastructure adapter. |
| F-16 | Provider selection can use a mock fallback in the final vertical slice. | INCORRECT | **OBSERVED:** legacy routing includes an emergency mock path and workers expose a fake-runtime switch. Certification must fail closed if fake/mock/bypass switches are enabled. |
| F-17 | V2 workspace APIs provide patterns worth retaining. | CONFIRMED | **OBSERVED:** production and screenplay V2 routers implement read models, optimistic concurrency, idempotency, parsing/diff/impact/lock validation. V3 should reuse patterns via adapters and leave V2 operational. |
| F-18 | `/api/v3/studio` already exists. | INCORRECT | **OBSERVED:** no V3 Studio route exists. Plan C owns an additive modular router tree and one small application-registration change. |
| F-19 | The desktop currently uses a real API client with no fixed sample IDs. | INCORRECT | **OBSERVED:** `ProductionWorkspacePage` instantiates `FakeProductionApiClient`; client/shell paths contain `vp_001`, `proj-alpha`, and synthesized revisions. Plan C removes production-path fakes and fixed IDs. |
| F-20 | Shared frontend contracts, state, platform, and UI are reusable. | CONFIRMED | **OBSERVED:** the five `production-*` packages and substantial screenplay UI/state exist. Plan C extends them or adds narrow `studio-*` packages without cloning domain definitions. |
| F-21 | `ProductionEnginePort` and a Blender adapter exist. | CONFIRMED | **OBSERVED:** a provider-neutral typed IR port and `BlenderEngineAdapter` exist; worker registration is environment guarded. These are protected by regression gates. |
| F-22 | An Unreal adapter and typed runtime capability profile exist. | INCORRECT | **OBSERVED:** no Unreal implementation and no `RuntimeCapabilityProfile` were found. Roadmap 1 creates only capability-discovery foundations; it does not implement Unreal production. |
| F-23 | Architectural and version evidence is currently green. | INCORRECT | **OBSERVED:** architecture check fails with 13 violations; version consistency fails on one hardcoded product literal and warns on desktop/product drift. A historic audit cannot substitute for a current pass. |
| F-24 | Current tests certify the full Studio vertical slice. | INCORRECT | **OBSERVED:** selected Python and desktop suites pass, but no Studio slice exists and the shared production UI package has a test-runner setup failure. Final certification remains future work. |
| F-25 | The internal terminal state should be named both `READY_FOR_PRODUCTION` and `EPISODE_READY_FOR_PRODUCTION`. | INCORRECT | **RESOLVED in `01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md` (contract v0.1):** one enum value, `READY_FOR_PRODUCTION`; the aggregate-qualified event is `studio.episode.ready_for_production`. No second state value is introduced. |

## Concrete evidence map

These are the principal current symbols/files an implementing agent must inspect before editing; the list is evidence routing, not implied ownership:

| Area | Current source/symbol | Finding |
|---|---|---|
| Project/revision domain | `core/windagent_core/domain/video_production/project.py` — `VideoProject`, `ProductionRevision`, `RevisionService` | Reuse/migrate; do not duplicate. |
| Existing screenplay domain | `core/windagent_core/domain/video_production/screenplay.py` — `CreativeBrief`, `StoryConcept`, `DialogueLine`, `Screenplay` | Reuse compatible content and add explicit adapters. |
| Existing approvals | `core/windagent_core/domain/video_production/approval.py` | Hash/revision-bound primitives exist; Studio policy/checkpoints do not. |
| VP3D episode runtime | `core/windagent_core/domain/video_production/episode.py` | Protect from collision with creative Studio `Episode`. |
| Project/revision SQL | `storage/windagent_storage/video_production/video_production_models.py`, `repositories.py`, `unit_of_work/video_production_uow.py` | Additive migration/compatibility base. |
| Canonical DAG service | `orchestration/windagent_orchestration/orchestrator_service.py` — `OrchestratorService` | Extend as sole new Story authority. |
| Durable plan scheduler | `orchestration/windagent_orchestration/durable_plan_scheduler.py` — `DurablePlanScheduler` | Existing multi-agent claim/release seam, not the worker task queue itself. |
| Other workflow authorities | `orchestration/windagent_orchestration/workflow_engine/engine.py`; `orchestration/windagent_orchestration/production/engine.py` | Deprecate/isolate for Story; preserve legacy behavior. |
| Runtime registry | `execution/windagent_execution/registry.py` — `ExecutionRuntimeRegistry` | Add Studio handler seam without replacing existing capabilities. |
| Durable submission/queue | `storage/windagent_storage/queue/submission_adapter.py` — `SqlWorkSubmissionAdapter`; `storage/windagent_storage/queue/sql_queue.py` — `SqlDurableTaskQueue` | Real transaction/claim/lease foundation; generic envelope needs compatible extension. |
| Worker/finalization | `apps/worker/windagent_worker/runner.py` — `ProductionWorker`; `storage/windagent_storage/services/task_finalizer.py` — `TaskFinalizer` | Preserve fencing/heartbeat/CAS/outbox guarantees. |
| Provider route authority | `providers/windagent_providers/routing/route_lock_service.py`; `providers/windagent_providers/routing/execution_coordinator.py` | Compose the Story model adapter here, outside Story domain logic. |
| Existing ideation | `intelligence/windagent_intelligence/video/ideation/brief_expander.py`; `ideation/outliner.py` | Useful services, but no canonical 3–5 candidate/evaluation pipeline. |
| Existing screenplay intelligence | `intelligence/windagent_intelligence/video/screenplay/writer.py`; `screenplay/narration.py` | Incremental extraction; structured screenplay contract must replace tolerant text authority. |
| V2 API patterns | `apps/api/windagent_api/routers/v2_production_workspace.py`; `v2_screenplay_workspace.py` | Retain compatibility/idempotency/concurrency patterns. |
| Desktop fake path | `apps/desktop/src/pages/ProductionWorkspacePage.tsx`; `frontend/packages/production-client/src/ProductionApiClient.ts`; `frontend/packages/production-ui/src/components/ProductionShell.tsx` | Remove production fake/default/synthesized data through Plan C migration. |
| Production engine boundary | `core/windagent_core/contracts/video_production/production_engine.py`; `tools/windagent_tools/production_engines/blender/adapter.py` | Existing neutral port + real Blender adapter; regression protect. |

## Current architecture truth

### Domain and persistence

**OBSERVED:** `VideoProject`, `ProductionRevision`, and revision derivation/locking already form a solid compatibility base. Their SQL representation uses `video_production_projects` and `video_production_revisions`. The ORM does not yet carry the complete Studio relationship and provenance surface: creative episode identity, actor, explicit lock/invalidation data, and story-artifact relationships need additive migration.

**INFERRED:** the lowest-risk route is an additive schema evolution with backfill and repository adapters, not a second Studio database. `SeriesProject` becomes the product-level name, while old V2 reads and IDs remain valid until deprecation completes.

**OBSERVED:** four current core application-service modules import concrete storage code. Together with undeclared package dependencies and cycles, the live architecture checker reports 13 violations. Plan A owns the boundary repair. Plans B and C must not independently edit these hot modules.

### Orchestration, durable work, and events

**OBSERVED:** `OrchestratorService` persists a multi-agent plan/DAG and dispatches through `ExecutionRuntimeRegistry`. `ProductionWorker` follows another real path: `SqlWorkSubmissionAdapter` records task plus `TaskSubmitted` outbox data; `SqlDurableTaskQueue` claims with row locks, leases, and fencing; the worker dispatches through the same runtime registry; `TaskFinalizer` performs CAS result/final-state/outbox/lease finalization in one transaction.

**INFERRED:** Roadmap 1 needs one orchestration command surface that turns an approved DAG node into a versioned durable submission and consumes durable completion to advance the DAG. It must not call a new story scheduler or allow the API to skip the orchestrator.

**OBSERVED:** the event catalog and taxonomy checker are established, but no Studio/story event family exists. The outbox is the authoritative durable publication boundary in the worker finalization path. Plans must not claim that every terminal event is also independently inserted into a second event store unless implementation proves it.

### Provider and model execution

**OBSERVED:** the provider layer contains `RouteLockService`, `EndpointExecutionCoordinator`, canonical adapters, and route provenance. Story services depend on `PreproductionModelPort`, for which only test doubles were located. Another gateway bridge is specialized and hard-wired enough that it should not become the canonical Studio route.

**PROPOSED:** Plan A builds the infrastructure adapter from the provider coordinator to the story model port, preserving route/model/prompt/schema provenance. Plan B owns prompts, schemas, parsers, and domain validation. The final slice explicitly disables `WINDAGENT_FAKE_RUNTIME` and any mock/emergency provider fallback.

### API and desktop

**OBSERVED:** V2 production and screenplay workspaces are useful compatibility surfaces. They already demonstrate idempotency, optimistic concurrency, structured errors, diffs, impacts, and lock validation. `/api/v3/studio` is absent.

**OBSERVED:** the desktop is the required product shell, but its active production page uses a fake client and fixed sample identifiers. Web builds/tests remain supporting verification only; Tauri is the certification target.

**PROPOSED:** Plan C adds one V3 Studio router aggregator backed by application services, schema-derived TypeScript contracts, a real Studio client, and route-driven desktop state. V2 receives deprecation metadata/adapters but is not deleted.

### VP3D and production engines

**OBSERVED:** production-neutral `ProductionEnginePort`, typed IR, a real Blender adapter, and VP3D fixtures/checkpointing are existing strengths. `ProductionWorkflowEngine` is composed behind a Blender environment switch and has no observed non-test `.advance` caller, but remains a parallel authority.

**PROPOSED:** Plan A marks the authority boundary, prevents new Story dependencies, and adds typed capability discovery around existing environment configuration. All plans run VP3D protection tests; none rewrites the Blender pipeline in Roadmap 1.

## Baseline verification record

| Check | Baseline result | Interpretation |
|---|---|---|
| Targeted Python foundation/API/orchestration/worker suites | 40 passed; one upstream deprecation warning | Useful green baseline, not a full-suite or Studio certification. |
| Desktop tests | 11 files, 106 tests passed; Vite/esbuild warning | Desktop baseline is healthy enough to extend. |
| Shared `production-platform` tests | 5 passed | Green. |
| Shared `production-state` tests | 8 passed | Green. |
| Shared `production-ui` tests | 3 suites fail before test execution with `describe is not defined`; 2 files/6 tests pass | Existing setup defect must be classified and fixed by Plan C before its UI gate. |
| `scripts/check_architecture_imports.py` | Fail: 13 live violations | Plan A entry criterion, not a regression introduced by future branches. |
| `scripts/check_version_consistency.py` | Fail: one hardcoded product version; desktop/product drift warning | Plan A/C must define current source of truth and final evidence must be fresh. |
| Video workspace architecture check | Pass | Preserve. |
| No-legacy-orchestration check | Pass | The checker is narrower than “only one composed engine”; extend its Roadmap 1 coverage. |
| Event taxonomy check | Pass, 68 registered event types | Preserve while adding Studio events. |
| Duplicate canonical model check | Pass | Preserve while migrating Studio aliases/facades. |

## Decisions frozen for planning

The following Roadmap decisions are treated as normative for all three plans:

1. Canonical hierarchy: `SeriesProject -> Episode -> ProductionRevision`.
2. Canonical orchestration authority: `OrchestratorService`; legacy engines receive deprecation/isolation fences and no new Story dependencies.
3. Product areas: Story, Assets, Production; generic kernel remains provider/product neutral.
4. Roadmap 1 ends at a locked screenplay and `READY_FOR_PRODUCTION`; no renderer cutover.
5. API base is `/api/v3/studio`; V2 remains available through a deprecation period.
6. Desktop/Tauri is required; Web is a build/test surface only.
7. Approval modes are `AUTO`, `HUMAN_REQUIRED`, and `QUALITY_GATE_ONLY` at IDEA, STORY_BIBLE, OUTLINE, and SCREENPLAY.
8. A locked screenplay is immutable; edits derive a new `ProductionRevision`.
9. Final acceptance uses a real provider/model and durable worker, with no fake, bypass, sample ID, or hardcoded result path.

## Current blockers versus implementation blockers

- **OBSERVED, not blocking planning:** the dirty worktree is intentional and preserved.
- **OBSERVED, implementation entry defects:** 13 architecture violations, version drift, and shared UI test setup failures.
- **BLOCKED until bootstrap decision:** any proposed change to the canonical terminal-state name or versioned contract shapes.
- **BLOCKED until environment certification:** credentials, provider availability, a writable durable database, and a runnable worker/Tauri environment for the real vertical slice.
- **BLOCKED if code owners overlap:** migrations, event catalog, API composition, root lockfiles, or CI workflow edited concurrently outside the ownership matrix.

## Findings verdict

The repository has credible kernel, storage, provider, screenplay-workspace, desktop, and VP3D foundations. It does not yet have one Studio aggregate model, one durable orchestration path, a complete Story artifact pipeline, a V3 Studio API, or a real desktop-to-worker vertical slice. The three-plan decomposition is feasible only after the short contract/bootstrap gate described in `01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md`.
