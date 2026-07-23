"""
Failover policy for WindAgent Provider Routing Phase 8.

Maps normalized error classes to retry/failover decisions and determines,
for an execution attempt, whether the coordinator should:
    - retry the same endpoint
    - failover to the next exact-equivalent endpoint
    - stop with an error
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from windagent_providers.base.errors import (
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


class FailoverDecision(str, Enum):
    """What the execution coordinator should do when an attempt fails."""

    FAILOVER = "failover"
    RETRY = "retry"
    STOP = "stop"


@dataclass
class AttemptPolicy:
    """Policy returned for an individual failure."""

    decision: FailoverDecision
    reason: str
    mark_credential_invalid: bool = False
    mark_binding_stale: bool = False


class SameModelFailoverPolicy:
    """
    Default Phase 8 failover policy.

    Error → decision mapping:
        429 RateLimitFailure       → failover + cooldown
        5xx / network / timeout    → retry/failover (counted toward circuit)
        401/403                    → stop (credential invalid) but try other credential if exists
        404 model                  → mark binding stale + failover
        400/422                    → stop (do not failover blindly)
        context overflow           → stop (return to orchestration)
        cancellation               → stop
        quota exhausted            → failover
    """

    def classify(
        self,
        error: ProviderFailure,
        attempt_index: int,
        *,
        max_retries_per_endpoint: int = 1,
    ) -> AttemptPolicy:
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

        # Unknown ProviderFailure: conservative stop.
        return AttemptPolicy(
            decision=FailoverDecision.STOP,
            reason=f"unclassified provider failure: {error.__class__.__name__}",
        )
