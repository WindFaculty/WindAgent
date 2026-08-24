"""
Automated tests for WindAgent Architecture V2 Phase 1:
- Workspace package importability
- API V2 skeleton endpoints
- Worker V2 skeleton lifecycle
- CLI V2 doctor and architecture checks
- Scaffold generator idempotency
- Import boundary enforcement
"""

import importlib
import pytest
from httpx import AsyncClient, ASGITransport

from windagent_api.main import app
from windagent_worker.runner import WorkerRunner
from windagent_cli.main import doctor, architecture_check

WORKSPACE_PACKAGES = [
    "windagent_core",
    "windagent_orchestration",
    "windagent_intelligence",
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_verification",
    "windagent_context",
    "windagent_memory",
    "windagent_execution",
    "windagent_storage",
    "windagent_observability",
    "windagent_evals",
    "windagent_api",
    "windagent_cli",
    "windagent_worker",
]


@pytest.mark.parametrize("pkg_name", WORKSPACE_PACKAGES)
def test_workspace_package_importable(pkg_name: str):
    module = importlib.import_module(pkg_name)
    assert module is not None
    assert hasattr(module, "__version__")


@pytest.mark.asyncio
async def test_api_v2_skeleton_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_live = await client.get("/health/live")
        assert res_live.status_code == 200
        assert res_live.json() == {"status": "live", "service": "windagent-api"}

        res_ready = await client.get("/health/ready")
        assert res_ready.status_code == 503
        assert res_ready.json()["status"] == "DOWN"
        assert res_ready.json()["checks"]["worker"]["status"] != "UP"
        res_arch = await client.get("/internal/architecture")
        assert res_arch.status_code == 200
        data = res_arch.json()
        assert data["architecture"] in ("V2", "V3")
        assert data["status"] in ("scaffold", "canonical_api_v2_production", "canonical_api_v3_production")


@pytest.mark.asyncio
async def test_worker_v2_skeleton_lifecycle():
    worker = WorkerRunner(name="test-worker")
    assert not worker.is_running
    assert not worker.is_ready

    await worker.start()
    assert worker.is_running
    assert worker.is_ready

    tick_res = await worker.noop_consumer_tick()
    assert tick_res == {"status": "ok", "processed": 0}

    await worker.cancel()
    await worker.stop()
    assert not worker.is_running
    assert not worker.is_ready


def test_cli_v2_skeleton_doctor(monkeypatch):
    """The scaffold-exposed doctor entry runs and maps its verdict onto the
    documented exit-code domain. The real verdict is machine-dependent (the
    composer migrates the default DB first), so the composer is scripted."""
    class _ScriptedComposer:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run_checks_sync(self) -> dict:
            return {
                "overall_status": "DOWN",
                "profile": "development",
                "checks": {"database": {"passed": False, "details": "scripted"}},
            }

    import sys

    cli_main = sys.modules["windagent_cli.main"]
    monkeypatch.setattr(cli_main, "DoctorCommandComposer", _ScriptedComposer)
    exit_code = doctor()
    assert exit_code == 2


def test_cli_v2_skeleton_architecture_check():
    exit_code = architecture_check()
    assert exit_code == 0
