"""Phase 6 — Memory-aware routing service.

Adds memory metadata scoring to the central router decision path.
If memory backend is unavailable, requests proceed in degraded mode
(fail-closed to a defined degraded profile) rather than crashing.

Usage example::

    service = MemoryRoutingService()
    decision = service.evaluate(context)
    if decision.degraded:
        log.warning("Memory unavailable, using degraded profile")
"""
from __future__ import annotations

import logging
from typing import Optional

from schemas.router_memory import MemoryRoutingContext, MemoryRoutingDecision

log = logging.getLogger(__name__)

# Sentinel flag — set to True when a real memory backend is wired up.
_MEMORY_BACKEND_READY: bool = False


class MemoryBackendUnavailableError(Exception):
    """Raised when a required memory backend is not configured or reachable."""


class MemoryRoutingService:
    """Evaluates memory requirements and returns a routing decision profile.

    This is a Phase 6 skeleton that enforces the memory routing contract
    without requiring a full vector-DB deployment. When the backend is
    unavailable the service returns a structured degraded decision instead
    of crashing the request path.
    """

    def __init__(self, memory_backend_ready: bool = _MEMORY_BACKEND_READY) -> None:
        self._ready = memory_backend_ready

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, context: MemoryRoutingContext) -> MemoryRoutingDecision:
        """Evaluate memory context and return a routing profile decision.

        Args:
            context: Memory metadata provided by the calling agent.

        Returns:
            A MemoryRoutingDecision describing which routing profile to use.
        """
        if not context.memory_required:
            return MemoryRoutingDecision(
                selected_profile="primary",
                memory_satisfied=True,
                degraded=False,
                reason="No memory required — using primary model profile.",
            )

        if not self._ready:
            log.warning(
                "Memory routing evaluated but backend is not ready. "
                "Proceeding in degraded mode (scope=%s, budget=%d tokens).",
                context.memory_scope,
                context.retrieval_budget_tokens,
            )
            return MemoryRoutingDecision(
                selected_profile="degraded",
                memory_satisfied=False,
                degraded=True,
                reason=(
                    "Memory backend is not available. Request will proceed "
                    "without memory context (degraded mode)."
                ),
            )

        # Backend is ready — select profile based on scope
        profile = self._select_profile(context)
        log.info(
            "Memory routing: scope=%s budget=%d profile=%s",
            context.memory_scope,
            context.retrieval_budget_tokens,
            profile,
        )
        return MemoryRoutingDecision(
            selected_profile=profile,
            memory_satisfied=True,
            degraded=False,
            reason=f"Memory backend ready — selected '{profile}' profile for scope '{context.memory_scope}'.",
        )

    def is_ready(self) -> bool:
        """Return True if the memory backend is configured and reachable."""
        return self._ready

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_profile(self, context: MemoryRoutingContext) -> str:
        """Choose a routing profile based on scope and token budget."""
        if context.memory_scope == "global":
            return "memory_enhanced_global"
        if context.memory_scope == "project":
            return "memory_enhanced_project"
        # Session scope — keep it lightweight
        if context.retrieval_budget_tokens <= 128:
            return "memory_lightweight"
        return "memory_enhanced_session"
