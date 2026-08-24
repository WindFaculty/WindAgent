"""
CLI Composition Root for WindAgent V2 (PHASE 7).
Provides per-command service composition - each CLI command composes only what it needs.

CLI Composition Strategy (PHASE 7):
- NO global "god container" for all CLI commands
- Each command composes its own required services
- Commands are independent and isolated

Command-specific compositions:
- doctor: Architecture checker, import boundary checker
- architecture-check: Scaffold checker, import boundary checker
- run: TaskManager, Provider registry, Tool registry
- eval: Evaluation service
- provider test: Provider registry, health checker
- worker status: Worker status query

CLI does NOT compose:
- Full API services
- Full Worker services
- Desktop services
"""

from __future__ import annotations
import logging
from typing import Optional, Sequence

logger = logging.getLogger("windagent.cli.composition")


def _canonical_schema_head() -> Optional[str]:
    """Canonical Alembic head for the health checker's schema_migration gate.

    Local import: this file is a composition root, but keeping the storage
    dependency lazy matches the per-command composition strategy.
    """
    from windagent_storage.migrations.runner import alembic_heads

    heads = alembic_heads()
    return heads[0] if len(heads) == 1 else None


def _require_existing_sqlite_database(db_url: str) -> None:
    """Fail before connecting when a read command targets a missing SQLite DB."""
    from pathlib import Path

    if not db_url.startswith(("sqlite:///", "sqlite+aiosqlite:///")):
        return
    database = db_url.split("///", 1)[1].split("?", 1)[0]
    if database in ("", ":memory:"):
        return
    path = Path(database)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise FileNotFoundError(
            f"Database is unavailable (run migrations/setup first): {path}"
        )


class DoctorCommandComposer:
    """Composes services for 'doctor' command using real HealthChecker service."""

    def __init__(
        self,
        db_url: str = None,
        profile: Optional[str] = None,
        component: Optional[str] = None,
    ):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self.profile = profile
        self.component = component
        self._checker_scripts = []
        self._health_checker = None

    def add_checker_script(self, script_path: str) -> None:
        self._checker_scripts.append(script_path)

    async def initialize(self):
        """Initialize HealthChecker with real services."""
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.repositories.worker_status import (
            SqlWorkerHeartbeatRepository,
            SqlWorkerStatusQuery,
        )
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        from windagent_tools.registry import ToolRegistry
        from windagent_plugins.registry import PluginRegistry
        from windagent_skills.registry import SkillRegistry
        from windagent_workflows.registry import WorkflowRegistry
        from windagent_observability.events.dispatcher import EventDispatcher
        from windagent_observability.health import HealthChecker, HealthProfile

        # Initialize database
        db = DatabaseManager(self.db_url)
        try:
            from windagent_storage.orm.models import BaseORM
            await db.upgrade_to_head(BaseORM.metadata)
        except Exception:
            pass  # Tables may already exist

        # Initialize registries (DB-backed when db available)
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import (
            SQLEndpointBindingRepository,
        )
        sync_factory = make_sync_session_factory(self.db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())
        provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)
        tool_registry = ToolRegistry()
        plugin_registry = PluginRegistry()
        skill_registry = SkillRegistry()
        workflow_registry = WorkflowRegistry()
        event_dispatcher = EventDispatcher()

        # Initialize worker status query
        worker_status_query = SqlWorkerStatusQuery(
            SqlWorkerHeartbeatRepository(db.session_factory)
        )

        # Determine profile from environment
        import os
        env = self.profile or os.environ.get("WINDAGENT_ENV", "development")
        profile = HealthProfile(env)

        # Create HealthChecker
        self._health_checker = HealthChecker(
            db_session_factory=db.session_factory,
            worker_status_query=worker_status_query,
            provider_registry=provider_registry,
            tool_registry=tool_registry,
            plugin_registry=plugin_registry,
            skill_registry=skill_registry,
            workflow_registry=workflow_registry,
            event_dispatcher=event_dispatcher,
            expected_schema_head=_canonical_schema_head(),
            profile=profile,
        )

        return db

    async def run_checks(self) -> dict:
        """Runs all diagnostic checks using HealthChecker service."""
        import subprocess
        import sys
        from pathlib import Path
        from windagent_observability.health import HealthStatus

        # First run architecture script checks
        script_results = {}
        root_dir = Path(__file__).resolve().parent.parent.parent.parent

        # Check architecture imports
        checker_script = root_dir / "scripts" / "check_architecture_imports.py"
        if checker_script.exists():
            res = subprocess.run([sys.executable, str(checker_script)],
                               capture_output=True, text=True)
            script_results["import_boundary_check"] = {
                "passed": res.returncode == 0,
                "details": res.stdout + res.stderr if res.returncode != 0 else "Zero import boundary violations"
            }

        # Check scaffold
        scaffold_script = root_dir / "scripts" / "scaffold_architecture_v2.py"
        if scaffold_script.exists():
            res = subprocess.run([sys.executable, str(scaffold_script), "--check"],
                               capture_output=True, text=True)
            script_results["scaffold_structure_check"] = {
                "passed": res.returncode == 0,
                "details": res.stdout + res.stderr if res.returncode != 0 else "Scaffold structure OK"
            }

        # Check duplicate models
        dup_script = root_dir / "scripts" / "check_duplicate_canonical_models.py"
        if dup_script.exists():
            res = subprocess.run([sys.executable, str(dup_script)],
                               capture_output=True, text=True)
            script_results["duplicate_model_check"] = {
                "passed": res.returncode == 0,
                "details": res.stdout + res.stderr if res.returncode != 0 else "ZERO duplicate models found"
            }

        # Now run real health checks
        db = None
        try:
            db = await self.initialize()
            components = [self.component] if self.component else None
            readiness_status = await self._health_checker.check_readiness(
                components=components
            )
            is_alive = await self._health_checker.check_liveness()

            # Convert health check results
            health_checks = {}
            for name, check_result in readiness_status.checks.items():
                health_checks[name] = {
                    "passed": check_result.status in (
                        HealthStatus.UP,
                        HealthStatus.NOT_REQUIRED,
                    ),
                    "details": check_result.message,
                    "status": check_result.status.value,
                    "required": check_result.required,
                }

            # Add liveness check
            health_checks["liveness"] = {
                "passed": is_alive,
                "details": "Process event loop alive" if is_alive else "Process not responsive",
                "status": "UP" if is_alive else "DOWN",
                "required": True,
            }

            # Combine results
            for check in script_results.values():
                check.setdefault("required", True)
                check.setdefault("status", "UP" if check["passed"] else "DOWN")
            all_checks = {**script_results, **health_checks}

            overall_status = readiness_status.overall_status
            if not is_alive or any(
                not check.get("passed", False)
                for check in script_results.values()
            ):
                overall_status = HealthStatus.DOWN

            legacy_status = {
                HealthStatus.UP: "ALL_SYSTEMS_OPERATIONAL",
                HealthStatus.DEGRADED: "SYSTEM_HEALTH_DEGRADED",
                HealthStatus.DOWN: "SYSTEM_HEALTH_DOWN",
            }[overall_status]

            return {
                "status": legacy_status,
                "overall_status": overall_status.value,
                "profile": readiness_status.profile.value,
                "checks": all_checks,
            }

        finally:
            if db:
                await db.close()

    def run_checks_sync(self) -> dict:
        """Synchronous wrapper for run_checks."""
        import asyncio
        return asyncio.run(self.run_checks())


class RunCommandComposer:
    """Composes services for 'run' command."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self._task_manager = None
        self._provider_registry = None
        self._tool_registry = None

    async def bootstrap(self):
        """Bootstraps only services needed for 'run' command."""
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.orm.models import BaseORM
        from windagent_orchestration.task_manager.service import TaskManager
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        from windagent_tools.registry import ToolRegistry

        logger.info("Bootstrapping Run command services...")

        # Only compose what 'run' needs
        db = DatabaseManager(self.db_url)
        try:
            await db.upgrade_to_head(BaseORM.metadata)
        except Exception as ex:
            logger.warning(f"Database migration warning: {ex}")

        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import (
            SQLEndpointBindingRepository,
        )
        sync_factory = make_sync_session_factory(self.db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())

        self._task_manager = TaskManager(uow_factory=db.session_factory)
        self._provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)
        self._tool_registry = ToolRegistry()

        logger.info("Run command services bootstrapped.")
        return db

    async def shutdown(self, db):
        """Shuts down Run command services."""
        if db:
            await db.close()


class ProviderTestCommandComposer:
    """Composes services for 'provider test' command."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite:///windagent.db")
        self._provider_registry = None

    async def bootstrap(self):
        """Bootstraps only services needed for provider testing."""
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import (
            SQLEndpointBindingRepository,
        )
        sync_factory = make_sync_session_factory(self.db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())

        logger.info("Bootstrapping Provider test command services...")
        self._provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)
        logger.info("Provider test command services bootstrapped.")

    async def shutdown(self):
        if self._provider_registry:
            await self._provider_registry.close()


class WorkerStatusCommandComposer:
    """Composes services for 'worker status' command."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self._worker_status_query = None

    async def bootstrap(self):
        """Bootstraps only services needed for worker status query."""
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.repositories.worker_status import (
            SqlWorkerHeartbeatRepository,
            SqlWorkerStatusQuery,
        )

        logger.info("Bootstrapping Worker status command services...")

        db = DatabaseManager(self.db_url)
        try:
            from windagent_storage.orm.models import BaseORM
            await db.upgrade_to_head(BaseORM.metadata)
        except Exception as ex:
            logger.warning(f"Database setup warning: {ex}")

        self._worker_status_query = SqlWorkerStatusQuery(
            SqlWorkerHeartbeatRepository(db.session_factory)
        )
        logger.info("Worker status command services bootstrapped.")
        return db

    async def shutdown(self, db):
        if db:
            await db.close()


class ArchitectureCheckCommandComposer:
    """Composes services for 'architecture-check' command."""

    def __init__(self):
        pass

    async def bootstrap(self):
        """Bootstraps architecture checking services."""
        # Uses scripts, no service composition needed
        logger.info("Architecture check uses scripts - no composition needed.")

    async def shutdown(self):
        pass


class TaskListCommandComposer:
    """Composes services for 'task list' command using real TaskRepository."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self._task_repo = None
        self._db = None

    async def bootstrap(self):
        """Open the configured database without creating schema."""
        from windagent_storage.database.connection import DatabaseManager

        _require_existing_sqlite_database(self.db_url)
        self._db = DatabaseManager(self.db_url)
        return self._db

    async def shutdown(self, db):
        if db:
            await db.close()

    async def list_tasks(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = None,
        after: str = None,
        session_id: str = None,
    ) -> list:
        """List tasks from real TaskRepository."""
        from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
        from windagent_storage.orm.v2_orchestration_models import TaskRunORM
        from datetime import datetime, timezone
        from sqlalchemy import select
        import json

        if not self._db:
            await self.bootstrap()

        async with SqlUnitOfWork(self._db.session_factory) as uow:
            stmt = select(TaskRunORM)
            if status:
                stmt = stmt.where(TaskRunORM.state == status)
            if session_id:
                stmt = stmt.where(TaskRunORM.session_id == session_id)
            if after:
                try:
                    cursor = datetime.fromisoformat(after.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError("--after must be an ISO-8601 timestamp") from exc
                if cursor.tzinfo is not None:
                    cursor = cursor.astimezone(timezone.utc).replace(tzinfo=None)
                stmt = stmt.where(TaskRunORM.created_at < cursor)
            stmt = (
                stmt.order_by(TaskRunORM.created_at.desc(), TaskRunORM.id.desc())
                .limit(limit)
                .offset(offset)
            )
            res = await uow.session.execute(stmt)
            orms = res.scalars().all()

            tasks = []
            for orm in orms:
                facts = json.loads(orm.facts_json) if orm.facts_json else {}
                tasks.append({
                    "task_id": orm.id,
                    "session_id": orm.session_id,
                    "status": orm.state,
                    "workflow_name": facts.get("workflow_name", "unknown"),
                    "prompt": facts.get("prompt", ""),
                    "created_at": orm.created_at.isoformat() if orm.created_at else None,
                    "updated_at": orm.updated_at.isoformat() if orm.updated_at else None,
                })
            return tasks


class TaskInspectCommandComposer:
    """Composes services for 'task inspect' command using real TaskRepository."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self._db = None

    async def bootstrap(self):
        """Open the configured database without creating schema."""
        from windagent_storage.database.connection import DatabaseManager

        _require_existing_sqlite_database(self.db_url)
        self._db = DatabaseManager(self.db_url)
        return self._db

    async def shutdown(self, db):
        if db:
            await db.close()

    async def inspect_task(self, task_id: str) -> dict:
        """Inspect specific task from real TaskRepository."""
        from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
        from windagent_storage.repositories.v2_orchestration_repositories import SqlTaskRunRepository

        if not self._db:
            await self.bootstrap()

        async with SqlUnitOfWork(self._db.session_factory) as uow:
            repo = SqlTaskRunRepository(uow.session)
            task = await repo.get_by_id(task_id)

            if not task:
                return None

            return task


class ReplayCommandComposer:
    """Composes services for 'replay' command using real EventStore."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self._db = None

    async def bootstrap(self):
        """Open the event store without creating schema."""
        from windagent_storage.database.connection import DatabaseManager

        _require_existing_sqlite_database(self.db_url)
        self._db = DatabaseManager(self.db_url)
        return self._db

    async def shutdown(self, db):
        if db:
            await db.close()

    async def replay_trace(self, trace_id: str) -> dict:
        """Replay trace from real EventStore."""
        import hashlib
        import json
        from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
        from windagent_storage.repositories.sql_repositories import SqlEventStore

        if not self._db:
            await self.bootstrap()

        async with SqlUnitOfWork(self._db.session_factory) as uow:
            event_store = SqlEventStore(uow.session)
            events = await event_store.get_events(stream_id=trace_id, after_sequence=0, limit=1000)

            if not events:
                return None

            step_sequence = [event.event_type for event in events]
            sequences = [event.sequence for event in events]
            ordering_verified = (
                sequences == sorted(sequences) and len(sequences) == len(set(sequences))
            )
            reconstructed_state = {}
            output_projection = []
            for event in events:
                if isinstance(event.payload, dict):
                    reconstructed_state.update(event.payload)
                output_projection.append({
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "payload": event.payload,
                })

            def digest(value) -> str:
                encoded = json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
                return hashlib.sha256(encoded).hexdigest()

            reconstructed_state_hash = digest(reconstructed_state)
            output_hash = digest(output_projection)
            reference = events[-1].metadata or {}
            expected_count = reference.get("expected_event_count")
            expected_state_hash = reference.get("expected_state_sha256")
            expected_output_hash = reference.get("expected_output_sha256")
            has_reference = (
                isinstance(expected_count, int)
                and isinstance(expected_state_hash, str)
                and isinstance(expected_output_hash, str)
            )
            parity_checks = {
                "event_count": (
                    len(events) == expected_count if has_reference else None
                ),
                "ordering": ordering_verified,
                "reconstructed_state_hash": (
                    reconstructed_state_hash == expected_state_hash
                    if has_reference else None
                ),
                "output_hash": (
                    output_hash == expected_output_hash if has_reference else None
                ),
            }
            if not has_reference:
                parity = "UNAVAILABLE"
            elif all(parity_checks.values()):
                parity = "100%"
            else:
                parity = "MISMATCH"

            return {
                "trace_id": trace_id,
                "replay_status": "REPLAYED",
                "step_sequence": step_sequence,
                "deterministic_parity": parity,
                "events_count": len(events),
                "ordering_verified": ordering_verified,
                "reconstructed_state_sha256": reconstructed_state_hash,
                "expected_state_sha256": expected_state_hash,
                "output_sha256": output_hash,
                "expected_output_sha256": expected_output_hash,
                "parity_checks": parity_checks,
            }


class ProvidersCommandComposer:
    """Composes services for 'providers' command using real CanonicalModelRegistryService."""

    def __init__(self, db_url: str = None):
        import os
        # Use sync URL for canonical model repository (sqlite:// not sqlite+aiosqlite://)
        raw_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self.db_url = raw_url.replace("sqlite+aiosqlite://", "sqlite://")
        self._provider_registry = None
        self._session = None

    async def bootstrap(self):
        """Open canonical provider storage without creating schema."""
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import SQLEndpointBindingRepository

        _require_existing_sqlite_database(self.db_url)
        sync_factory = make_sync_session_factory(self.db_url)
        self._session = sync_factory()
        binding_repo = SQLEndpointBindingRepository(self._session)
        self._provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)

    async def shutdown(self):
        if self._session:
            self._session.close()
            self._session = None

    async def list_providers(self) -> list:
        """List configured canonical providers without inventing health state."""
        if not self._provider_registry:
            await self.bootstrap()

        from windagent_storage.repositories.v3_routing_repositories import SQLCanonicalModelRepository

        canonical_repo = SQLCanonicalModelRepository(self._session)
        models = canonical_repo.list_canonical_models()

        providers = {}
        for model in models:
            vendor = model.get("vendor", "unknown")
            if vendor not in providers:
                providers[vendor] = {
                    "provider_name": vendor,
                    "models": [],
                    "configured": True,
                    "available": False,
                    "healthy": None,
                    "authenticated": None,
                    "rate_limited": None,
                }
            providers[vendor]["models"].append(
                model.get("canonical_name", "unknown")
            )
            providers[vendor]["available"] = (
                providers[vendor]["available"] or bool(model.get("enabled"))
            )

        return [providers[name] for name in sorted(providers)]


class ToolsCommandComposer:
    """Composes services for 'tools' command using real ToolRegistry."""

    def __init__(self):
        self._tool_registry = None

    async def bootstrap(self):
        """Use the shared runtime registration factory."""
        from windagent_tools.builtin_registry import create_builtin_tool_registry

        self._tool_registry = create_builtin_tool_registry()

    async def shutdown(self):
        if self._tool_registry:
            await self._tool_registry.close()

    async def list_tools(self) -> list:
        """List tools from real ToolRegistry."""
        if not self._tool_registry:
            await self.bootstrap()

        tools = self._tool_registry.list_tools()
        result = []
        for tool in tools:
            result.append({
                "name": tool.name,
                "capability": tool.capability.value if hasattr(tool.capability, 'value') else str(tool.capability),
                "risk_level": tool.risk_level.value if hasattr(tool.risk_level, 'value') else str(tool.risk_level),
                "description": tool.description,
                "version": tool.version,
                "required_permissions": list(tool.required_permissions),
                "availability": "REGISTERED",
            })
        return result


class EvalCommandComposer:
    """Composes services for 'eval' command using real eval artifacts."""

    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = artifacts_dir
        self._eval_service = None

    async def bootstrap(self):
        """Bootstraps eval service."""
        logger.info("Eval command uses verified eval artifacts - no composition needed.")

    async def shutdown(self):
        pass

    async def run_eval(self, suite: str = "all") -> dict:
        """Read an eval artifact only after the canonical Phase 1 gate passes."""
        import json
        import subprocess
        import sys
        from pathlib import Path
        from windagent_core.config.repository_root import find_repository_root

        root = find_repository_root(Path(__file__).resolve())
        artifacts_root = Path(self.artifacts_dir)
        if not artifacts_root.is_absolute():
            artifacts_root = root / artifacts_root
        eval_path = artifacts_root / "eval" / f"{suite}_results.json"
        if not eval_path.is_file():
            return {
                "suite": suite,
                "data_source": "OFFLINE",
                "non_production": False,
                "error": "No verified eval artifact found. Run eval suite first.",
                "verdict": "EVAL UNAVAILABLE",
            }

        validator = root / "scripts" / "validate_artifact_schema.py"
        validation = subprocess.run(
            [
                sys.executable,
                str(validator),
                str(eval_path),
                "--verify-hashes",
                "--fail-on-warning",
                "--repo-root",
                str(root),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if validation.returncode != 0:
            return {
                "suite": suite,
                "data_source": "OFFLINE",
                "non_production": False,
                "error": "Eval artifact failed Phase 1 validation.",
                "validation_details": (
                    validation.stdout + validation.stderr
                )[-1000:],
                "verdict": "EVAL UNAVAILABLE",
            }

        try:
            data = json.loads(eval_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "suite": suite,
                "data_source": "OFFLINE",
                "non_production": False,
                "error": f"Eval artifact is unreadable: {exc}",
                "verdict": "EVAL UNAVAILABLE",
            }
        artifact_suite = data.get("results", {}).get("suite")
        if artifact_suite != suite:
            return {
                "suite": suite,
                "data_source": "OFFLINE",
                "non_production": False,
                "error": (
                    f"Eval suite identity mismatch: expected {suite!r}, "
                    f"artifact contains {artifact_suite!r}"
                ),
                "verdict": "EVAL UNAVAILABLE",
            }
        data["suite"] = artifact_suite
        data["data_source"] = "OFFLINE"
        data["non_production"] = False
        data["verification"] = "PHASE1_VALIDATED"
        return data


class StatusCommandComposer:
    """Composes services for 'status' command using real HealthChecker and WorkerStatusQuery."""

    def __init__(self, db_url: str = None):
        import os
        self.db_url = db_url or os.environ.get("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent.db")
        self._health_checker = None
        self._worker_status_query = None
        self._db = None

    async def bootstrap(self):
        """Compose read-only health adapters; never initialize schema/runtime."""
        import os
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.repositories.worker_status import (
            SqlWorkerHeartbeatRepository,
            SqlWorkerStatusQuery,
        )
        from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
        from windagent_tools.registry import ToolRegistry
        from windagent_plugins.registry import PluginRegistry
        from windagent_skills.registry import SkillRegistry
        from windagent_workflows.registry import WorkflowRegistry
        from windagent_observability.events.dispatcher import EventDispatcher
        from windagent_observability.health import HealthChecker, HealthProfile

        _require_existing_sqlite_database(self.db_url)
        self._db = DatabaseManager(self.db_url)

        # Initialize registries
        from windagent_storage.database.sync_factory import make_sync_session_factory
        from windagent_storage.repositories.v3_routing_repositories import (
            SQLEndpointBindingRepository,
        )
        sync_factory = make_sync_session_factory(self.db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())
        provider_registry = CanonicalModelRegistryService(binding_repository=binding_repo)
        tool_registry = ToolRegistry()
        plugin_registry = PluginRegistry()
        skill_registry = SkillRegistry()
        workflow_registry = WorkflowRegistry()
        event_dispatcher = EventDispatcher()

        # Initialize worker status query
        worker_status_query = SqlWorkerStatusQuery(
            SqlWorkerHeartbeatRepository(self._db.session_factory)
        )
        self._worker_status_query = worker_status_query

        # Determine profile from environment
        env = os.environ.get("WINDAGENT_ENV", "development")
        profile = HealthProfile(env)

        # Create HealthChecker
        self._health_checker = HealthChecker(
            db_session_factory=self._db.session_factory,
            worker_status_query=worker_status_query,
            provider_registry=provider_registry,
            tool_registry=tool_registry,
            plugin_registry=plugin_registry,
            skill_registry=skill_registry,
            workflow_registry=workflow_registry,
            event_dispatcher=event_dispatcher,
            expected_schema_head=_canonical_schema_head(),
            profile=profile,
        )

        return self._db

    async def shutdown(self, db):
        if db:
            await db.close()

    async def get_status(self) -> dict:
        """Get real system status from HealthChecker and WorkerStatusQuery."""
        if not self._health_checker:
            await self.bootstrap()

        # Check liveness
        is_alive = await self._health_checker.check_liveness()

        # Check readiness (key components)
        readiness = await self._health_checker.check_readiness()

        # Get worker status
        worker_status = await self._worker_status_query.get_status()

        from sqlalchemy import func, select
        from windagent_core.version import (
            get_architecture_generation,
            get_product_version,
        )
        from windagent_storage.orm.v2_orchestration_models import TaskRunORM

        async with self._db.session_factory() as session:
            queue_depth = (
                await session.execute(
                    select(func.count())
                    .select_from(TaskRunORM)
                    .where(TaskRunORM.state.in_(["pending", "received"]))
                )
            ).scalar_one()

        # Overall status
        overall = "ONLINE" if is_alive and readiness.overall_status.value == "UP" else "DEGRADED" if is_alive else "UNAVAILABLE"

        return {
            "api_status": overall,
            "worker_pool": {
                "active_workers": worker_status.active_workers,
                "active_leases": worker_status.active_leases,
            },
            "queue_depth": queue_depth,
            "architecture_version": get_architecture_generation(),
            "product_version": get_product_version(),
            "data_source": "LIVE",
            "non_production": False,
            "health_details": {
                "liveness": "UP" if is_alive else "DOWN",
                "readiness": readiness.overall_status.value,
                "components": {k: v.status.value for k, v in readiness.checks.items()},
            },
        }


class SocialReportCommandComposer:
    """Composes services for 'social-report' command (Phase 6)."""

    def __init__(self, config=None):
        self.config = config

    async def run_report(
        self,
        *,
        query: str,
        urls: Sequence[str],
        output_dir: str = "artifacts/social_reports",
        workspace_root: str = ".",
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        skip_model_preflight: bool = False,
        save_screenshots: bool = True,
        authenticated: bool = False,
        profile: Optional[str] = None,
    ):
        from windagent_cli.social_research_composition import (
            compose_social_research_workflow,
        )
        from windagent_workflows.social_research import (
            SocialResearchConfig,
            SocialSourceSpec,
        )

        cfg = SocialResearchConfig(
            output_dir=output_dir,
            skip_model_preflight=skip_model_preflight,
            save_screenshots=save_screenshots,
            browser_authenticated=authenticated,
            browser_profile=profile,
        )
        workflow = compose_social_research_workflow(config=cfg)
        sources = [SocialSourceSpec(url=u) for u in urls]
        return await workflow.run(
            query=query,
            sources=sources,
            workspace_root=workspace_root,
            task_id=task_id,
            session_id=session_id,
        )

    def verify_report(self, report_dir: str):
        from windagent_workflows.social_research import verify_report_integrity

        return verify_report_integrity(report_dir)


# Command registry for per-command composition
COMMAND_COMPOSERS = {
    "doctor": DoctorCommandComposer,
    "run": RunCommandComposer,
    "eval": EvalCommandComposer,
    "provider-test": ProviderTestCommandComposer,
    "worker-status": WorkerStatusCommandComposer,
    "architecture-check": ArchitectureCheckCommandComposer,
    "task-list": TaskListCommandComposer,
    "task-inspect": TaskInspectCommandComposer,
    "replay": ReplayCommandComposer,
    "providers": ProvidersCommandComposer,
    "tools": ToolsCommandComposer,
    "status": StatusCommandComposer,
    "social-report": SocialReportCommandComposer,
}
