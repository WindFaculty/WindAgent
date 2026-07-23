"""Phase 6 — Tests for memory-aware routing service."""
from __future__ import annotations


from schemas.router_memory import MemoryRoutingContext
from services.memory_routing_service import MemoryRoutingService


class TestMemoryRoutingServiceNoBackend:
    """Tests for MemoryRoutingService when backend is NOT ready."""

    def setup_method(self):
        self.service = MemoryRoutingService(memory_backend_ready=False)

    def test_no_memory_required_returns_primary(self):
        ctx = MemoryRoutingContext(memory_required=False)
        decision = self.service.evaluate(ctx)
        assert decision.selected_profile == "primary"
        assert decision.memory_satisfied is True
        assert decision.degraded is False

    def test_memory_required_backend_down_returns_degraded(self):
        ctx = MemoryRoutingContext(memory_required=True, memory_scope="session")
        decision = self.service.evaluate(ctx)
        assert decision.selected_profile == "degraded"
        assert decision.memory_satisfied is False
        assert decision.degraded is True
        assert "degraded" in decision.reason.lower()

    def test_degraded_mode_does_not_raise(self):
        """Memory unavailability must never crash the call path."""
        ctx = MemoryRoutingContext(
            memory_required=True,
            memory_scope="global",
            retrieval_budget_tokens=4096,
            writeback_policy="full",
        )
        decision = self.service.evaluate(ctx)
        # Must return a valid response, not raise
        assert decision is not None
        assert decision.degraded is True

    def test_is_ready_returns_false(self):
        assert self.service.is_ready() is False


class TestMemoryRoutingServiceWithBackend:
    """Tests for MemoryRoutingService when backend IS ready."""

    def setup_method(self):
        self.service = MemoryRoutingService(memory_backend_ready=True)

    def test_session_scope_small_budget_returns_lightweight(self):
        ctx = MemoryRoutingContext(
            memory_required=True,
            memory_scope="session",
            retrieval_budget_tokens=64,
        )
        decision = self.service.evaluate(ctx)
        assert decision.selected_profile == "memory_lightweight"
        assert decision.memory_satisfied is True
        assert decision.degraded is False

    def test_session_scope_large_budget_returns_enhanced_session(self):
        ctx = MemoryRoutingContext(
            memory_required=True,
            memory_scope="session",
            retrieval_budget_tokens=1024,
        )
        decision = self.service.evaluate(ctx)
        assert decision.selected_profile == "memory_enhanced_session"

    def test_project_scope_returns_enhanced_project(self):
        ctx = MemoryRoutingContext(
            memory_required=True,
            memory_scope="project",
        )
        decision = self.service.evaluate(ctx)
        assert decision.selected_profile == "memory_enhanced_project"

    def test_global_scope_returns_enhanced_global(self):
        ctx = MemoryRoutingContext(
            memory_required=True,
            memory_scope="global",
        )
        decision = self.service.evaluate(ctx)
        assert decision.selected_profile == "memory_enhanced_global"

    def test_is_ready_returns_true(self):
        assert self.service.is_ready() is True
