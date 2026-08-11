from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from windagent_api.services.studio_capability_provider import (
    ApiRuntimeCapabilityProvider,
)
from windagent_core.contracts.studio.capabilities import (
    REQUIRED_STORY_TASK_HANDLERS,
    RuntimeCapabilityProfile,
    WorkerRuntimeAttestation,
)
from windagent_core.contracts.workers.models import WorkerHealth, WorkerHeartbeat


class _HeartbeatRepository:
    def __init__(self, workers: list[WorkerHeartbeat]) -> None:
        self.workers = workers

    async def get_active_workers(self, stale_after_seconds: int) -> list[WorkerHeartbeat]:
        assert stale_after_seconds == 30
        return list(self.workers)


def _attestation(
    *,
    worker_id: str = "wkr-cert",
    source_sha: str = "candidate-sha",
    certification_mode: bool = True,
    fake_runtime: bool = False,
    studio_runtime: bool = True,
) -> WorkerRuntimeAttestation:
    return WorkerRuntimeAttestation(
        worker_id=worker_id,
        source_sha=source_sha,
        process_version="workspace",
        certification_mode=certification_mode,
        runtime_adapter="StudioRuntimeAdapter" if studio_runtime else "",
        completion_reconciler="StudioCompletionReconciler" if studio_runtime else "",
        completion_recovery="StudioCompletionRecovery" if studio_runtime else "",
        handler_names=sorted(REQUIRED_STORY_TASK_HANDLERS) if studio_runtime else [],
        handler_digest="handler-digest" if studio_runtime else "",
        model_port_type="RouteLockedModelPort" if studio_runtime else "",
        canonical_model="windagent/story-default" if studio_runtime else "",
        provider_route_ready=studio_runtime,
        durable_route_lock=studio_runtime,
        endpoint_binding_identities=(
            [
                {
                    "binding_id": "bind-1",
                    "endpoint_id": "endpoint-1",
                    "provider_model_id": "provider-model-1",
                }
            ]
            if studio_runtime
            else []
        ),
        fake_runtime=fake_runtime,
        capability_profile=RuntimeCapabilityProfile(
            certification_mode=certification_mode,
            fail_closed_flags=["fake_runtime"] if fake_runtime else [],
        ),
    )


def _heartbeat(
    *,
    worker_id: str = "wkr-cert",
    attestation: WorkerRuntimeAttestation | None = None,
) -> WorkerHeartbeat:
    metadata = {}
    if attestation is not None:
        metadata["studio_runtime_attestation"] = attestation.model_dump(mode="json")
    return WorkerHeartbeat(
        worker_id=worker_id,
        runtime_type="production_worker",
        health=WorkerHealth.HEALTHY,
        active_leases=0,
        last_heartbeat_at=datetime.now(timezone.utc),
        metadata=metadata,
    )


def _container(workers: list[WorkerHeartbeat]) -> SimpleNamespace:
    return SimpleNamespace(
        db=object(),
        db_url="sqlite+aiosqlite:///cert.db",
        task_submission=object(),
        worker_heartbeat_repo=_HeartbeatRepository(workers),
        orchestrator_service=SimpleNamespace(_studio_run_extension=object()),
    )


def _by_name(profile) -> dict[str, object]:
    return {capability.name: capability for capability in profile.capabilities}


def _set_certification_api(monkeypatch) -> None:
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "1")
    monkeypatch.setenv("WINDAGENT_SOURCE_SHA", "candidate-sha")
    monkeypatch.setenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "windagent/story-default")
    monkeypatch.delenv("WINDAGENT_FAKE_RUNTIME", raising=False)
    monkeypatch.delenv("WINDAGENT_MODEL_BACKEND", raising=False)


@pytest.mark.asyncio
async def test_api_env_on_worker_studio_off_is_unavailable(monkeypatch) -> None:
    _set_certification_api(monkeypatch)
    profile = await ApiRuntimeCapabilityProvider(_container([_heartbeat()])).get_capabilities()
    capabilities = _by_name(profile)

    assert capabilities["worker"].status.value == "AVAILABLE"
    assert capabilities["worker"].metadata["eligible_studio_worker_count"] == 0
    assert capabilities["story_engine"].status.value == "UNAVAILABLE"
    assert capabilities["model_route"].status.value == "UNAVAILABLE"
    assert "no_eligible_studio_worker" in profile.fail_closed_flags


@pytest.mark.asyncio
async def test_api_env_off_reflects_eligible_worker_attestation(monkeypatch) -> None:
    monkeypatch.delenv("WINDAGENT_CERTIFICATION_MODE", raising=False)
    monkeypatch.delenv("WIND_STUDIO_CERTIFICATION", raising=False)
    monkeypatch.delenv("WINDAGENT_STUDIO_RUNTIME", raising=False)
    monkeypatch.delenv("WINDAGENT_STUDIO_MODEL_ROUTE", raising=False)
    worker = _heartbeat(attestation=_attestation())

    profile = await ApiRuntimeCapabilityProvider(_container([worker])).get_capabilities()
    capabilities = _by_name(profile)

    assert profile.certification_mode is False
    assert capabilities["story_engine"].status.value == "AVAILABLE"
    assert capabilities["model_route"].status.value == "AVAILABLE"
    assert capabilities["worker"].metadata["eligible_studio_workers"][0][
        "certification_mode"
    ] is True


@pytest.mark.asyncio
async def test_stale_worker_attestation_is_unavailable(monkeypatch) -> None:
    _set_certification_api(monkeypatch)
    profile = await ApiRuntimeCapabilityProvider(_container([])).get_capabilities()
    capabilities = _by_name(profile)

    assert capabilities["worker"].status.value == "UNAVAILABLE"
    assert capabilities["story_engine"].status.value == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_generic_worker_heartbeat_is_not_a_studio_worker(monkeypatch) -> None:
    _set_certification_api(monkeypatch)
    profile = await ApiRuntimeCapabilityProvider(_container([_heartbeat()])).get_capabilities()

    worker = _by_name(profile)["worker"]
    assert worker.metadata["active_worker_count"] == 1
    assert worker.metadata["eligible_studio_worker_count"] == 0
    assert worker.metadata["rejected_workers"][0]["reason"] == "missing_studio_attestation"


@pytest.mark.asyncio
async def test_fake_worker_attestation_fails_closed(monkeypatch) -> None:
    _set_certification_api(monkeypatch)
    fake = _heartbeat(attestation=_attestation(fake_runtime=True))
    profile = await ApiRuntimeCapabilityProvider(_container([fake])).get_capabilities()

    capabilities = _by_name(profile)
    assert capabilities["story_engine"].status.value == "UNAVAILABLE"
    assert capabilities["worker"].metadata["rejected_workers"][0]["reason"] == (
        "studio_runtime_ineligible"
    )


@pytest.mark.asyncio
async def test_worker_source_sha_mismatch_blocks_certification(monkeypatch) -> None:
    _set_certification_api(monkeypatch)
    mismatched = _heartbeat(attestation=_attestation(source_sha="different-sha"))
    profile = await ApiRuntimeCapabilityProvider(_container([mismatched])).get_capabilities()

    assert _by_name(profile)["story_engine"].status.value == "UNAVAILABLE"
    assert set(profile.fail_closed_flags) >= {
        "no_eligible_studio_worker",
        "worker_source_sha_mismatch",
    }


@pytest.mark.asyncio
async def test_fresh_matching_attestation_enables_story_runtime(monkeypatch) -> None:
    _set_certification_api(monkeypatch)
    worker = _heartbeat(attestation=_attestation())
    profile = await ApiRuntimeCapabilityProvider(_container([worker])).get_capabilities()
    capabilities = _by_name(profile)

    assert capabilities["worker"].status.value == "AVAILABLE"
    assert capabilities["worker"].metadata["eligible_studio_worker_count"] == 1
    assert capabilities["model_route"].status.value == "AVAILABLE"
    assert capabilities["story_engine"].status.value == "AVAILABLE"
    assert profile.fail_closed_flags == []
