"""
Architecture / canonical contract test for Phase 16: Human Intervention and Account Safety.
"""

from windagent_tools.google_flow import (
    FlowAccountSafetyPolicy,
    FlowCircuitBreakerTrippedError,
    FlowConcurrencyLimitExceededError,
    FlowHumanActionBlockedError,
    FlowHumanActionRecord,
    FlowHumanActionStatus,
    FlowHumanBypassAttemptedError,
    FlowHumanControlDetector,
    FlowHumanControlError,
    FlowHumanControlManager,
    FlowImageHumanActionRequiredError,
    FlowRateLimitExceededError,
    FlowHumanState,
    FlowVideoHumanActionRequiredError,
)


def test_phase16_canonical_exports():
    """Verify that all Phase 16 classes and types are exported by windagent_tools.google_flow."""
    exports = [
        FlowAccountSafetyPolicy,
        FlowCircuitBreakerTrippedError,
        FlowConcurrencyLimitExceededError,
        FlowHumanActionBlockedError,
        FlowHumanActionRecord,
        FlowHumanActionStatus,
        FlowHumanBypassAttemptedError,
        FlowHumanControlDetector,
        FlowHumanControlError,
        FlowHumanControlManager,
        FlowImageHumanActionRequiredError,
        FlowRateLimitExceededError,
        FlowHumanState,
        FlowVideoHumanActionRequiredError,
    ]
    for cls in exports:
        assert cls is not None
