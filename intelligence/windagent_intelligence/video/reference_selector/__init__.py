"""
Phase 11 — Reference Binding (plan 03 §24.1).

The `ReferenceBindingPlanner` binds APPROVED, hash-bound reference assets to
every shot of the Phase 9 shot graph: identity portraits, location/prop/style
references, and mode-required frames. Only APPROVED assets of the correct
revision bind; a candidate, rejected, stale or wrong-revision asset fails
closed and never compiles into a GenerationRequest. Fully deterministic —
never calls a provider.
"""

from windagent_intelligence.video.reference_selector.models import (
    ReferenceBindingPlanReceipt,
)
from windagent_intelligence.video.reference_selector.service import (
    ReferenceBindingPlanner,
)

__all__ = ["ReferenceBindingPlanner", "ReferenceBindingPlanReceipt"]
