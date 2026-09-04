"""API tests for the /api/v4/quality HTTP endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import windagent.modules.quality.infrastructure.tables  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from windagent.modules.quality.manifest import build_quality_manifest
from windagent.platform.configuration.settings import Settings
from windagent.platform.persistence import metadata
from windagent_api.app import create_app

QUALITY_URL = "/api/v4/quality"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def quality_client(tmp_path: Path) -> TestClient:
    db_path = (tmp_path / "qual_test.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    _run(_create())

    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_quality_manifest_structure() -> None:
    manifest = build_quality_manifest()
    assert manifest.id == "quality"
    assert manifest.version == "1.0.0"
    assert len(manifest.commands) == 8
    assert len(manifest.queries) == 10
    assert len(manifest.jobs) == 4
    assert "evals" in manifest.capabilities
    assert "verification" in manifest.capabilities
    assert "graders" in manifest.capabilities
    assert "regression" in manifest.capabilities


def test_quality_api_flow(quality_client: TestClient) -> None:
    # 1. Create dataset
    ds_payload = {
        "name": "Integration Quality Benchmark",
        "domain": "agent_runtime",
        "description": "API test dataset",
    }
    ds_resp = quality_client.post(f"{QUALITY_URL}/datasets", json=ds_payload)
    assert ds_resp.status_code == 201, ds_resp.text
    ds_id = ds_resp.json()["dataset_id"]

    # 2. Add test case
    case_payload = {
        "name": "tool_execution_case",
        "input_payload": {"tool": "calculator", "args": {"expr": "2+2"}, "output": "4"},
        "expected_output": {"output": "4"},
        "dimension": "tool_correctness",
    }
    tc_resp = quality_client.post(f"{QUALITY_URL}/datasets/{ds_id}/cases", json=case_payload)
    assert tc_resp.status_code == 201
    assert tc_resp.json()["dimension"] == "tool_correctness"

    # 3. Start evaluation run
    run_resp = quality_client.post(
        f"{QUALITY_URL}/evaluations/runs",
        json={"execution_id": "exec_api_1", "dataset_id": ds_id},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["run_id"]

    # 4. Record metric
    m_resp = quality_client.post(
        f"{QUALITY_URL}/evaluations/runs/{run_id}/metrics",
        json={
            "dimension": "task_success",
            "metric_name": "task_success_rate",
            "score": 0.92,
            "evidence_refs": ["artifact://task_res.json"],
        },
    )
    assert m_resp.status_code == 201
    assert m_resp.json()["passed"] is True

    # 5. Finalize run
    fin_resp = quality_client.post(f"{QUALITY_URL}/evaluations/runs/{run_id}/finalize")
    assert fin_resp.status_code == 200
    assert fin_resp.json()["status"] == "COMPLETED"

    # 6. Get run
    get_run = quality_client.get(f"{QUALITY_URL}/evaluations/runs/{run_id}")
    assert get_run.status_code == 200
    assert get_run.json()["composite_score"] == 0.92

    # 7. Verification suite
    ver_resp = quality_client.post(
        f"{QUALITY_URL}/verification/suites/run",
        json={
            "suite_id": "api_suite",
            "target_id": "target_1",
            "gate_checks": [
                {
                    "gate_name": "security_scan",
                    "gate_type": "SECURITY_SCAN",
                    "command": "scan_secrets",
                    "exit_code": 0,
                }
            ],
        },
    )
    assert ver_resp.status_code == 201
    rep_id = ver_resp.json()["report_id"]

    get_rep = quality_client.get(f"{QUALITY_URL}/verification/reports/{rep_id}")
    assert get_rep.status_code == 200

    # 8. Baseline comparison
    comp_resp = quality_client.post(
        f"{QUALITY_URL}/baselines/compare",
        json={
            "candidate_id": "cand_v2",
            "baseline_id": "base_v1",
            "candidate_metrics": {"accuracy": ["task_success", 0.95]},
            "baseline_metrics": {"accuracy": ["task_success", 0.90]},
        },
    )
    assert comp_resp.status_code == 201
    assert comp_resp.json()["passed"] is True

    # 9. Summary
    sum_resp = quality_client.get(f"{QUALITY_URL}/summary")
    assert sum_resp.status_code == 200
    assert sum_resp.json()["total_evaluations"] >= 1
