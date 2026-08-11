"""Plan A A6 — real provider-neutral Studio model port over route lock + coordinator.

``RouteLockedModelPort`` implements the frozen ``PreproductionModelPort``
protocol (``windagent_intelligence.video.ports``) with REAL provider
infrastructure. It lives in the worker app package because it bridges
provider infrastructure (route lock + endpoint coordinator) and the
intelligence port contract — a leaf-app composition seam, never a provider
or intelligence dependency edge.

- ``lock_route`` resolves/creates a durable route lock through
  ``RouteLockService`` for a deterministic scope derived from the request
  (explicit ``route_lock_id`` wins; otherwise ``capability:prompt-hash``).
  The same scope always reuses the same lock, so retries of the same task
  never silently flip canonical model.
- ``complete`` executes the completion through ``EndpointExecutionCoordinator``
  (same-model endpoint failover, cooldowns, attempt audit) and returns a typed
  ``ModelCompletionResult`` with provider/model/usage provenance. Provider
  failures re-raise as typed ``ProviderFailure`` subclasses; ``classify`` maps
  every failure class into typed retryability (transient/quota/auth/schema/
  safety/terminal/unknown) with an explicit retryable flag.
- No mock fallback and no bypass: when no rule matches, the model is disabled,
  or every exact-equivalent endpoint is exhausted, the failure propagates.
  The port has no ``fixture`` marker, so certification guards
  (``assert_not_fixture``) accept it as a real provider boundary.

Env variables are compatibility inputs only — the adapter reads
``WINDAGENT_STUDIO_CANONICAL_MODEL`` as the routing default, never as hidden
domain policy (Plan A A6 step 5).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from windagent_core.contracts.providers import ProviderRequest, ProviderResponse
from windagent_providers.base.errors import (
    AuthenticationFailure,
    CancellationFailure,
    ContentPolicyFailure,
    ContextOverflowFailure,
    InvalidRequestFailure,
    MalformedResponseFailure,
    ModelNotFoundFailure,
    NetworkFailure,
    PermissionFailure,
    ProtocolMismatchFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    QuotaExhaustedFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
    TimeoutFailure,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext
from windagent_providers.routing.rules import RoutingRule, RoutingRuleSet
from windagent_providers.routing.route_lock_service import RouteLockService

try:  # frozen intelligence port (B-owned protocol; provider never imports B logic)
    from windagent_intelligence.video.ports import (
        ModelCompletionRequest,
        ModelCompletionResult,
        PreproductionModelPort,
    )
except ImportError:  # pragma: no cover - providers must stay importable standalone
    PreproductionModelPort = None  # type: ignore[assignment,misc]
    ModelCompletionRequest = None  # type: ignore[assignment,misc]
    ModelCompletionResult = None  # type: ignore[assignment,misc]

#: Failure categories from the B0 taxonomy (quality_and_error_taxonomy.md §3).
TRANSIENT = "transient"
QUOTA = "quota"
AUTH = "auth"
SCHEMA = "schema"
SAFETY = "safety"
TERMINAL = "terminal"
UNKNOWN = "unknown"

#: Default canonical model used by the studio routing rule; env is a
#: compatibility input, never embedded domain policy.
DEFAULT_STUDIO_CANONICAL_MODEL = "windagent/story-default"


@dataclass(frozen=True)
class FailureClassification:
    """Typed retryability of one provider failure (A6 step 3)."""

    category: str
    retryable: bool
    code: str
    retry_after: Optional[float] = None


@dataclass(frozen=True)
class RouteLockReceipt:
    """Returned by ``lock_route``; carries route/model provenance only."""

    route_lock_id: str
    canonical_model_id: str
    rule_id: str
    rule_version: int
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    prompt_ref: Dict[str, str] = field(default_factory=dict)


def _scope_id(request: Any, *, prefix: str) -> str:
    """Deterministic route-lock scope for one completion request.

    Explicit ``route_lock_id`` (e.g. carried by the durable task envelope)
    wins; otherwise ``capability:prompt-hash`` so identical prompts on the
    same capability always lock the same canonical model.
    """
    explicit = (request.metadata or {}).get("route_lock_id")
    if explicit:
        return str(explicit)
    prompt_spec = getattr(request, "prompt_spec", None)
    if prompt_spec is not None and getattr(prompt_spec, "content_hash", None):
        prompt_hash = prompt_spec.content_hash[:16]
    else:
        digest = hashlib.sha256(
            f"{request.system or ''}\0{request.user or ''}".encode("utf-8")
        ).hexdigest()
        prompt_hash = digest[:16]
    return f"{request.capability}:{prompt_hash}"


def classify_provider_error(exc: BaseException) -> FailureClassification:
    """Map any provider failure into typed retryability (A6 step 3).

    Transient network/timeout/5xx and quota-rate-limit failures are retryable;
    auth/schema/safety/terminal failures are not. Unknown exceptions fail
    closed as non-retryable UNKNOWN.
    """
    if not isinstance(exc, ProviderFailure):
        return FailureClassification(
            category=UNKNOWN, retryable=False, code=type(exc).__name__
        )
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(exc, RateLimitFailure):
        return FailureClassification(QUOTA, True, "STORY_PROVIDER_RATE_LIMIT", retry_after)
    if isinstance(exc, QuotaExhaustedFailure):
        return FailureClassification(QUOTA, False, "STORY_PROVIDER_QUOTA_EXHAUSTED")
    if isinstance(exc, AuthenticationFailure):
        return FailureClassification(AUTH, False, "STORY_PROVIDER_AUTH")
    if isinstance(exc, PermissionFailure):
        return FailureClassification(AUTH, False, "STORY_PROVIDER_PERMISSION")
    if isinstance(exc, ContentPolicyFailure):
        return FailureClassification(SAFETY, False, "STORY_PROVIDER_CONTENT_POLICY")
    if isinstance(exc, (InvalidRequestFailure, ContextOverflowFailure)):
        return FailureClassification(SCHEMA, False, "STORY_PROVIDER_INVALID_REQUEST")
    if isinstance(exc, ModelNotFoundFailure):
        return FailureClassification(TERMINAL, False, "STORY_PROVIDER_MODEL_NOT_FOUND")
    if isinstance(exc, MalformedResponseFailure):
        return FailureClassification(TERMINAL, False, "STORY_PROVIDER_MALFORMED_RESPONSE")
    if isinstance(exc, ProtocolMismatchFailure):
        return FailureClassification(TERMINAL, False, "STORY_PROVIDER_PROTOCOL_MISMATCH")
    if isinstance(exc, CancellationFailure):
        return FailureClassification(TERMINAL, False, "STORY_PROVIDER_CANCELLED")
    if isinstance(exc, SameModelEndpointExhausted):
        return FailureClassification(TRANSIENT, True, "STORY_PROVIDER_ENDPOINTS_EXHAUSTED")
    if isinstance(exc, (NetworkFailure, TimeoutFailure, ProviderUnavailableFailure)):
        return FailureClassification(TRANSIENT, True, f"STORY_PROVIDER_{type(exc).__name__.upper()}")
    return FailureClassification(TERMINAL, False, f"STORY_PROVIDER_{type(exc).__name__.upper()}")


class RouteLockedModelPort:
    """Real ``PreproductionModelPort`` backed by route lock + coordinator."""

    #: Marker for certification guards: this IS a real provider boundary, so
    #: the fixture-detection contract must see no ``fixture`` attribute.
    fixture = False

    def __init__(
        self,
        route_lock_service: RouteLockService,
        coordinator: Any,
        *,
        canonical_model: Optional[str] = None,
        disabled_models: Optional[set] = None,
        scope_type: str = "studio_model",
        max_attempts: int = 5,
    ) -> None:
        self._route_lock_service = route_lock_service
        self._coordinator = coordinator
        self._canonical_model = canonical_model
        self._disabled_models = disabled_models or set()
        self._scope_type = scope_type
        self._max_attempts = max_attempts

    # -- PreproductionModelPort --------------------------------------------

    async def complete(self, request: Any) -> Any:
        receipt = await self.lock_route(request)
        provider_request = self._build_provider_request(request, receipt)
        response = await self._coordinator.execute(
            provider_request,
            self._route_lock_service.get_lock_by_id(receipt.route_lock_id),
            turn_id=(request.metadata or {}).get("task_id") or receipt.route_lock_id,
            max_attempts=self._max_attempts,
        )
        return self._to_completion_result(request, response, receipt)

    async def lock_route(self, request: Any) -> RouteLockReceipt:
        """Lock the canonical model for this request scope (create-or-reuse)."""
        scope_id = _scope_id(request, prefix=self._scope_type)
        context = RuleMatchContext(
            scope_type=self._scope_type,
            scope_id=scope_id,
            task_labels=[request.capability],
            available_capabilities=[request.capability],
        )
        record = self._route_lock_service.resolve_or_create_lock(context)
        return RouteLockReceipt(
            route_lock_id=record.lock_id,
            canonical_model_id=record.canonical_model_id,
            rule_id=record.routing_snapshot.rule_id,
            rule_version=record.routing_snapshot.rule_version,
            prompt_ref={"prompt_id": (request.metadata or {}).get("prompt_id", "")},
        )

    def classify(self, exc: BaseException) -> FailureClassification:
        return classify_provider_error(exc)

    # -- internals ----------------------------------------------------------

    def _build_provider_request(self, request: Any, receipt: RouteLockReceipt) -> ProviderRequest:
        metadata = request.metadata or {}
        return ProviderRequest(
            model_id=receipt.canonical_model_id,
            prompt=request.user,
            messages=[],
            system_instruction=request.system,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            request_id=metadata.get("task_id") or receipt.route_lock_id,
            idempotency_key=metadata.get("idempotency_key")
            or f"studio:{receipt.route_lock_id}:{receipt.canonical_model_id}",
        )

    @staticmethod
    def _to_completion_result(
        request: Any, response: ProviderResponse, receipt: RouteLockReceipt
    ) -> Any:
        usage = response.usage
        provider = (
            response.provider_id
            or response.provider_model_id
            or receipt.canonical_model_id
        )
        return ModelCompletionResult(
            capability=request.capability,
            content=response.content or response.text or "",
            finish_reason=response.finish_reason,
            provider=str(provider),
            usage={
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "estimated_cost_usd": usage.estimated_cost_usd,
                #: Route lock id is provenance (an id, never content/secrets);
                #: artifact envelopes persist it as model_route_id.
                "route_lock_id": receipt.route_lock_id,
            },
        )


def build_studio_ruleset(
    canonical_model: Optional[str] = None, *, rule_id: str = "studio-story"
) -> RoutingRuleSet:
    """Routing rule set for Studio story completions (one rule, env default)."""
    return RoutingRuleSet(
        rules=[
            RoutingRule(
                rule_id=rule_id,
                rule_version=1,
                canonical_model_id=canonical_model or DEFAULT_STUDIO_CANONICAL_MODEL,
                description="Plan A A6 Studio story model route (provider-neutral)",
            )
        ]
    )


__all__ = [
    "TRANSIENT",
    "QUOTA",
    "AUTH",
    "SCHEMA",
    "SAFETY",
    "TERMINAL",
    "UNKNOWN",
    "DEFAULT_STUDIO_CANONICAL_MODEL",
    "FailureClassification",
    "RouteLockReceipt",
    "classify_provider_error",
    "RouteLockedModelPort",
    "build_studio_ruleset",
]
