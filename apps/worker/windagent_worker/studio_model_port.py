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
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.contracts.providers import ProviderRequest, ProviderResponse
from windagent_core.contracts.studio.story_roles import (
    ROUTING_UNAVAILABLE,
    RoutingUnavailableError,
    expand_role_labels,
)
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
from windagent_providers.routing.route_lock_service import (
    CanonicalModelDisabledError,
    NoMatchingRuleError,
    RouteLockService,
)

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

#: Rule id of the worker system-default route (lowest priority, P0.3.4).
SYSTEM_DEFAULT_RULE_ID = "system-default"

#: Failure classes eligible for rule-declared model fallback (P0.3.5).
#: Exactly: endpoint unavailable, timeout, rate limit, temporary provider
#: failure — plus exhaustion of every exact-equivalent endpoint. Schema
#: validation, auth, safety, and prompt-contract failures NEVER fall back.
FALLBACK_ELIGIBLE_FAILURES = (
    NetworkFailure,
    TimeoutFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
)


def utc_now_naive() -> datetime:
    """Naive UTC timestamp (storage convention of the durable tables)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        receipt_repository: Any = None,
    ) -> None:
        self._route_lock_service = route_lock_service
        self._coordinator = coordinator
        self._canonical_model = canonical_model
        self._disabled_models = disabled_models or set()
        self._scope_type = scope_type
        self._max_attempts = max_attempts
        #: Optional durable route-receipt writer (P0.3.6). Receipt failures
        #: never break routing — they are diagnostics, not the transaction.
        self._receipt_repository = receipt_repository

    # -- PreproductionModelPort --------------------------------------------

    async def complete(self, request: Any) -> Any:
        receipt = await self.lock_route(request)
        provider_request = self._build_provider_request(request, receipt)
        turn_id = (request.metadata or {}).get("task_id") or receipt.route_lock_id
        started_at = utc_now_naive()
        try:
            response = await self._coordinator.execute(
                provider_request,
                self._route_lock_service.get_lock_by_id(receipt.route_lock_id),
                turn_id=turn_id,
                max_attempts=self._max_attempts,
            )
        except ProviderFailure as exc:
            classification = classify_provider_error(exc)
            fallback_result = await self._execute_rule_fallback(
                request,
                receipt,
                provider_request,
                exc,
                classification.code,
                turn_id=turn_id,
                started_at=started_at,
            )
            if fallback_result is not None:
                return fallback_result
            self._record_receipt(
                request=request,
                receipt=receipt,
                response=None,
                started_at=started_at,
                status="failed",
                error_code=classification.code,
            )
            raise
        completed_at = utc_now_naive()
        result = self._to_completion_result(request, response, receipt)
        self._record_receipt(
            request=request,
            receipt=receipt,
            response=response,
            started_at=started_at,
            completed_at=completed_at,
        )
        return result

    async def _execute_rule_fallback(
        self,
        request: Any,
        primary_receipt: RouteLockReceipt,
        provider_request: ProviderRequest,
        primary_exc: ProviderFailure,
        reason_code: str,
        *,
        turn_id: str,
        started_at: datetime,
    ) -> Optional[Any]:
        """Retry a transient failure against the rule's declared fallback model.

        Only ``FALLBACK_ELIGIBLE_FAILURES`` may fall back, and only when the
        matched rule declares a different fallback canonical model. The
        primary lock is never mutated: a separate pinned fallback lock keeps
        endpoint attempts FK-consistent and audited.
        """
        if not isinstance(primary_exc, FALLBACK_ELIGIBLE_FAILURES):
            return None
        fallback_model = self._resolve_declared_fallback_model(primary_receipt)
        if not fallback_model or fallback_model == primary_receipt.canonical_model_id:
            return None
        try:
            fallback_lock = self._route_lock_service.create_fallback_lock(
                scope_type=f"{self._scope_type}_fallback",
                scope_id=(
                    f"{primary_receipt.route_lock_id}:"
                    f"{uuid.uuid4().hex[:10]}"
                ),
                canonical_model_id=fallback_model,
                reason=f"model_failover:{reason_code}"[:255],
                source_lock_id=primary_receipt.route_lock_id,
            )
        except Exception:  # noqa: BLE001 — fallback lock issues never mask the primary failure
            return None

        fallback_receipt = replace(
            primary_receipt,
            route_lock_id=fallback_lock.lock_id,
            canonical_model_id=fallback_model,
        )
        fallback_request = provider_request.model_copy(
            update={
                "model_id": fallback_model,
                "idempotency_key": f"studio:{fallback_lock.lock_id}",
            }
        )
        try:
            response = await self._coordinator.execute(
                fallback_request,
                fallback_lock,
                turn_id=turn_id,
                max_attempts=self._max_attempts,
            )
        except Exception:  # noqa: BLE001 — original failure wins over fallback failure
            self._record_receipt(
                request=request,
                receipt=primary_receipt,
                response=None,
                started_at=started_at,
                status="failed",
                error_code=reason_code,
                fallback_used=True,
                fallback_reason=reason_code,
            )
            return None
        completed_at = utc_now_naive()
        result = self._to_completion_result(request, response, fallback_receipt)
        result = replace(
            result,
            usage={
                **result.usage,
                "fallback_used": True,
                "fallback_reason": reason_code,
            },
        )
        self._record_receipt(
            request=request,
            receipt=primary_receipt,
            response=response,
            started_at=started_at,
            completed_at=completed_at,
            fallback_used=True,
            fallback_reason=reason_code,
            override_lock_id=fallback_lock.lock_id,
            override_model_id=fallback_model,
        )
        return result

    def _resolve_declared_fallback_model(self, receipt: RouteLockReceipt) -> Optional[str]:
        """Resolve the matched rule's declared fallback canonical model."""
        ruleset = self._route_lock_service.current_ruleset
        for rule in ruleset.rules:
            if rule.rule_id == receipt.rule_id:
                return rule.fallback_model_id
        return None

    def _record_receipt(
        self,
        *,
        request: Any,
        receipt: RouteLockReceipt,
        response: Optional[ProviderResponse],
        started_at: datetime,
        completed_at: Optional[datetime] = None,
        status: str = "success",
        error_code: Optional[str] = None,
        fallback_used: bool = False,
        fallback_reason: Optional[str] = None,
        override_lock_id: Optional[str] = None,
        override_model_id: Optional[str] = None,
    ) -> None:
        """Persist one route receipt row (P0.3.6); diagnostics only."""
        repo = self._receipt_repository
        if repo is None:
            return
        metadata = request.metadata or {}
        task_id = str(
            metadata.get("task_id")
            or getattr(request, "request_id", "")
            or receipt.route_lock_id
        )
        rule_id = receipt.rule_id or ""
        role = (
            rule_id[len("role-") :]
            if rule_id.startswith("role-")
            else (getattr(request, "capability", "") or "")
        )
        raw_metadata = getattr(response, "raw_metadata", {}) or {}
        try:
            repo.record_receipt(
                task_id=task_id[:128],
                role=(role or "")[:128],
                rule_id=rule_id[:128],
                route_lock_id=override_lock_id or receipt.route_lock_id,
                selected_provider=(
                    str(provider_value) if (provider_value := getattr(response, "provider_id", None)) else None
                ),
                selected_model_id=(
                    override_model_id
                    or getattr(response, "canonical_model_id", None)
                    or receipt.canonical_model_id
                ),
                provider_model_id=getattr(response, "provider_model_id", None),
                endpoint_id=getattr(response, "endpoint_id", None)
                or raw_metadata.get("endpoint_id"),
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                status=status,
                error_code=error_code,
                started_at=started_at,
                completed_at=completed_at or utc_now_naive(),
            )
        except Exception as exc:  # noqa: BLE001 — receipts must never break routing
            import logging

            logging.getLogger("windagent.worker.studio").warning(
                "Route receipt write failed: %s", exc
            )

    async def lock_route(self, request: Any) -> RouteLockReceipt:
        """Lock the canonical model for this request scope (create-or-reuse)."""
        scope_id = _scope_id(request, prefix=self._scope_type)
        capability = request.capability
        context = RuleMatchContext(
            scope_type=self._scope_type,
            scope_id=scope_id,
            # P0.3.1: expand the capability label so rules authored with the
            # canonical story role (or its plan alias) match short
            # prompt-registry capabilities symmetrically.
            task_labels=expand_role_labels(capability),
            available_capabilities=expand_role_labels(capability),
        )
        record = None
        try:
            record = self._route_lock_service.resolve_or_create_lock(context)
        except (NoMatchingRuleError, CanonicalModelDisabledError) as exc:
            # P0.3.4 fail-closed: no valid model → typed ROUTING_UNAVAILABLE,
            # never a random selection.
            raise RoutingUnavailableError(request.capability, str(exc)) from exc
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
            structured_output_schema=request.structured_output_schema,
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
                "canonical_model_id": response.canonical_model_id
                or receipt.canonical_model_id,
                "provider_model_id": response.provider_model_id,
                "endpoint_id": response.endpoint_id,
                "provider_binding_id": response.raw_metadata.get(
                    "provider_binding_id"
                ),
                "provider_attempt_id": response.raw_metadata.get(
                    "provider_attempt_id"
                ),
                "provider_request_id": response.provider_request_id,
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


def compose_story_ruleset(
    sql_ruleset: RoutingRuleSet,
    *,
    system_default_model: Optional[str],
) -> RoutingRuleSet:
    """Resolution order composition (P0.3.4).

    SQL role rules keep their configured priorities and win first; when a
    system-default model is explicitly configured it is appended ONCE as the
    lowest-priority wildcard rule so unmatched roles resolve to it instead of
    failing. With no SQL rule and no default, resolution fails closed with
    ``NoMatchingRuleError`` → ``ROUTING_UNAVAILABLE``.
    """
    rules = list(sql_ruleset.rules)
    if system_default_model:
        already_default = any(
            r.rule_id == SYSTEM_DEFAULT_RULE_ID for r in rules
        )
        if not already_default:
            rules.append(
                RoutingRule(
                    rule_id=SYSTEM_DEFAULT_RULE_ID,
                    rule_version=1,
                    canonical_model_id=system_default_model,
                    description="System default route (lowest priority)",
                    priority=10_000,
                )
            )
    return RoutingRuleSet(rules=rules)


__all__ = [
    "TRANSIENT",
    "QUOTA",
    "AUTH",
    "SCHEMA",
    "SAFETY",
    "TERMINAL",
    "UNKNOWN",
    "ROUTING_UNAVAILABLE",
    "DEFAULT_STUDIO_CANONICAL_MODEL",
    "SYSTEM_DEFAULT_RULE_ID",
    "FALLBACK_ELIGIBLE_FAILURES",
    "FailureClassification",
    "RouteLockReceipt",
    "classify_provider_error",
    "RouteLockedModelPort",
    "build_studio_ruleset",
    "compose_story_ruleset",
]
