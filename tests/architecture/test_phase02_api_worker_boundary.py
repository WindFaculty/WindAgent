"""Phase 2 API/Worker process-boundary gates."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from windagent_core.contracts.workers import WorkerHealth, WorkerHeartbeat
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.repositories.worker_status import (
    SqlWorkerHeartbeatRepository,
    SqlWorkerStatusQuery,
)
from windagent_api.health import health_readiness


ROOT = Path(__file__).parents[2]
API_ROOT = ROOT / "apps" / "api"


WORKER_ROOT = ROOT / "apps" / "worker"


def test_api_has_no_worker_import_or_declared_dependency():
    violations = []
    for path in (API_ROOT / "windagent_api").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(alias.name for alias in node.names if alias.name.startswith("windagent_worker"))
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("windagent_worker"):
                violations.append(node.module)
    assert not violations
    assert "windagent-worker" not in (API_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_worker_has_no_api_import_or_declared_dependency():
    violations = []
    for path in (WORKER_ROOT / "windagent_worker").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(alias.name for alias in node.names if alias.name.startswith("windagent_api"))
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("windagent_api"):
                violations.append(node.module)
    assert not violations
    assert "windagent-api" not in (WORKER_ROOT / "pyproject.toml").read_text(encoding="utf-8")



def test_api_import_succeeds_when_worker_import_is_blocked(monkeypatch):
    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("windagent_worker"):
            raise AssertionError("API attempted to import Worker package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    import windagent_api.main  # noqa: F401


@pytest.mark.asyncio
async def test_worker_status_uses_durable_non_stale_heartbeats():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    repository = SqlWorkerHeartbeatRepository(db.session_factory)
    query = SqlWorkerStatusQuery(repository)

    await repository.record_heartbeat(
        WorkerHeartbeat(
            worker_id="fresh-worker",
            runtime_type="worker",
            health=WorkerHealth.HEALTHY,
            active_leases=2,
            last_heartbeat_at=datetime.now(timezone.utc),
        )
    )
    await repository.record_heartbeat(
        WorkerHeartbeat(
            worker_id="stale-worker",
            runtime_type="worker",
            health=WorkerHealth.HEALTHY,
            active_leases=9,
            last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
    )

    status = await query.get_status(stale_after_seconds=30)
    assert status.available is True
    assert status.active_workers == 1
    assert status.active_leases == 2
    assert status.workers[0].worker_id == "fresh-worker"
    await db.close()


@pytest.mark.asyncio
async def test_no_heartbeat_means_worker_unavailable():
    db = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db.create_tables(BaseORM.metadata)
    status = await SqlWorkerStatusQuery(
        SqlWorkerHeartbeatRepository(db.session_factory)
    ).get_status()
    assert status.available is False
    assert status.active_workers == 0
    await db.close()


@pytest.mark.asyncio
async def test_production_readiness_fails_when_worker_unavailable():
    class UnavailableQuery:
        async def get_status(self, stale_after_seconds=30):
            from windagent_core.contracts.workers import WorkerStatus

            return WorkerStatus(available=False, active_workers=0, active_leases=0)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                container=SimpleNamespace(
                    db=None,
                    worker_status_query=UnavailableQuery(),
                    provider_registry=object(),
                ),
                db=None,
                bootstrap_config=SimpleNamespace(env="production"),
            )
        )
    )
    res = await health_readiness(request)
    assert getattr(res, "status_code", None) == 503
