"""Phase 6 — Tests for agent capability registry and delegation service."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from schemas.agent_routing import AgentRole, DelegationRequest
from services.agent_capability_registry import AgentCapabilityRegistry
from services.agent_delegation_service import (
    AgentDelegationService,
    MAX_DELEGATION_DEPTH,
)


# ---------------------------------------------------------------------------
# Registry Tests
# ---------------------------------------------------------------------------


class TestAgentCapabilityRegistry:
    def setup_method(self):
        self.registry = AgentCapabilityRegistry()

    def test_all_roles_present(self):
        roles = self.registry.all_roles()
        assert "Planner" in roles
        assert "Coder" in roles
        assert "GUI" in roles
        assert "Workflow" in roles
        assert "Research" in roles
        assert "Memory" in roles

    def test_get_planner_capability(self):
        cap = self.registry.get("Planner")
        assert cap is not None
        assert "planning" in cap.task_types
        assert cap.supports_delegation is True

    def test_gui_does_not_support_delegation(self):
        cap = self.registry.get("GUI")
        assert cap is not None
        assert cap.supports_delegation is False

    def test_find_capable_agents_for_research(self):
        agents = self.registry.find_capable_agents("research")
        roles = [a.role for a in agents]
        assert "Research" in roles

    def test_find_capable_agents_for_code_generation(self):
        agents = self.registry.find_capable_agents("code_generation")
        roles = [a.role for a in agents]
        assert "Coder" in roles

    def test_cannot_delegate_to_gui(self):
        assert self.registry.can_delegate("Planner", "GUI") is False

    def test_can_delegate_planner_to_research(self):
        assert self.registry.can_delegate("Planner", "Research") is True

    def test_can_delegate_planner_to_coder(self):
        assert self.registry.can_delegate("Planner", "Coder") is True

    def test_unknown_roles_return_false(self):
        # type: ignore[arg-type]  # testing invalid input
        assert self.registry.can_delegate("Unknown", "Planner") is False  # type: ignore
        assert self.registry.can_delegate("Planner", "Unknown") is False  # type: ignore


# ---------------------------------------------------------------------------
# Delegation Service Tests
# ---------------------------------------------------------------------------


def _make_delegation_service(mock_result: str = "mock response") -> AgentDelegationService:
    """Build a delegation service with a mocked router execution service."""
    registry = AgentCapabilityRegistry()
    router_service = MagicMock()
    router_service.execute_chat = AsyncMock(return_value=mock_result)
    return AgentDelegationService(registry=registry, router_service=router_service)


class TestAgentDelegationService:
    def test_planner_delegates_research_task_to_research_agent(self):
        service = _make_delegation_service("Research result here")

        request = DelegationRequest(
            from_role="Planner",
            to_role="Research",
            task_type="research",
            prompt="Research quantum entanglement",
            depth=0,
        )

        response = asyncio.run(service.delegate(request))
        assert response.success is True
        assert response.executed_by == "Research"
        assert response.result == "Research result here"
        assert "Research" in response.delegation_chain

    def test_planner_delegates_coding_task_to_coder(self):
        service = _make_delegation_service("def quicksort(): pass")

        request = DelegationRequest(
            from_role="Planner",
            to_role="Coder",
            task_type="code_generation",
            prompt="Write a quicksort function",
            depth=0,
        )

        response = asyncio.run(service.delegate(request))
        assert response.success is True
        assert response.executed_by == "Coder"

    def test_delegation_to_gui_requires_explicit_permission(self):
        service = _make_delegation_service()

        request = DelegationRequest(
            from_role="Planner",
            to_role="GUI",
            task_type="gui_interaction",
            prompt="Click the Submit button",
            depth=0,
        )

        response = asyncio.run(service.delegate(request))
        assert response.success is False
        assert "permission" in response.error.lower() or "not accept" in response.error.lower()

    def test_delegation_depth_guard_blocks_at_max_depth(self):
        service = _make_delegation_service()

        request = DelegationRequest(
            from_role="Planner",
            to_role="Research",
            task_type="research",
            prompt="Research something",
            depth=MAX_DELEGATION_DEPTH + 1,
        )

        response = asyncio.run(service.delegate(request))
        assert response.success is False
        assert "depth" in response.error.lower() or "limit" in response.error.lower()

    def test_delegation_loop_guard_blocks_cycle(self):
        service = _make_delegation_service()

        request = DelegationRequest(
            from_role="Planner",
            to_role="Research",
            task_type="research",
            prompt="Research something",
            depth=0,
        )

        # Simulate Research already visited (loop)
        visited = {"Research"}
        response = asyncio.run(service.delegate(request, visited=visited))
        assert response.success is False
        assert "loop" in response.error.lower() or "chain" in response.error.lower()

    def test_auto_delegate_finds_research_agent(self):
        service = _make_delegation_service("Auto-research result")

        response = asyncio.run(service.auto_delegate(
            from_role="Planner",
            task_type="research",
            prompt="Find information about AI agents",
        ))
        assert response.success is True
        assert response.executed_by == "Research"

    def test_auto_delegate_finds_coder_for_code_generation(self):
        service = _make_delegation_service("def example(): pass")

        response = asyncio.run(service.auto_delegate(
            from_role="Planner",
            task_type="code_generation",
            prompt="Write a Python function",
        ))
        assert response.success is True
        assert response.executed_by == "Coder"

    def test_auto_delegate_fails_gracefully_for_unknown_task_type(self):
        service = _make_delegation_service()

        response = asyncio.run(service.auto_delegate(
            from_role="Planner",
            task_type="unknown_task_xyz",
            prompt="Do something impossible",
        ))
        assert response.success is False
        assert "eligible" in response.error.lower() or "not found" in response.error.lower()
