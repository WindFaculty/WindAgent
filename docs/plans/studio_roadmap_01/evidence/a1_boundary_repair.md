# A1 — Boundary Repair and Authority Fence Evidence

Contract version: `studio.contract/v0.1`. Baseline SHA: `9a09375700db02a64315068f008b15e43ba5f42d`.
Fresh gate: `STUDIO_ARCHITECTURE_GATE`.

## 1. Dependency graph before / after

| Check | Before A1 | After A1 |
|---|---|---|
| `check_architecture_imports.py` | FAIL — 13 violations (4 disallowed core->storage imports, 4 undeclared workspace dependencies, 5 dependency cycles) | PASS — 0 violations |
| core -> storage import edges | `command_dispatcher.py:21`, `query_service.py:12`, `screenplay_command_handlers.py:14`, `screenplay_query_service.py:14` | removed (dependency inverted) |
| Dependency cycles | `core -> storage -> providers -> core` (3 cycles reported) | eliminated |

## 2. Boundary repair slices

Each slice is behavior-preserving and independently revertible.

1. **New core port**: `core/windagent_core/contracts/video_production/video_production_uow.py`
   declares `VideoProductionUnitOfWorkPort` (structural Protocols for projects,
   events, idempotency, read models, commit/rollback) mirroring the real SQL
   repository signatures in `storage/windagent_storage/video_production/repositories.py`.
2. **Inversion**: the four core application services (`CommandDispatcher`,
   `ProductionQueryService`, `ScreenplayCommandHandler`, `ScreenplayQueryService`)
   now type against the port. Callers (V2 routers, tests) keep constructing the
   concrete storage `VideoProductionUnitOfWork` unchanged.
3. **Hidden side-effect dependency fixed**: `video_production_models` was only
   registered on `BaseORM.metadata` transitively through the removed
   core->storage import chain; the Alembic baseline then silently skipped those
   tables for fresh file databases. Explicit registrations added to
   `storage/windagent_storage/migrations/alembic/versions/0001_baseline.py` and
   `env.py`. This is the canonical import-for-side-effect pattern the boundary
   repair must replace, not preserve.

## 3. Legacy authority fence (deprecation inventory)

| Authority | Location | Fence |
|---|---|---|
| `WorkflowEngine` | `orchestration/windagent_orchestration/workflow_engine/engine.py` | DEPRECATED AUTHORITY docstring; `_assert_no_story_node` rejects any node whose id/name/tool_name uses `studio.` / `studio.story.` or whose params reference a `studio.story.*` task type at `initialize_run` (covers `resume_from_checkpoint`). Fence code is wrapped in `# STORY-FENCE-START/END`. |
| `ProductionWorkflowEngine` | `orchestration/windagent_orchestration/production/engine.py` | DEPRECATED AUTHORITY docstring; constructor rejects `ProductionStepNode` with a `studio.` / `studio.story.` step_id (`WINDAGENT_ERR_STORY_LEGACY_ENGINE`). Fence wrapped in `# STORY-FENCE-START/END`. |
| Composition diagnostics | `orchestration/windagent_orchestration/composition.py`, `apps/worker/windagent_worker/composition.py` | `logger.warning("DEPRECATED AUTHORITY: ...")` emitted whenever a legacy engine is composed; VP3D worker composition remains behind `WINDAGENT_BLENDER_ENGINE` env guard (behavior unchanged). |

Checker: `scripts/check_no_story_in_legacy_engines.py` (PASS) — no Story import,
task-type, or event literal enters either legacy tree outside the explicit fence;
docstrings/comments are exempt as documentation.

## 4. OrchestratorService seam

`OrchestratorService.__init__` gains an optional `studio_run_extension` parameter
(inert until Plan A A4 wires it). Public behavior and callers unchanged;
documented as the extension seam for Studio run commands.

## 5. Regression results (fresh, this run)

- Architecture imports checker: PASS (0 violations)
- No-Story-in-legacy-engines checker: PASS
- Event taxonomy (68 registered types): PASS
- Duplicate canonical models: PASS
- Video workspace architecture: PASS
- No-legacy-orchestration: PASS
- `tests/unit/orchestration/` + `tests/unit/worker/` + screenplay workspace unit tests: 170 passed
- `tests/unit/api/` excluding pre-existing failures: 55 passed
- `tests/integration/` + `tests/regression/`: 91 passed, 1 skipped (1 pre-existing failure below)
- `tests/contracts/test_studio_contract_fixtures_v0_1.py` + legacy-engine guard tests: green
- `git diff --check`: clean

## 6. Pre-existing failures classified (owner + retirement gate)

Recorded in `a0_bootstrap_manifest.json` (regenerated this phase):

| Failure | Owner | Retirement gate | Evidence |
|---|---|---|---|
| `check_version_consistency.py` FAIL (hardcoded product literal + desktop drift) | Plan A | `PLAN_A_HANDOFF_GATE` | reproduced at HEAD |
| `production-ui` test runner (`describe is not defined`) | Plan C | `STORY_UI_GATE` | recorded in findings doc |
| `pytest_v2_api_events_contract` (4 tests expect `/api/v2/events`, router serves `/api/v2/video-production/events`) | Plan C | `STORY_UI_GATE` | reproduced at HEAD |
| `pytest_session_recovery_isolation` (WebSocket handshake HTTP 403) | Plan C | `STORY_UI_GATE` | reproduced at HEAD |

## 7. Gate verdict

`STUDIO_ARCHITECTURE_GATE`: PASSED — zero live architecture violations, zero
Story dependency/call edge to either legacy engine, V2/VP3D regression surface
green apart from explicitly classified pre-existing failures.
