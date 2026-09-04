"""Same-model failover policy: normalized failures to execution decisions.

REWRITE of the frozen ``providers/windagent_providers/routing/failover_policy.py``
with decision mapping preserved exactly (parity oracle):

- 429 rate limit          → failover (endpoint gets a cooldown)
- quota exhausted         → failover
- 5xx / network / timeout → retry same endpoint once, then failover
- 401/403                 → failover and mark the credential invalid
- 404 model               → failover and mark the binding stale
- context overflow        → stop (returned to the caller for compaction)
- invalid request         → stop (never fail over blindly)
- cancellation            → stop
- unknown provider failure→ conservative stop
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .errors import (
    AuthenticationFailure,
    CancellationFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    PermissionFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    QuotaExhaustedFailure,
    RateLimitFailure,
    TimeoutFailure,
)


class FailoverDecision(StrEnum):
    """What the execution coordinator should do when an attempt fails."""

    FAILOVER = "failover"
    RETRY = "retry"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class AttemptPolicy:
    """The outcome for one failed execution attempt."""

    decision: FailoverDecision
    reason: str
    mark_credential_invalid: bool = False
    mark_binding_stale: bool = False


class SameModelFailoverPolicy:
    """Default failover policy for the execution coordinator."""

    def classify(
        self,
        error: ProviderFailure,
        attempt_index: int,
        *,
        max_retries_per_endpoint: int = 1,
    ) -> AttemptPolicy:
        """Classify ``error`` raised on ``attempt_index`` of one endpoint."""
        if isinstance(error, RateLimitFailure):
            return AttemptPolicy(
                decision=FailoverDecision.FAILOVER,
                reason="429 received; cooldown endpoint and failover to same-model binding",
            )

        if isinstance(error, QuotaExhaustedFailure):
            return AttemptPolicy(
                decision=FailoverDecision.FAILOVER,
                reason="quota exhausted; failover to same-model binding",
            )

        if isinstance(error, ProviderUnavailableFailure):
            if attempt_index < max_retries_per_endpoint:
                return AttemptPolicy(
                    decision=FailoverDecision.RETRY,
                    reason="5xx received; retry same endpoint",
                )
            return AttemptPolicy(
                decision=FailoverDecision.FAILOVER,
                reason="5xx persisted; failover to same-model binding",
            )

        if isinstance(error, (NetworkFailure, TimeoutFailure)):
            if attempt_index < max_retries_per_endpoint:
                return AttemptPolicy(
                    decision=FailoverDecision.RETRY,
                    reason="transient network/timeout; retry same endpoint",
                )
            return AttemptPolicy(
                decision=FailoverDecision.FAILOVER,
                reason="network/timeout persisted; failover to same-model binding",
            )

        if isinstance(error, (AuthenticationFailure, PermissionFailure)):
            return AttemptPolicy(
                decision=FailoverDecision.FAILOVER,
                reason="auth/permission failure; failover to binding with different credential",
                mark_credential_invalid=True,
            )

        if isinstance(error, ModelNotFoundFailure):
            return AttemptPolicy(
                decision=FailoverDecision.FAILOVER,
                reason="model not found; mark binding stale and failover",
                mark_binding_stale=True,
            )

        if isinstance(error, ContextOverflowFailure):
            return AttemptPolicy(
                decision=FailoverDecision.STOP,
                reason="context overflow; return to orchestration for compaction/truncation",
            )

        if isinstance(error, InvalidRequestFailure):
            return AttemptPolicy(
                decision=FailoverDecision.STOP,
                reason="invalid request; no blind failover",
            )

        if isinstance(error, CancellationFailure):
            return AttemptPolicy(
                decision=FailoverDecision.STOP,
                reason="request cancelled; do not retry",
            )

        return AttemptPolicy(
            decision=FailoverDecision.STOP,
            reason=f"unclassified provider failure: {error.__class__.__name__}",
        )
