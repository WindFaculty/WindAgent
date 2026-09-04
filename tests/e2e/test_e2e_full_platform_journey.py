"""E2E Test: Full User Platform Journey tying all bounded contexts together."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from windagent.kernel.time import SystemClock

# Agent Runtime
from windagent.modules.agent_runtime.application.runtime import (
    AgentRuntimeContainer,
    AgentRuntimeServices,
)
from windagent.modules.agent_runtime.infrastructure.memory import (
    InMemoryAgentRuntimeStore,
)
from windagent.modules.agent_runtime.infrastructure.memory import (
    memory_scope_factory as agent_scope_factory,
)

# Live Record
from windagent.modules.live_record.application.runtime import LiveRecordServices
from windagent.modules.live_record.application.runtime import container_for as live_record_container
from windagent.modules.live_record.infrastructure.memory import (
    InMemoryLiveRecordStore,
)
from windagent.modules.live_record.infrastructure.memory import (
    memory_scope_factory as live_record_scope_factory,
)

# Model Gateway
from windagent.modules.model_gateway.application.models import (
    BindingRow,
    CanonicalModelRow,
    EndpointRow,
    ProviderRow,
    RuleRow,
)
from windagent.modules.model_gateway.application.runtime import (
    ModelGatewayServices,
)
from windagent.modules.model_gateway.application.runtime import (
    container_for as model_gw_container,
)
from windagent.modules.model_gateway.domain.rules import RuleMatchContext
from windagent.modules.model_gateway.infrastructure.memory import (
    InMemoryModelGatewayStore,
)
from windagent.modules.model_gateway.infrastructure.memory import (
    memory_scope_factory as gw_scope_factory,
)
from windagent.modules.model_gateway.providers.contracts import (
    DiscoveredModel,
    HealthReport,
    ProviderAdapter,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)

# Production
from windagent.modules.production.application.runtime import ProductionContainer, ProductionServices
from windagent.modules.production.infrastructure.memory import (
    InMemoryProductionStore,
)
from windagent.modules.production.infrastructure.memory import (
    memory_scope_factory as prod_scope_factory,
)

# Quality
from windagent.modules.quality.application.commands import (
    CreateEvaluationDataset,
    FinalizeEvaluationRun,
    RecordEvaluationMetric,
    StartEvaluationRun,
)
from windagent.modules.quality.application.services import QualityService
from windagent.modules.quality.infrastructure.memory import (
    InMemoryQualityStore,
)
from windagent.modules.quality.infrastructure.memory import (
    InMemoryTransactionScope as QualityTxScope,
)

# Studio
from windagent.modules.studio.application.runtime import StudioContainer, StudioServices
from windagent.modules.studio.infrastructure.memory import (
    InMemoryStudioStore,
)
from windagent.modules.studio.infrastructure.memory import (
    memory_scope_factory as studio_scope_factory,
)

# Workspace
from windagent.modules.workspace.application.commands import CreateWorkspace
from windagent.modules.workspace.application.services import WorkspaceService
from windagent.modules.workspace.infrastructure.memory import (
    InMemoryTransactionScope as WorkspaceTxScope,
)
from windagent.modules.workspace.infrastructure.memory import (
    InMemoryWorkspaceStore,
)
from windagent.platform.security import InMemorySecretStore


class E2EPlatformFakeAdapter:
    provider_name = "openai"

    async def generate(self, request: ProviderRequest, model_id: str) -> ProviderResponse:
        return ProviderResponse(
            provider_model_id=model_id,
            text="Platform generated script response.",
            usage=ProviderUsage(prompt_tokens=50, completion_tokens=50),
        )

    async def list_models(self) -> tuple[DiscoveredModel, ...]:
        return (DiscoveredModel(id="gpt-4o"),)

    async def health(self) -> HealthReport:
        return HealthReport(provider_name=self.provider_name, healthy=True)


class E2EPlatformAdapterFactory:
    def __init__(self, adapter: E2EPlatformFakeAdapter) -> None:
        self.adapter = adapter

    def resolve(self, protocol_mode: str, *, base_url: str, api_key: str | None, timeout_seconds: float | None = None) -> ProviderAdapter:
        return cast("ProviderAdapter", self.adapter)


@pytest.mark.asyncio
async def test_e2e_full_platform_journey(tmp_path: Path) -> None:
    clock = SystemClock()

    # 1. Multi-tenant Workspace Setup
    ws_store = InMemoryWorkspaceStore()
    ws_svc = WorkspaceService(transaction_factory=lambda: WorkspaceTxScope(ws_store))
    ws_view = await ws_svc.create_workspace(
        CreateWorkspace(
            name="Global Media Lab",
            slug="global-media-lab",
            root_path=str(tmp_path),
            owner_id="usr-ceo",
        )
    )
    assert ws_view.name == "Global Media Lab"

    # 2. Model Gateway Routing Authority
    gw_store = InMemoryModelGatewayStore()
    adapter = E2EPlatformFakeAdapter()
    gw_services = ModelGatewayServices(
        scope_factory=gw_scope_factory(gw_store),
        secrets=InMemorySecretStore(),
        adapter_factory=E2EPlatformAdapterFactory(adapter),
    )
    gw_container = model_gw_container(gw_services)
    gw_store.providers["pv-openai"] = ProviderRow(
        id="pv-openai",
        name="openai",
        display_name="OpenAI Gateway",
        vendor_type="cloud",
        base_url="https://api.openai.com/v1",
        protocol_mode="openai",
    )
    gw_store.provider_by_name["openai"] = "pv-openai"
    gw_store.models["gpt-4o"] = CanonicalModelRow(
        canonical_name="gpt-4o",
        vendor="openai",
        family="video_scripting",
        context_window=128000,
    )
    gw_store.endpoints["ep-gpt4o"] = EndpointRow(
        id="ep-gpt4o",
        provider_id="pv-openai",
        base_url="https://api.openai.com/v1",
        protocol_mode="openai",
        enabled=True,
    )
    gw_store.bindings["bind-gpt4o"] = BindingRow(
        id="bind-gpt4o",
        endpoint_id="ep-gpt4o",
        canonical_model_id="gpt-4o",
        provider_model_id="gpt-4o",
    )
    gw_store.rules["rule-prod-1"] = RuleRow(
        rule_id="rule-prod-1",
        rule_version=1,
        canonical_model_id="gpt-4o",
        task_labels=("video_scripting",),
        priority=100,
        enabled=True,
    )

    lock = await gw_container.locks.resolve_or_create_lock(
        RuleMatchContext(scope_type="session", scope_id="sess-full-1", task_labels=("video_scripting",))
    )
    assert lock.canonical_model_id == "gpt-4o"

    # 3. Agent Runtime Session Initialization
    agent_store = InMemoryAgentRuntimeStore()
    agent_container = AgentRuntimeContainer(
        AgentRuntimeServices(scope_factory=agent_scope_factory(agent_store), clock=clock)
    )
    sess_view = await agent_container.agent_runtime.create_session(
        actor_id="user-producer",
        title="Full Pipeline Production Run",
    )
    assert sess_view is not None
    assert sess_view.session_id is not None

    # 4. Studio Creative Generation
    studio_store = InMemoryStudioStore()
    studio_container = StudioContainer(StudioServices(scope_factory=studio_scope_factory(studio_store), clock=clock))
    studio_proj = await studio_container.studio.create_project(
        title="Neo Tokyo Chronology",
        description="The complete cyberpunk story",
    )
    assert studio_proj.title == "Neo Tokyo Chronology"

    # 5. Production Video Timeline Master
    prod_store = InMemoryProductionStore()
    prod_container = ProductionContainer(ProductionServices(scope_factory=prod_scope_factory(prod_store), clock=clock))
    prod_proj = await prod_container.production.create_project(
        title="Chronology Master 4K",
        description="Master 4K video timeline",
    )
    assert prod_proj.title == "Chronology Master 4K"

    # 6. Live Record Studio Plan
    rec_store = InMemoryLiveRecordStore()
    rec_container = live_record_container(LiveRecordServices(scope_factory=live_record_scope_factory(rec_store), clock=clock))
    rec_plan = await rec_container.live_record.create_plan(
        episode_id="ep-full-1",
        episode_revision_id="rev-full-1",
    )
    assert rec_plan is not None

    # 7. Quality Certification Benchmark
    qual_store = InMemoryQualityStore()
    qual_svc = QualityService(transaction_factory=lambda: QualityTxScope(qual_store))
    qual_ds = await qual_svc.create_dataset(
        CreateEvaluationDataset(
            name="Milestone 4 Platform Parity",
            domain="Full Integration",
            description="All 9 contexts green",
        )
    )
    assert qual_ds.name == "Milestone 4 Platform Parity"

    run_view = await qual_svc.start_evaluation_run(
        StartEvaluationRun(execution_id="exec-full-1", dataset_id=qual_ds.dataset_id)
    )
    metric_view = await qual_svc.record_metric(
        RecordEvaluationMetric(
            run_id=run_view.run_id,
            dimension="full_integration",
            metric_name="cross_module_flow",
            score=1.0,
            threshold=0.8,
            confidence=1.0,
            evidence_refs=("evidence://m4/cert_run_001.json",),
        )
    )
    assert metric_view.passed is True

    final_run = await qual_svc.finalize_evaluation_run(
        FinalizeEvaluationRun(run_id=run_view.run_id)
    )
    assert final_run.status == "COMPLETED"
    assert final_run.passed is True
