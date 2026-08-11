from __future__ import annotations

from types import SimpleNamespace

import pytest

from windagent_api.services.studio_capability_provider import (
    ApiRuntimeCapabilityProvider,
)


class _Registry:
    is_durable = True

    def __init__(self, bindings: list[object]) -> None:
        self.bindings = bindings

    def get_exact_equivalent_endpoints(self, canonical_model_id: str) -> list[object]:
        assert canonical_model_id == "windagent/story-default"
        return list(self.bindings)


class _WorkerStatus:
    def __init__(self, *, available: bool) -> None:
        self.available = available
        self.active_workers = 1 if available else 0
        self.active_leases = 0


class _WorkerQuery:
    def __init__(self, *, available: bool) -> None:
        self.available = available

    async def get_status(self, *, stale_after_seconds: int) -> _WorkerStatus:
        assert stale_after_seconds == 30
        return _WorkerStatus(available=self.available)


def _container(*, worker_available: bool, bindings: list[object]) -> SimpleNamespace:
    return SimpleNamespace(
        db=object(),
        db_url="sqlite+aiosqlite:///cert.db",
        task_submission=object(),
        worker_status_query=_WorkerQuery(available=worker_available),
        provider_registry=_Registry(bindings),
        orchestrator_service=SimpleNamespace(_studio_run_extension=object()),
    )


def _by_name(profile) -> dict[str, object]:
    return {capability.name: capability for capability in profile.capabilities}


@pytest.mark.asyncio
async def test_certification_capability_recovers_from_worker_heartbeat(monkeypatch) -> None:
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "windagent/story-default")
    monkeypatch.delenv("WINDAGENT_FAKE_RUNTIME", raising=False)
    monkeypatch.delenv("WINDAGENT_MODEL_BACKEND", raising=False)

    down = await ApiRuntimeCapabilityProvider(
        _container(worker_available=False, bindings=[object()])
    ).get_capabilities()
    down_caps = _by_name(down)
    assert down_caps["model_route"].status.value == "AVAILABLE"
    assert down_caps["worker"].status.value == "UNAVAILABLE"
    assert down_caps["story_engine"].status.value == "UNAVAILABLE"

    recovered = await ApiRuntimeCapabilityProvider(
        _container(worker_available=True, bindings=[object()])
    ).get_capabilities()
    recovered_caps = _by_name(recovered)
    assert recovered_caps["worker"].status.value == "AVAILABLE"
    assert recovered_caps["model_route"].status.value == "AVAILABLE"
    assert recovered_caps["story_engine"].status.value == "AVAILABLE"
    assert recovered.fail_closed_flags == []


@pytest.mark.asyncio
async def test_missing_real_binding_keeps_story_engine_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "windagent/story-default")

    profile = await ApiRuntimeCapabilityProvider(
        _container(worker_available=True, bindings=[])
    ).get_capabilities()
    capabilities = _by_name(profile)
    assert capabilities["model_route"].status.value == "UNAVAILABLE"
    assert capabilities["story_engine"].status.value == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_certification_reports_unsafe_runtime_flags(monkeypatch) -> None:
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "0")
    monkeypatch.setenv("WINDAGENT_STUDIO_CANONICAL_MODEL", "windagent/story-default")
    monkeypatch.setenv("WINDAGENT_FAKE_RUNTIME", "true")
    monkeypatch.setenv("WINDAGENT_MODEL_BACKEND", "mock")

    profile = await ApiRuntimeCapabilityProvider(
        _container(worker_available=True, bindings=[object()])
    ).get_capabilities()
    capabilities = _by_name(profile)
    assert capabilities["model_route"].status.value == "UNAVAILABLE"
    assert capabilities["story_engine"].status.value == "UNAVAILABLE"
    assert set(profile.fail_closed_flags) == {
        "fake_runtime_active",
        "non_real_model_backend_active",
        "studio_model_route_disabled",
    }
