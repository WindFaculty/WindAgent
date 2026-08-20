"""Phase 3 acceptance: a conversation turn uses same-model provider failover."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from windagent_core.contracts.execution import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionResult,
    ExecutionRuntimePort,
    RuntimeStatus,
    RuntimeStatusEnum,
)
from windagent_core.contracts.providers.responses import ProviderResponse, ProviderUsage
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_orchestration.orchestrator_service import OrchestratorService, Subtask
from windagent_providers.base.errors import RateLimitFailure
from windagent_providers.routing.circuit_breaker import InMemoryEndpointStateManager
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.routing.memory_ports import (
    InMemoryEndpointRegistry,
    InMemoryQuotaStateManager,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.database.sync_factory import make_sync_session_factory
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from tests.fakes.provider_graph_seed import PersistentRouteLocks, seed_provider_graph
from windagent_storage.repositories.v3_repositories import SQLRouteAttemptRepository


class HoldingRuntime(ExecutionRuntimePort):
    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        return ExecutionHandle(
            handle_id=f"handle-{uuid.uuid4().hex}",
            runtime_run_id=f"runtime-{uuid.uuid4().hex}",
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=request.workflow_run_id,
        )

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        return RuntimeStatus(handle_id=handle.handle_id, status=RuntimeStatusEnum.RUNNING)

    async def cancel(self, handle: ExecutionHandle) -> None:
        return None

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        return ExecutionResult(handle_id=handle.handle_id, step_run_id=handle.step_run_id, status=RuntimeStatusEnum.RUNNING)

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        return None


class RateLimitedAdapter:
    async def generate(self, *_: Any, **__: Any) -> ProviderResponse:
        raise RateLimitFailure("provider A is rate limited", provider_id="provider-a", status_code=429)


class SuccessfulAdapter:
    async def generate(self, *_: Any, **__: Any) -> ProviderResponse:
        return ProviderResponse(
            canonical_model_id="wrong-unlocked-value",
            provider_model_id="model-exact-revision",
            endpoint_id="provider-b-endpoint",
            text="answer from provider B",
            usage=ProviderUsage(prompt_tokens=5, completion_tokens=3),
        )


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase3.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_turn_429_failover_is_same_model_and_auditable(db: DatabaseManager):
    canonical_model_id = "phase3/model@2026-08-03"
    bindings = [
        {
            "endpoint_id": "provider-a-endpoint",
            "binding_id": "binding-provider-a",
            "canonical_model_id": canonical_model_id,
            "provider_model_id": "model-exact-revision",
            "provider_name": "provider-a",
            "base_url": "https://provider-a.invalid/v1",
            "credential_ciphertext": "test-key-a",
            "equivalence_level": "exact_revision",
            "is_active": True,
        },
        {
            "endpoint_id": "provider-b-endpoint",
            "binding_id": "binding-provider-b",
            "canonical_model_id": canonical_model_id,
            "provider_model_id": "model-exact-revision",
            "provider_name": "provider-b",
            "base_url": "https://provider-b.invalid/v1",
            "credential_ciphertext": "test-key-b",
            "equivalence_level": "exact_revision",
            "is_active": True,
        },
    ]
    # GAP A: FK enforcement requires the provider reference graph to exist and
    # the route lock to be persisted into route_locks_v3 (as production
    # RouteLockService + SQLRouteLockRepository do).
    sync_session = make_sync_session_factory(db.db_url)()
    seed_provider_graph(sync_session, canonical_model_id=canonical_model_id, bindings=bindings)

    endpoint_state = InMemoryEndpointStateManager()
    coordinator = EndpointExecutionCoordinator(
        adapter_resolver=lambda candidate: RateLimitedAdapter()
        if candidate.endpoint_id == "provider-a-endpoint"
        else SuccessfulAdapter(),
        endpoint_registry=InMemoryEndpointRegistry(bindings),
        endpoint_state=endpoint_state,
        quota_state=InMemoryQuotaStateManager(),
        attempt_log=SQLRouteAttemptRepository(
            make_sync_session_factory(db.db_url)()
        ),
    )
    runtime = HoldingRuntime()
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("local_agent", runtime)
    service = OrchestratorService(
        db.session_factory,
        registry,
        PersistentRouteLocks(
            make_sync_session_factory(db.db_url),
            canonical_model_id=canonical_model_id,
            rule_id="phase3-test-rule",
            rule_version=7,
            reason="phase3 routed turns",
        ),
        coordinator,
        repo_factory=lambda session: MultiAgentRepository(session),
    )

    goal = await service.submit_goal(
        conversation_id="conversation-phase3",
        objective="Execute a routed provider turn",
        subtasks=(Subtask(objective="Answer the user", node_id="answer"),),
    )
    agent = goal.agents[0]
    result = await service.execute_provider_turn(
        conversation_id=goal.conversation_id,
        agent_instance_id=agent.agent_instance_id,
        prompt="hello",
    )

    assert result.text == "answer from provider B"
    assert result.canonical_model_id == canonical_model_id
    assert result.routing_snapshot["binding"] == {
        "provider_binding_id": "binding-provider-b",
        "endpoint_id": "provider-b-endpoint",
        "provider_model_id": "model-exact-revision",
    }
    assert (await endpoint_state.is_available("provider-a-endpoint")) is False

    # The read-only audit backing the dashboard exposes the immutable turn
    # snapshot and exactly the two provider attempts, with no credentials.
    audit = await service.routing_turn_detail(goal.conversation_id, result.turn_id)
    assert audit is not None
    assert audit["canonical_model_id"] == canonical_model_id
    assert audit["routing_snapshot"]["lock_id"] == result.route_lock_id
    assert audit["routing_snapshot"]["binding"]["provider_binding_id"] == "binding-provider-b"
    assert [(item["status"], item["provider_binding_id"]) for item in audit["attempts"]] == [
        ("rate_limited", "binding-provider-a"),
        ("success", "binding-provider-b"),
    ]

    async with db.session_factory() as session:
        assert (await session.execute(text("SELECT COUNT(*) FROM agent_turns"))).scalar_one() == 1
        assert (await session.execute(text("SELECT COUNT(*) FROM route_attempts_v3"))).scalar_one() == 2
