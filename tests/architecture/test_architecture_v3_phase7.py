"""Phase 7 — API composition split and execution-ownership removal.

Strong AST/source/runtime guards proving:
- the composition package exists with the required modules and the
  compatibility import works;
- ``container.py`` orchestrates focused composers;
- zero ``ExecutionRuntimeRegistry`` / ``WorktreeContextManager`` references
  anywhere under ``apps/api/windagent_api`` (AST call count and source scan);
- ``ApplicationContainer`` exposes no ``execution_registry`` /
  ``worktree_manager`` attributes;
- no ``get_execution_registry`` dependency; the no-lifespan fallback uses the
  canonical container graph;
- API bootstrap succeeds with a file-backed temporary DB and
  ``WINDAGENT_WORKSPACE_ROOT`` unset (including production configuration with
  required backup evidence supplied by the test);
- API lifespan contains no ``RecoveryManager`` / ``recover_production``;
- control-plane ``OrchestratorService`` with no runtime persists/query
  operations and queues submissions without dispatch;
- demo seed remains opt-in and idempotent without application-layer ORM imports;
- the architecture checker returns zero violations.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
import yaml

import check_architecture_imports as checker  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

API_PACKAGE = ROOT / "apps" / "api" / "windagent_api"
COMPOSITION_DIR = API_PACKAGE / "composition"
REQUIRED_COMPOSITION_MODULES = {
    "__init__.py",
    "database.py",
    "repositories.py",
    "providers.py",
    "realtime.py",
    "studio.py",
    "projects.py",
    "health.py",
    "container.py",
}


def _api_source_files() -> list[Path]:
    return sorted(API_PACKAGE.rglob("*.py"))


def _api_source_text() -> str:
    parts = []
    for path in _api_source_files():
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
    return "\n".join(parts)


def _ast_call_names(path: Path, names: set[str]) -> list[tuple[int, str]]:
    """Return (lineno, name) for every AST Call whose func name is in ``names``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            hits.append((node.lineno, func.id))
        elif isinstance(func, ast.Attribute) and func.attr in names:
            hits.append((node.lineno, func.attr))
    return hits


# ── composition package structure ───────────────────────────────────────────


def test_composition_package_modules_exist():
    """The required composition package/modules exist."""
    assert COMPOSITION_DIR.is_dir(), "composition package directory missing"
    present = {p.name for p in COMPOSITION_DIR.rglob("*.py")}
    missing = REQUIRED_COMPOSITION_MODULES - present
    assert not missing, f"required composition modules missing: {sorted(missing)}"


def test_compatibility_import_works():
    """``from windagent_api.composition import ApplicationContainer`` works."""
    from windagent_api.composition import ApplicationContainer

    assert ApplicationContainer.__name__ == "ApplicationContainer"


def test_container_orchestrates_focused_composers():
    """``container.py`` orchestrates the focused composer modules."""
    container_source = (COMPOSITION_DIR / "container.py").read_text(encoding="utf-8")
    tree = ast.parse(container_source, filename=str(COMPOSITION_DIR / "container.py"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
    for composer in (
        "windagent_api.composition.database",
        "windagent_api.composition.repositories",
        "windagent_api.composition.providers",
        "windagent_api.composition.realtime",
        "windagent_api.composition.studio",
        "windagent_api.composition.projects",
        "windagent_api.composition.health",
    ):
        assert composer in imported_modules, f"container.py does not import {composer}"
    # The container must not hand-compose the runtime/worktree authorities.
    assert "ExecutionRuntimeRegistry" not in container_source
    assert "WorktreeContextManager" not in container_source


# ── execution ownership removal ─────────────────────────────────────────────


def test_zero_execution_runtime_references_in_api_source():
    """No API file calls or names the execution runtime / worktree authorities."""
    forbidden = {"ExecutionRuntimeRegistry", "WorktreeContextManager"}
    source = _api_source_text()
    for name in forbidden:
        assert name not in source, f"{name} appears in API source"
    for path in _api_source_files():
        hits = _ast_call_names(path, forbidden)
        assert not hits, f"{path.relative_to(ROOT)} calls forbidden symbols: {hits}"


def test_container_has_no_execution_attributes():
    """ApplicationContainer exposes no execution_registry / worktree_manager."""
    from windagent_api.composition import ApplicationContainer

    container = ApplicationContainer(db_url="sqlite+aiosqlite:///unused.db")
    assert not hasattr(container, "execution_registry")
    assert not hasattr(container, "worktree_manager")


def test_no_get_execution_registry_dependency():
    """``get_execution_registry`` is removed from API dependencies."""
    dependencies_source = (API_PACKAGE / "dependencies.py").read_text(encoding="utf-8")
    assert "get_execution_registry" not in dependencies_source
    assert "ExecutionRuntimeRegistry" not in dependencies_source


def test_fallback_uses_canonical_container_graph():
    """The no-lifespan fallback drives the canonical container bootstrap."""
    dependencies_source = (API_PACKAGE / "dependencies.py").read_text(encoding="utf-8")
    assert "container.bootstrap()" in dependencies_source
    assert "container.seed_demo_profile()" in dependencies_source
    # The fallback must not hand-compose runtime/provider/realtime/storage
    # authorities again.
    assert "ExecutionRuntimeRegistry" not in dependencies_source
    assert "make_sync_session_factory" not in dependencies_source


# ── bootstrap without workspace root ────────────────────────────────────────


def test_api_bootstrap_without_workspace_root(tmp_path, monkeypatch):
    """API bootstrap succeeds with a file-backed temp DB and no workspace root."""
    monkeypatch.delenv("WINDAGENT_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("WINDAGENT_ENV", "test")
    monkeypatch.setenv("WINDAGENT_PROFILE", "test")

    from windagent_api.composition import ApplicationContainer

    async def run() -> None:
        db_path = tmp_path / "phase7_bootstrap.db"
        container = ApplicationContainer(
            db_url=f"sqlite+aiosqlite:///{db_path}"
        )
        await container.bootstrap()
        try:
            assert container.is_initialized
            assert container.db is not None
            assert container.orchestrator_service is not None
            assert container.orchestrator_service._execution_registry is None
            assert container.orchestrator_service._worktree_manager is None
        finally:
            await container.shutdown()

    asyncio.run(run())


def test_api_bootstrap_production_with_backup_evidence(tmp_path, monkeypatch):
    """Production bootstrap succeeds when required backup evidence is supplied."""
    monkeypatch.delenv("WINDAGENT_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("WINDAGENT_ENV", "production")
    monkeypatch.setenv("WINDAGENT_PROFILE", "production")
    monkeypatch.setenv("WINDAGENT_RELEASE_BACKUP_ROOT", str(tmp_path))

    from windagent_api.composition import ApplicationContainer

    async def run() -> None:
        db_path = tmp_path / "phase7_prod.db"
        container = ApplicationContainer(
            db_url=f"sqlite+aiosqlite:///{db_path}"
        )
        await container.bootstrap()
        try:
            assert container.is_initialized
            assert container.orchestrator_service is not None
            assert container.orchestrator_service._execution_registry is None
        finally:
            await container.shutdown()

    asyncio.run(run())


def test_api_bootstrap_production_fails_closed_without_backup_evidence(
    tmp_path, monkeypatch
):
    """Production bootstrap fails closed when backup evidence is missing."""
    monkeypatch.delenv("WINDAGENT_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("WINDAGENT_ENV", "production")
    monkeypatch.delenv("WINDAGENT_RELEASE_BACKUP_ROOT", raising=False)

    from windagent_api.composition import ApplicationContainer

    async def run() -> None:
        db_path = tmp_path / "phase7_prod_fail.db"
        container = ApplicationContainer(
            db_url=f"sqlite+aiosqlite:///{db_path}"
        )
        with pytest.raises(RuntimeError):
            await container.bootstrap()

    asyncio.run(run())


# ── lifespan recovery removal ───────────────────────────────────────────────


def test_lifespan_has_no_recovery_manager():
    """API lifespan contains no RecoveryManager / recover_production."""
    lifespan_source = (API_PACKAGE / "lifespan.py").read_text(encoding="utf-8")
    assert "RecoveryManager" not in lifespan_source
    assert "recover_production" not in lifespan_source
    assert "windagent_orchestration.recovery" not in lifespan_source
    # Lifespan must not import storage/database directly.
    assert "make_sync_session_factory" not in lifespan_source


# ── control-plane OrchestratorService ───────────────────────────────────────


@pytest.fixture
async def control_db(tmp_path):
    from windagent_storage.database.connection import DatabaseManager
    from windagent_storage.orm.models import BaseORM

    manager = DatabaseManager(
        f"sqlite+aiosqlite:///{tmp_path / 'phase7_control.db'}"
    )
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_control_plane_orchestrator_queues_without_dispatch(control_db):
    """Control-plane OrchestratorService persists/query operations and queues
    submissions without dispatch; no runtime instance exists."""
    from windagent_orchestration.orchestrator_service import OrchestratorService
    from windagent_storage.repositories.multi_agent_repository import (
        MultiAgentRepository,
    )

    service = OrchestratorService(
        control_db.session_factory,
        None,  # no execution runtime
        repo_factory=lambda session: MultiAgentRepository(session),
    )
    assert service._execution_registry is None

    # Pure SQL control-plane CRUD works.
    conv = await service.create_conversation(
        conversation_id="conv-phase7-cp",
        title="Phase 7 control plane",
        objective="Prove control-plane CRUD without a runtime",
    )
    assert conv["id"] == "conv-phase7-cp"
    assert conv["status"] == "ACTIVE"

    launched = await service.launch_agent(
        agent_instance_id="inst-phase7-cp",
        conversation_id="conv-phase7-cp",
        definition_id="def-coder-01",
        agent_type="coder",
    )
    assert launched["id"] == "inst-phase7-cp"

    # submit_goal persists the durable plan/ownership rows but does not
    # dispatch; returned agents remain queued for Worker pickup.
    result = await service.submit_goal(
        conversation_id="conv-phase7-cp",
        objective="Queue a goal without a runtime",
    )
    assert result.conversation_id == "conv-phase7-cp"
    assert result.agents
    assert all(agent.status == "queued" for agent in result.agents)
    assert all(agent.runtime_run_id is None for agent in result.agents)

    # The durable rows are persisted and queryable.
    agents = await service.list_agents("conv-phase7-cp")
    assert len(agents) >= 3  # launched instance + two queued plan agents
    assert await service.get_conversation("conv-phase7-cp") is not None

    # No live runtime handle was ever registered.
    assert service.live_agent_run_ids == frozenset()


@pytest.mark.asyncio
async def test_control_plane_stop_agent_fails_closed(control_db):
    """``stop_agent`` without a runtime fails closed before any mutation.

    Active queued runs belong to the Worker's execution runtime, which is not
    composed in control-plane mode.  ``stop_agent`` must raise before runtime
    cancellation, worktree cleanup, durable status changes, events, commits, or
    live-registry removal; the durable run stays active/queued and unchanged.
    """
    from windagent_orchestration.orchestrator_service import OrchestratorService
    from windagent_storage.repositories.multi_agent_repository import (
        MultiAgentRepository,
    )

    service = OrchestratorService(
        control_db.session_factory,
        None,  # no execution runtime
        repo_factory=lambda session: MultiAgentRepository(session),
    )
    assert service._execution_registry is None

    await service.create_conversation(
        conversation_id="conv-phase7-stop",
        title="Phase 7 stop fail-closed",
        objective="Prove stop_agent fails closed without a runtime",
    )
    result = await service.submit_goal(
        conversation_id="conv-phase7-stop",
        objective="Queue a goal that must stay queued",
    )
    target = result.agents[0]
    assert target.status == "queued"
    assert target.runtime_run_id is None

    # Snapshot the durable run before attempting cancellation.
    async with control_db.session_factory() as session:
        repo = MultiAgentRepository(session)
        before = await repo.active_runs_for_agent(target.agent_instance_id)
    assert before, "queued AgentRun must be considered active by active_runs_for_agent"

    # The read-only query found active rows, so stop_agent must fail closed.
    with pytest.raises(RuntimeError, match="execution runtime is not composed"):
        await service.stop_agent(
            target.agent_instance_id, conversation_id=result.conversation_id
        )

    # No live handle was ever registered, and the durable run/status is
    # unchanged: still active and still queued.
    assert service.live_agent_run_ids == frozenset()
    async with control_db.session_factory() as session:
        repo = MultiAgentRepository(session)
        after = await repo.active_runs_for_agent(target.agent_instance_id)
    assert after, "durable run must remain active after failed stop_agent"
    assert [run["agent_run_id"] for run in after] == [
        run["agent_run_id"] for run in before
    ]
    assert all(run["status"] == "queued" for run in after)
    assert all(run["version"] == 1 for run in after), (
        "failed stop_agent must not bump durable run versions"
    )


@pytest.mark.asyncio
async def test_control_plane_dispatch_fails_closed(control_db):
    """A direct dispatch attempt without a runtime fails closed before mutation."""
    from windagent_orchestration.orchestrator_service import OrchestratorService
    from windagent_storage.repositories.multi_agent_repository import (
        MultiAgentRepository,
    )

    service = OrchestratorService(
        control_db.session_factory,
        None,
        repo_factory=lambda session: MultiAgentRepository(session),
    )
    # Scheduler ticks return the explicit no-runtime result (nothing claimed,
    # nothing dispatched) rather than touching a runtime.
    assert await service.schedule_due_nodes() == ()
    assert await service.reconcile_runtime_completions() == ()
    # A direct dispatch attempt fails closed before any mutation.
    with pytest.raises(RuntimeError):
        await service._dispatch_agent_run(
            conversation_id="conv-x",
            parent_task_id="pt-x",
            plan_version_id="pv-x",
            launch={
                "agent_instance_id": "inst-x",
                "agent_session_id": "sess-x",
                "agent_run_id": "run-x",
                "task_node_run_id": "tnr-x",
                "windagent_session_id": "ws-x",
                "node_id": "node-x",
                "agent_type": "generalist",
                "objective": "x",
                "fencing_token": "tok",
            },
        )


# ── demo seed ───────────────────────────────────────────────────────────────


def test_demo_seed_has_no_application_layer_orm_imports():
    """``v3_demo_seed.py`` remains application logic with no ORM/database imports."""
    seed_source = (
        API_PACKAGE / "services" / "v3_demo_seed.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(seed_source, filename=str(API_PACKAGE / "services" / "v3_demo_seed.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("windagent_storage"), (
                f"v3_demo_seed.py imports storage: {module}"
            )
            assert not module.startswith("sqlalchemy"), (
                f"v3_demo_seed.py imports sqlalchemy: {module}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("windagent_storage"), (
                    f"v3_demo_seed.py imports storage: {alias.name}"
                )
    assert "CanonicalModelV3ORM" not in seed_source


def test_demo_seed_opt_in_and_idempotent(tmp_path):
    """Demo seeding is opt-in and idempotent through the container operation."""
    from windagent_api.composition import ApplicationContainer

    async def run() -> None:
        db_path = tmp_path / "phase7_demo.db"
        container = ApplicationContainer(
            db_url=f"sqlite+aiosqlite:///{db_path}"
        )
        await container.bootstrap()
        try:
            # Default startup (no demo profile) leaves the DB free of demo rows.
            projects = await container.v3_resource_service.list("projects")
            assert projects == []

            # Explicit seeding installs records and is idempotent.
            await container.seed_demo_profile()
            first = await container.v3_resource_service.list("projects")
            assert len(first) >= 1

            await container.seed_demo_profile()
            second = await container.v3_resource_service.list("projects")
            assert len(second) == len(first)
            assert {p["id"] for p in first} == {p["id"] for p in second}
        finally:
            await container.shutdown()

    asyncio.run(run())


# ── architecture checker ────────────────────────────────────────────────────


def test_architecture_checker_returns_zero():
    """``python scripts/check_architecture_imports.py`` returns zero violations.

    Uses the same default configuration as the CLI command (scaffold_v2.yaml).
    """
    policy = yaml.safe_load(
        (ROOT / "configs" / "architecture" / "scaffold_v2.yaml").read_text(
            encoding="utf-8"
        )
    )
    report, _ = checker.check(ROOT, policy)
    assert report["status"] == "PASS", report["violations"]
    assert report["total_violations"] == 0, report["violations"]