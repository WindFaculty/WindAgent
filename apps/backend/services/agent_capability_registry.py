"""Phase 6 — Agent Capability Registry.

Defines the static registry of known agents and their capabilities.
Used by the delegation service to route tasks between agents.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from schemas.agent_routing import AgentCapability, AgentRole

# ---------------------------------------------------------------------------
# Static registry — extend as new agents are added
# ---------------------------------------------------------------------------

_REGISTRY: Dict[AgentRole, AgentCapability] = {
    "Planner": AgentCapability(
        role="Planner",
        task_types=["planning", "reasoning", "chat", "orchestration"],
        model_requirements={"context_window": 4096},
        tool_permissions=["read_file", "create_task"],
        max_latency_ms=8000,
        cost_priority="medium",
        supports_delegation=True,
    ),
    "Coder": AgentCapability(
        role="Coder",
        task_types=["code_generation", "code_review", "debugging", "refactoring"],
        model_requirements={"context_window": 8192, "code_capability": True},
        tool_permissions=["read_file", "write_file", "run_command"],
        max_latency_ms=15000,
        cost_priority="medium",
        supports_delegation=True,
    ),
    "GUI": AgentCapability(
        role="GUI",
        task_types=["gui_interaction", "screen_reading", "computer_use"],
        model_requirements={"vision": True, "context_window": 4096},
        tool_permissions=["screenshot", "mouse_click", "keyboard_type"],
        max_latency_ms=5000,
        cost_priority="high",
        supports_delegation=False,  # GUI tasks require explicit user permission
    ),
    "Workflow": AgentCapability(
        role="Workflow",
        task_types=["workflow_execution", "step_orchestration", "memory_lookup"],
        model_requirements={"context_window": 8192},
        tool_permissions=["read_file", "write_file", "create_task", "run_workflow"],
        max_latency_ms=30000,
        cost_priority="low",
        supports_delegation=True,
    ),
    "Research": AgentCapability(
        role="Research",
        task_types=["research", "web_search", "document_parsing", "summarization"],
        model_requirements={"context_window": 16384},
        tool_permissions=["web_search", "read_url", "read_file"],
        max_latency_ms=20000,
        cost_priority="low",
        supports_delegation=True,
    ),
    "Memory": AgentCapability(
        role="Memory",
        task_types=["memory_storage", "memory_retrieval", "context_injection"],
        model_requirements={"context_window": 4096},
        tool_permissions=["memory_read", "memory_write"],
        max_latency_ms=2000,
        cost_priority="low",
        supports_delegation=True,
    ),
}


class AgentCapabilityRegistry:
    """Read-only registry of agent capabilities.

    Agents can be looked up by role, and compatible agents can be found
    for a given task type.
    """

    def get(self, role: AgentRole) -> Optional[AgentCapability]:
        """Return the capability descriptor for the given agent role."""
        return _REGISTRY.get(role)

    def all_roles(self) -> List[AgentRole]:
        """Return all registered agent roles."""
        return list(_REGISTRY.keys())

    def find_capable_agents(self, task_type: str) -> List[AgentCapability]:
        """Return all agents that can handle the given task type."""
        return [
            cap for cap in _REGISTRY.values()
            if task_type in cap.task_types and cap.supports_delegation
        ]

    def can_delegate(self, from_role: AgentRole, to_role: AgentRole) -> bool:
        """Check if delegation from one role to another is safe.

        Rules:
        - Source agent must exist in registry.
        - Target agent must exist and support delegation.
        - GUI agent cannot be auto-delegated to (requires explicit permission).
        """
        source = _REGISTRY.get(from_role)
        target = _REGISTRY.get(to_role)
        if not source or not target:
            return False
        if not target.supports_delegation:
            return False
        if to_role == "GUI":
            return False  # GUI requires explicit user-granted permission
        return True
