"""Provider, routing, registry, and intelligence composition for Worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.exc import OperationalError

from windagent_intelligence.pipeline import IntelligencePipeline
from windagent_providers.registry.canonical_registry import (
    CanonicalModelRegistryService,
)
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.management import RoutingPolicyProjection
from windagent_storage.database.sync_factory import make_sync_session_factory
from windagent_storage.repositories.provider_management_repository import (
    SQLProviderManagementRepository,
)
from windagent_storage.repositories.v3_repositories import SQLRouteLockRepository
from windagent_storage.repositories.v3_routing_repositories import (
    SQLEndpointBindingRepository,
    SQLProviderRoutingAuditRepository,
)
from windagent_tools.registry import ToolRegistry
from windagent_workflows.registry import WorkflowRegistry


@dataclass(frozen=True)
class ProviderBundle:
    sync_factory: Callable[[], Any]
    binding_repo: Any
    audit_repo: Any
    lock_repo: Any
    provider_management_repo: SQLProviderManagementRepository
    provider_registry: CanonicalModelRegistryService
    tool_registry: ToolRegistry
    workflow_registry: WorkflowRegistry
    intelligence_pipeline: IntelligencePipeline
    route_lock_service: RouteLockService


class ProviderComposer:
    """Compose durable provider projection and route-lock dependencies."""

    @staticmethod
    def compose(db_url: str) -> ProviderBundle:
        sync_factory = make_sync_session_factory(db_url)
        binding_repo = SQLEndpointBindingRepository(sync_factory())
        audit_repo = SQLProviderRoutingAuditRepository(sync_factory())
        lock_repo = SQLRouteLockRepository(sync_factory())
        provider_management_repo = SQLProviderManagementRepository(sync_factory())
        try:
            ruleset = RoutingPolicyProjection(provider_management_repo).load_ruleset()
        except OperationalError:
            # The legacy in-memory bootstrap uses separate async and sync
            # SQLite connections, so the sync projection cannot see the async
            # schema. Preserve its dev/test-only empty ruleset behavior while
            # keeping every file-backed/production database fail-fast.
            if ":memory:" not in db_url.lower():
                raise
            from windagent_providers.routing.rules import RoutingRuleSet

            ruleset = RoutingRuleSet()
        provider_registry = CanonicalModelRegistryService(
            binding_repository=binding_repo
        )
        tool_registry = ToolRegistry()
        workflow_registry = WorkflowRegistry()
        return ProviderBundle(
            sync_factory=sync_factory,
            binding_repo=binding_repo,
            audit_repo=audit_repo,
            lock_repo=lock_repo,
            provider_management_repo=provider_management_repo,
            provider_registry=provider_registry,
            tool_registry=tool_registry,
            workflow_registry=workflow_registry,
            intelligence_pipeline=IntelligencePipeline(
                provider_registry=provider_registry,
                tool_registry=tool_registry,
            ),
            route_lock_service=RouteLockService(
                ruleset=ruleset,
                lock_repository=lock_repo,
                audit_repository=audit_repo,
            ),
        )


__all__ = ["ProviderBundle", "ProviderComposer"]
