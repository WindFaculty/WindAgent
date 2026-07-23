"""Phase 6 — Agent Delegation Service.

Manages agent-to-agent task delegation with:
- Capability-based routing to the best agent for a task type.
- Delegation loop guard (max depth and visited-set tracking).
- Fail-closed behavior: delegation never crashes the call path.
- GUI agent requires explicit permission and cannot be auto-delegated.
"""
from __future__ import annotations

import logging
from typing import Optional, Set

from schemas.agent_routing import (
    AgentRole,
    DelegationRequest,
    DelegationResponse,
)
from services.agent_capability_registry import AgentCapabilityRegistry
from services.router_execution_service import RouterExecutionService

log = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 3
"""Maximum number of times a task can be re-delegated before forced termination."""


class DelegationLoopError(Exception):
    """Raised when a delegation cycle or depth limit is detected."""


class MissingPermissionError(Exception):
    """Raised when delegating to an agent that requires explicit user permission."""


class AgentDelegationService:
    """Orchestrates agent-to-agent task delegation.

    Delegates tasks from one agent to another when the target agent has a
    capability the source agent lacks. Enforces depth limits and cycle guards.

    Args:
        registry: The capability registry of all known agents.
        router_service: The router execution service used to run actual completions.
    """

    def __init__(
        self,
        registry: AgentCapabilityRegistry,
        router_service: RouterExecutionService,
    ) -> None:
        self.registry = registry
        self.router_service = router_service

    async def delegate(
        self,
        request: DelegationRequest,
        visited: Optional[Set[str]] = None,
    ) -> DelegationResponse:
        """Delegate a task to a target agent role, enforcing safety guardrails.

        Args:
            request: The delegation request containing source/target roles and task.
            visited: Set of already-visited agent roles in the current chain
                     (for loop detection).

        Returns:
            A DelegationResponse with the result or structured error.
        """
        if visited is None:
            visited = set()

        # ---- Safety guards ------------------------------------------------

        # 1. Depth guard
        if request.depth > MAX_DELEGATION_DEPTH:
            log.error(
                "Delegation depth exceeded: %d > max %d (chain: %s)",
                request.depth,
                MAX_DELEGATION_DEPTH,
                " -> ".join(visited),
            )
            return DelegationResponse(
                success=False,
                error=f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) exceeded. "
                      "Preventing infinite delegation chain.",
                executed_by=request.from_role,
                depth=request.depth,
                delegation_chain=list(visited),
            )

        # 2. Loop guard
        if request.to_role in visited:
            log.error(
                "Delegation loop detected: %s already visited in chain %s",
                request.to_role,
                " -> ".join(visited),
            )
            return DelegationResponse(
                success=False,
                error=f"Delegation loop detected: '{request.to_role}' already in chain.",
                executed_by=request.from_role,
                depth=request.depth,
                delegation_chain=list(visited),
            )

        # 3. Permission guard: GUI cannot be auto-delegated
        if not self.registry.can_delegate(request.from_role, request.to_role):
            target_cap = self.registry.get(request.to_role)
            if target_cap and not target_cap.supports_delegation:
                log.warning(
                    "Delegation denied: %s → %s (target does not support auto-delegation).",
                    request.from_role,
                    request.to_role,
                )
                return DelegationResponse(
                    success=False,
                    error=(
                        f"Agent '{request.to_role}' does not accept delegated tasks. "
                        "Explicit user permission is required for GUI/computer-use operations."
                    ),
                    executed_by=request.from_role,
                    depth=request.depth,
                    delegation_chain=list(visited),
                )
            return DelegationResponse(
                success=False,
                error=f"Delegation from '{request.from_role}' to '{request.to_role}' is not permitted.",
                executed_by=request.from_role,
                depth=request.depth,
                delegation_chain=list(visited),
            )

        # ---- Execute via router -------------------------------------------

        visited.add(request.from_role)
        new_chain = list(visited) + [request.to_role]

        messages = []
        if request.context:
            messages.append({"role": "system", "content": request.context})
        messages.append({"role": "user", "content": request.prompt})

        log.info(
            "Delegating task from %s → %s (depth=%d, task_type=%s)",
            request.from_role,
            request.to_role,
            request.depth,
            request.task_type,
        )

        try:
            result = await self.router_service.execute_chat(
                role=request.to_role,
                messages=messages,
            )
            return DelegationResponse(
                success=True,
                result=result,
                executed_by=request.to_role,
                depth=request.depth,
                delegation_chain=new_chain,
            )
        except Exception as exc:
            log.exception(
                "Delegation execution failed: %s → %s: %s",
                request.from_role,
                request.to_role,
                exc,
            )
            return DelegationResponse(
                success=False,
                error=f"Delegated execution failed: {exc}",
                executed_by=request.to_role,
                depth=request.depth,
                delegation_chain=new_chain,
            )

    async def auto_delegate(
        self,
        from_role: AgentRole,
        task_type: str,
        prompt: str,
        context: Optional[str] = None,
        depth: int = 0,
        visited: Optional[Set[str]] = None,
    ) -> DelegationResponse:
        """Automatically find the best capable agent for a task type and delegate.

        Args:
            from_role: The role initiating the delegation.
            task_type: The task type to find a capable agent for.
            prompt: The task prompt.
            context: Optional system context.
            depth: Current delegation depth.
            visited: Set of already-visited roles.

        Returns:
            DelegationResponse from the selected agent, or a structured error
            if no capable agent is found.
        """
        capable = self.registry.find_capable_agents(task_type)
        eligible = [
            cap for cap in capable
            if cap.role != from_role and (visited is None or cap.role not in visited)
        ]

        if not eligible:
            return DelegationResponse(
                success=False,
                error=f"No eligible agent found for task_type='{task_type}'.",
                executed_by=from_role,
                depth=depth,
                delegation_chain=list(visited or []),
            )

        # Pick first eligible — could be extended to score by latency/cost
        target = eligible[0]

        request = DelegationRequest(
            from_role=from_role,
            to_role=target.role,
            task_type=task_type,
            prompt=prompt,
            context=context,
            depth=depth,
        )
        return await self.delegate(request, visited=visited or set())
