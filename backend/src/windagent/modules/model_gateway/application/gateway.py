"""The ModelGateway facade: the single routing and invocation authority.

REWRITE target of plan section 17 — there is exactly one place in V2 that
decides which canonical model serves a scope, which endpoint serves the
model, and how failures fail over.  Model-level fallback (P0.3.5) is
preserved: only the eligible failure classes trigger it, and it pins a
separate fallback lock instead of mutating the primary decision.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from uuid import uuid4

from windagent.kernel.time import Clock, SystemClock, utc_now
from windagent.kernel.types import JSONValue
from windagent.platform.observability import Telemetry

from ..domain.errors import (
    CanonicalModelDisabledError,
    ModelGatewayValidationError,
    ModelInvocationFailed,
    NetworkFailure,
    NoMatchingRuleError,
    ProviderFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    SameModelEndpointExhausted,
    TimeoutFailure,
)
from ..domain.route_lock import RouteLockRecord
from ..domain.rules import RoutingRule, RuleMatchContext, RuleMatcher
from ..providers.contracts import ImagePart, ProviderMessage, ProviderRequest
from .coordinator import EndpointExecutionCoordinator, ModelCompletionResult
from .models import ReceiptRow
from .ports import TransactionScope
from .route_locks import RouteLockService
from .selector import EndpointSelector

FALLBACK_ELIGIBLE_KINDS = frozenset(
    {
        NetworkFailure.kind,
        TimeoutFailure.kind,
        ProviderUnavailableFailure.kind,
        RateLimitFailure.kind,
        SameModelEndpointExhausted.kind,
    }
)


@dataclass(frozen=True, slots=True)
class InvocationRequest:
    """Everything one model invocation needs, in normalized form."""

    task_id: str
    scope_id: str
    scope_type: str = "task"
    role: str | None = None

    prompt: str = ""
    messages: tuple[ProviderMessage, ...] = ()
    system_instruction: str | None = None
    temperature: float | None = 0.7
    top_p: float | None = None
    seed: int | None = None
    max_output_tokens: int | None = None
    stop_sequences: tuple[str, ...] = ()
    tools: tuple[Mapping[str, object], ...] = ()
    tool_choice: str | dict[str, object] | None = None
    structured_output_schema: dict[str, object] | None = None
    image_parts: tuple[ImagePart, ...] = ()
    timeout_seconds: float = 30.0

    task_labels: tuple[str, ...] = ()
    agent_type: str = ""
    workflow_type: str = ""
    available_capabilities: tuple[str, ...] = ()
    estimated_context_tokens: int = 0
    has_tools: bool = False
    has_vision: bool = False
    cost_class: str = ""
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = None

    def match_context(self) -> RuleMatchContext:
        """Project the routing-relevant signals onto the matcher context."""
        return RuleMatchContext(
            scope_id=self.scope_id,
            scope_type=self.scope_type,
            task_labels=self.task_labels,
            agent_type=self.agent_type,
            workflow_type=self.workflow_type,
            available_capabilities=self.available_capabilities,
            estimated_context_tokens=self.estimated_context_tokens,
            has_tools=self.has_tools,
            has_vision=self.has_vision,
            cost_class=self.cost_class,
            requires_local=self.requires_local,
            requires_private=self.requires_private,
            user_preference_model=self.user_preference_model,
        )

    def provider_request(self) -> ProviderRequest:
        """Build the transport-agnostic provider request."""
        return ProviderRequest(
            model_id="",
            messages=self.messages,
            prompt=self.prompt,
            system_instruction=self.system_instruction,
            temperature=self.temperature,
            top_p=self.top_p,
            seed=self.seed,
            max_output_tokens=self.max_output_tokens,
            stop_sequences=self.stop_sequences,
            tools=tuple(dict(tool) for tool in self.tools),
            tool_choice=self.tool_choice,
            structured_output_schema=self.structured_output_schema,
            image_parts=self.image_parts,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Dry-run routing outcome (no lock is created)."""

    rule_id: str
    rule_version: int
    canonical_model_id: str
    fallback_model_id: str | None
    reason: str
    candidates: tuple[dict[str, JSONValue], ...] = ()
    would_lock: bool = True

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "canonical_model_id": self.canonical_model_id,
            "fallback_model_id": self.fallback_model_id,
            "reason": self.reason,
            "candidates": [dict(candidate) for candidate in self.candidates],
            "would_lock": self.would_lock,
        }


class ModelGateway:
    """Single authority: lock routing, endpoint execution, fallback, receipts."""

    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        locks: RouteLockService,
        selector: EndpointSelector,
        coordinator: EndpointExecutionCoordinator,
        clock: Clock | None = None,
        telemetry: Telemetry | None = None,
        matcher: RuleMatcher | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._locks = locks
        self._selector = selector
        self._coordinator = coordinator
        self._clock: Clock = clock or SystemClock()
        self._telemetry = telemetry
        self._matcher = matcher or RuleMatcher()

    # ------------------------------------------------------------------ #
    # Invocation
    # ------------------------------------------------------------------ #

    async def invoke(self, request: InvocationRequest) -> ModelCompletionResult:
        """Route and execute one model invocation with fallback semantics."""
        if not request.task_id.strip():
            raise ModelGatewayValidationError("task_id cannot be empty")
        lock = await self._locks.resolve_or_create_lock(request.match_context())
        rule = await self._rule_for(lock)
        try:
            result = await self._coordinator.execute(
                request.provider_request(),
                lock=lock,
                task_id=request.task_id,
                role=request.role,
            )
        except ProviderFailure as failure:
            if failure.kind not in FALLBACK_ELIGIBLE_KINDS:
                await self._record_failed_receipt(request, lock, failure)
                raise
            if rule is None or not rule.fallback_model_id:
                await self._record_failed_receipt(request, lock, failure)
                raise
            fallback_lock = await self._locks.create_fallback_lock(
                scope_type=lock.scope_type,
                scope_id=lock.scope_id,
                canonical_model_id=rule.fallback_model_id,
                reason=f"fallback after {failure.kind}: {failure.message}",
                source_lock_id=lock.lock_id,
            )
            try:
                result = await self._coordinator.execute(
                    request.provider_request(),
                    lock=fallback_lock,
                    task_id=request.task_id,
                    role=request.role,
                )
            except ProviderFailure as fallback_failure:
                await self._record_failed_receipt(request, lock, fallback_failure)
                raise ModelInvocationFailed(
                    "invocation failed on both the primary and fallback models",
                    attempts=2,
                    last_kind=fallback_failure.kind,
                    context={
                        "primary_model": lock.canonical_model_id,
                        "fallback_model": rule.fallback_model_id,
                        "primary_error_kind": failure.kind,
                    },
                ) from fallback_failure
            result = replace(
                result,
                fallback_used=True,
                fallback_reason=failure.kind,
                canonical_model_id=fallback_lock.canonical_model_id,
                route_lock_id=fallback_lock.lock_id,
                rule_id=fallback_lock.routing_snapshot.rule_id,
                rule_version=fallback_lock.routing_snapshot.rule_version,
            )
            await self._record_receipt(request, fallback_lock, result, failure.kind)
            return result
        await self._record_receipt(request, lock, result, None)
        return result

    # ------------------------------------------------------------------ #
    # Routing operations
    # ------------------------------------------------------------------ #

    async def simulate(self, context: RuleMatchContext) -> RouteDecision:
        """Dry-run a routing decision without creating a lock."""
        rule = self._matcher.find_first_match(
            await self._locks.current_ruleset(), context
        )
        if rule is None:
            raise NoMatchingRuleError(
                "no enabled routing rule matches the request context",
                context={
                    "scope_type": context.scope_type,
                    "scope_id": context.scope_id,
                },
            )
        async with self._scope_factory() as scope:
            model = await scope.store().get_model(rule.canonical_model_id)
        if model is not None and not model.enabled:
            raise CanonicalModelDisabledError(
                f"canonical model {rule.canonical_model_id!r} is disabled",
                context={"canonical_model_id": rule.canonical_model_id},
            )
        candidates: tuple[dict[str, JSONValue], ...] = ()
        try:
            async with self._scope_factory() as scope:
                selected = await self._selector.select(
                    scope.store(), rule.canonical_model_id, now=self._clock.now()
                )
            candidates = tuple(
                {
                    "endpoint_id": candidate.endpoint_id,
                    "binding_id": candidate.binding_id,
                    "provider_name": candidate.provider_name,
                    "provider_model_id": candidate.provider_model_id,
                    "score": candidate.score,
                }
                for candidate in selected
            )
        except SameModelEndpointExhausted:
            candidates = ()
        return RouteDecision(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            canonical_model_id=rule.canonical_model_id,
            fallback_model_id=rule.fallback_model_id,
            reason=rule.description or f"matched rule {rule.rule_id}",
            candidates=candidates,
        )

    async def _rule_for(self, lock: RouteLockRecord) -> RoutingRule | None:
        """Load the rule that produced the lock (for its fallback target)."""
        if lock.routing_snapshot.rule_id == "fallback":
            return None
        async with self._scope_factory() as scope:
            row = await scope.store().get_rule(lock.routing_snapshot.rule_id)
        return row.to_domain_rule() if row else None

    # ------------------------------------------------------------------ #
    # Receipts (diagnostics only — never break routing)
    # ------------------------------------------------------------------ #

    async def _record_receipt(
        self,
        request: InvocationRequest,
        lock: RouteLockRecord,
        result: ModelCompletionResult | None,
        fallback_reason: str | None,
    ) -> None:
        """Write the durable receipt; failures are swallowed by design."""
        try:
            row = _receipt_row(request, lock, result, fallback_reason)
            async with self._scope_factory() as scope:
                await scope.store().insert_receipt(row)
                await scope.commit()
        except Exception:  # noqa: BLE001 - receipts must never break routing
            if self._telemetry is not None:
                self._telemetry.emit_event(
                    "model_gateway.receipt.write_failed",
                    attributes={"task_id": request.task_id},
                )

    async def _record_failed_receipt(
        self, request: InvocationRequest, lock: RouteLockRecord, failure: ProviderFailure
    ) -> None:
        await self._record_receipt(request, lock, None, failure.kind)


def _receipt_row(
    request: InvocationRequest,
    lock: RouteLockRecord,
    result: ModelCompletionResult | None,
    fallback_reason: str | None,
) -> ReceiptRow:
    now = utc_now()
    return ReceiptRow(
        id=f"rcpt-{uuid4().hex[:12]}",
        task_id=request.task_id,
        role=request.role,
        route_lock_id=lock.lock_id,
        rule_id=lock.routing_snapshot.rule_id,
        rule_version=lock.routing_snapshot.rule_version,
        provider_id=result.provider_name if result else "",
        canonical_model_id=result.canonical_model_id if result else lock.canonical_model_id,
        provider_model_id=result.provider_model_id if result else "",
        endpoint_id=result.endpoint_id if result else "",
        fallback_used=bool(result.fallback_used) if result else lock.is_fallback,
        fallback_reason=fallback_reason
        if fallback_reason is not None
        else (lock.routing_snapshot.reason if lock.is_fallback else None),
        status="success" if result else "failed",
        error_code=None if result else (fallback_reason or "unknown"),
        started_at=now,
        completed_at=now,
        created_at=now,
    )
