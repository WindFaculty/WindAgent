"""Provider/routing composer for the API composition root (Phase 7).

Constructs the provider registry, tool/plugin/skill/workflow registries, the
route-lock service, the provider execution coordinator, and the routing
authority bridge.  No execution runtime or worktree authority is composed here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_providers.routing.route_lock_service import RouteLockService
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
from windagent_providers.routing.endpoint_adapter_resolver import EndpointAdapterResolver
from windagent_providers.routing.execution_coordinator import EndpointExecutionCoordinator
from windagent_providers.management import (
    ProviderAdapterFactory,
    ProviderManagementService,
    ProviderProbeService,
    RoutingPolicyProjection,
)
from windagent_tools.registry import ToolRegistry
from windagent_plugins.registry import PluginRegistry
from windagent_skills.registry import SkillRegistry
from windagent_workflows.registry import WorkflowRegistry
from windagent_storage.security.encryption import decrypt
from windagent_api.services.routing_authority_bridge import RoutingAuthorityBridge
from windagent_api.composition.repositories import RepositoryBundle


@dataclass
class ProviderBundle:
    """Typed result of the provider composer."""

    provider_registry: CanonicalModelRegistryService
    tool_registry: ToolRegistry
    plugin_registry: PluginRegistry
    skill_registry: SkillRegistry
    workflow_registry: WorkflowRegistry
    route_lock_service: RouteLockService
    provider_execution_coordinator: EndpointExecutionCoordinator
    provider_management_service: ProviderManagementService
    provider_probe_service: ProviderProbeService
    routing_policy_projection: RoutingPolicyProjection


class ProviderComposer:
    """Constructs the provider/routing services for the API process."""

    def compose(
        self,
        repositories: RepositoryBundle,
        release_telemetry: Any,
    ) -> ProviderBundle:
        provider_registry = CanonicalModelRegistryService(
            binding_repository=repositories.binding_repo
        )
        tool_registry = ToolRegistry()
        plugin_registry = PluginRegistry()
        skill_registry = SkillRegistry()
        workflow_registry = WorkflowRegistry()

        default_model = os.getenv(
            "WINDAGENT_ORCHESTRATOR_CANONICAL_MODEL", "windagent/local-agent"
        )
        route_lock_service = RouteLockService(
            ruleset=RoutingRuleSet(
                rules=[
                    RoutingRule(
                        rule_id="orchestrator-local-agent",
                        rule_version=1,
                        canonical_model_id=default_model,
                        description="Phase-2 conversation control plane",
                    )
                ]
            ),
            lock_repository=repositories.lock_repo,
            audit_repository=repositories.audit_repo,
        )
        provider_execution_coordinator = EndpointExecutionCoordinator(
            adapter_resolver=EndpointAdapterResolver(decrypt),
            endpoint_registry=repositories.endpoint_registry,
            endpoint_state=repositories.endpoint_state,
            quota_state=repositories.quota_state,
            attempt_log=repositories.attempt_log,
            release_telemetry=release_telemetry,
        )
        # Phase 10: provider-management infrastructure. The adapter factory is
        # injectable so tests can drive the real adapter path with a controlled
        # local/mock HTTP transport; production passes None (real clients).
        provider_management_service = ProviderManagementService(
            repositories.provider_management_repo
        )
        provider_probe_service = ProviderProbeService(
            adapter_factory=ProviderAdapterFactory(decrypt),
            repository=repositories.provider_management_repo,
        )
        routing_policy_projection = RoutingPolicyProjection(
            repositories.provider_management_repo
        )
        return ProviderBundle(
            provider_registry=provider_registry,
            tool_registry=tool_registry,
            plugin_registry=plugin_registry,
            skill_registry=skill_registry,
            workflow_registry=workflow_registry,
            route_lock_service=route_lock_service,
            provider_execution_coordinator=provider_execution_coordinator,
            provider_management_service=provider_management_service,
            provider_probe_service=provider_probe_service,
            routing_policy_projection=routing_policy_projection,
        )

    @staticmethod
    def compose_routing_bridge(
        resource_service: Any,
        route_lock_service: RouteLockService,
    ) -> RoutingAuthorityBridge:
        """Wire the durable routing-rules authority onto the runtime ruleset."""
        return RoutingAuthorityBridge(
            resource_service=resource_service,
            route_lock_service=route_lock_service,
        )


__all__ = ["ProviderBundle", "ProviderComposer"]