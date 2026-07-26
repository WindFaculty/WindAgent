"""
Unit tests for Phase 12 — CLI Doctor & Operational Diagnostics.
Verifies CLI doctor health infrastructure parity, exit codes, filtering, secret masking, and remediations.
"""

from __future__ import annotations
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from windagent_observability.health.contracts import (
    HealthStatus,
    HealthProfile,
    HealthCheckResult,
    HealthDependencyBundle,
)
from windagent_observability.health.checker import HealthChecker
from windagent_cli.composition import DoctorCommandComposer
from windagent_cli.main import doctor, main


@pytest.mark.asyncio
async def test_api_cli_parity_same_dependency_bundle():
    """Verify API and CLI produce identical health status given the same dependency bundle."""
    mock_publisher = MagicMock()
    mock_publisher.is_running = True
    
    mock_worker_query = AsyncMock()
    mock_status = MagicMock()
    mock_status.available = True
    mock_status.active_workers = 1
    mock_status.active_leases = 0
    mock_worker_query.get_status.return_value = mock_status

    bundle = HealthDependencyBundle(
        outbox=mock_publisher,
        worker=mock_worker_query,
    )

    checker = HealthChecker(bundle=bundle, profile=HealthProfile.DEVELOPMENT)
    readiness_api = await checker.check_readiness()

    composer = DoctorCommandComposer(profile="development")
    composer._health_checker = HealthChecker(bundle=bundle, profile=HealthProfile.DEVELOPMENT)

    with patch.object(composer, "initialize", AsyncMock(return_value=None)):
        cli_result = await composer.run_checks()

    assert cli_result["overall_status"] == readiness_api.overall_status.value
    assert cli_result["profile"] == readiness_api.profile.value


def test_doctor_exit_code_3_on_invalid_profile(capsys):
    """CLI doctor returns exit code 3 when an invalid profile is passed."""
    exit_code = doctor(profile="invalid_profile_name")
    assert exit_code == 3
    captured = capsys.readouterr()
    assert "Invalid health profile" in captured.err


def test_doctor_exit_code_3_on_invalid_cli_flag():
    """CLI main returns exit code 3 on unknown argument."""
    exit_code = main(["doctor", "--invalid-flag"])
    assert exit_code == 3


def test_doctor_component_filtering(capsys):
    """Doctor command with --component filters output checks."""
    exit_code = doctor(json_mode=True, component="worker")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "checks" in data
    # Worker check should be included
    assert "worker" in data["checks"]
    # Unrelated checks like database shouldn't be included when filtered
    assert "database" not in data["checks"]


def test_doctor_secret_masking(capsys):
    """Doctor hides credentials/secrets in diagnostic messages."""
    res = HealthCheckResult(
        name="database",
        status=HealthStatus.DOWN,
        message="Failed connecting to postgresql://user:my_secret_pass@localhost:5432/db",
        details={"api_key": "sk-secretkey123"},
    )
    checker = HealthChecker(profile=HealthProfile.DEVELOPMENT)
    checker._attach_suggested_action_and_mask_secrets(res)

    assert "my_secret_pass" not in res.message
    assert "***" in res.message
    assert res.details["api_key"] == "***"


@pytest.mark.asyncio
async def test_doctor_remediation_provided_on_failure():
    """Doctor attaches actionable remediation instructions when component is DOWN/DEGRADED."""
    checker = HealthChecker(profile=HealthProfile.PRODUCTION)
    res = await checker._check_worker_heartbeat()
    assert res.status in (HealthStatus.DOWN, HealthStatus.DEGRADED)
    assert res.suggested_action is not None
    assert "worker process" in res.suggested_action.lower() or "python" in res.suggested_action.lower()


@pytest.mark.asyncio
async def test_doctor_detects_stopped_outbox_publisher():
    """Doctor detects when outbox publisher object exists but is not running."""
    mock_pub = MagicMock()
    mock_pub.is_running = False

    checker = HealthChecker(outbox_publisher=mock_pub, profile=HealthProfile.DEVELOPMENT)
    res = await checker._check_outbox_publisher()
    assert res.status == HealthStatus.DOWN
    assert "task is not running" in res.message
    assert res.suggested_action is not None


@pytest.mark.asyncio
async def test_doctor_detects_stale_worker():
    """Doctor detects unavailable/stale worker heartbeats."""
    mock_worker_query = AsyncMock()
    mock_status = MagicMock()
    mock_status.available = False
    mock_status.active_workers = 0
    mock_worker_query.get_status.return_value = mock_status

    checker = HealthChecker(worker_status_query=mock_worker_query, profile=HealthProfile.PRODUCTION)
    res = await checker._check_worker_heartbeat()
    assert res.status == HealthStatus.DOWN
    assert "No active workers" in res.message
