"""Durable row and read-model records for the model gateway.

Rows are the store-port data shapes (one per table family); views are what
the API layer serializes.  Views never contain credential material — the
write-only credential contract is enforced structurally here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..domain.normalization import EquivalenceLevel
from ..domain.route_lock import RouteLockRecord
from ..domain.rules import RoutingRule

AVAILABILITY_ACTIVE = "active"
AVAILABILITY_UNAVAILABLE = "unavailable"
AVAILABILITY_DEPRECATED = "deprecated"

TEST_STATUS_UNTESTED = "untested"
TEST_STATUS_PASS = "pass"
TEST_STATUS_FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ProviderRow:
    """One physical provider vendor."""

    id: str
    name: str
    display_name: str
    vendor_type: str
    base_url: str
    protocol_mode: str
    supports_model_discovery: bool = True
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EndpointRow:
    """One callable base URL belonging to a provider."""

    id: str
    provider_id: str
    base_url: str
    protocol_mode: str
    priority: int = 50
    weight: int = 100
    enabled: bool = True
    test_status: str = TEST_STATUS_UNTESTED
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CredentialRow:
    """Metadata for one stored provider credential.

    The secret itself lives only in the platform ``SecretStore`` under
    ``secret_name``; this row can never expose it.
    """

    id: str
    provider_id: str
    secret_name: str
    secret_version: int = 1
    label: str = ""
    created_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CanonicalModelRow:
    """One entry of the canonical model catalog."""

    canonical_name: str
    vendor: str
    family: str
    revision: str | None = None
    quantization: str | None = None
    parameter_size: str | None = None
    equivalence_fingerprint: str = ""
    context_window: int | None = None
    capabilities: tuple[str, ...] = ()
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BindingRow:
    """One endpoint↔canonical-model binding."""

    id: str
    endpoint_id: str
    canonical_model_id: str
    provider_model_id: str
    equivalence_level: str = EquivalenceLevel.EXACT_REVISION.value
    equivalence_fingerprint: str = ""
    pricing_class: str = "UNKNOWN"
    priority: int = 50
    availability: str = AVAILABILITY_ACTIVE
    is_active: bool = True
    last_discovered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SelectableBinding:
    """A binding enriched with its endpoint and provider for selection."""

    binding_id: str
    endpoint_id: str
    provider_name: str
    provider_id: str
    provider_model_id: str
    base_url: str
    protocol_mode: str
    equivalence_level: str
    endpoint_enabled: bool
    binding_enabled: bool
    has_credential: bool
    credential_secret_name: str | None = None


@dataclass(frozen=True, slots=True)
class RuleRow:
    """One durable routing rule."""

    rule_id: str
    rule_version: int
    canonical_model_id: str
    fallback_model_id: str | None = None
    description: str = ""
    enabled: bool = True
    priority: int = 50
    task_labels: tuple[str, ...] = ()
    agent_types: tuple[str, ...] = ()
    workflow_types: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    min_context_tokens: int = 0
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: tuple[str, ...] = ()
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_domain_rule(self) -> RoutingRule:
        """Project the durable row onto the domain rule value object."""
        return RoutingRule(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            canonical_model_id=self.canonical_model_id,
            fallback_model_id=self.fallback_model_id,
            description=self.description,
            enabled=self.enabled,
            priority=self.priority,
            task_labels=self.task_labels,
            agent_types=self.agent_types,
            workflow_types=self.workflow_types,
            required_capabilities=self.required_capabilities,
            min_context_tokens=self.min_context_tokens,
            requires_tools=self.requires_tools,
            requires_vision=self.requires_vision,
            cost_classes=self.cost_classes,
            requires_local=self.requires_local,
            requires_private=self.requires_private,
            user_preference_model=self.user_preference_model,
        )


@dataclass(frozen=True, slots=True)
class AttemptRow:
    """One execution attempt against one endpoint binding."""

    id: str
    route_lock_id: str
    endpoint_id: str
    binding_id: str
    attempt_index: int
    status: str
    error_class: str | None = None
    http_status: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ReceiptRow:
    """The durable per-invocation routing receipt (old P0.3.6 semantics)."""

    id: str
    task_id: str
    role: str | None
    route_lock_id: str
    rule_id: str
    rule_version: int
    provider_id: str
    canonical_model_id: str
    provider_model_id: str
    endpoint_id: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    status: str = "success"
    error_code: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderView:
    """API read model of a provider (never carries credential material)."""

    id: str
    name: str
    display_name: str
    vendor_type: str
    base_url: str
    protocol_mode: str
    supports_model_discovery: bool
    enabled: bool
    endpoint_count: int = 0
    has_credential: bool = False
    model_count: int = 0

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "vendor_type": self.vendor_type,
            "base_url": self.base_url,
            "protocol_mode": self.protocol_mode,
            "supports_model_discovery": self.supports_model_discovery,
            "enabled": self.enabled,
            "endpoint_count": self.endpoint_count,
            "has_credential": self.has_credential,
            "model_count": self.model_count,
        }


@dataclass(frozen=True, slots=True)
class CredentialView:
    """Write-only credential surface: metadata only, never the secret."""

    id: str
    provider_id: str
    label: str
    secret_version: int
    created_at: datetime | None = None
    revoked_at: datetime | None = None

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        payload: dict[str, object] = {
            "id": self.id,
            "provider_id": self.provider_id,
            "label": self.label,
            "secret_version": self.secret_version,
            "has_secret": True,
        }
        if self.created_at is not None:
            payload["created_at"] = self.created_at.isoformat()
        if self.revoked_at is not None:
            payload["revoked_at"] = self.revoked_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class EndpointView:
    """API read model of an endpoint."""

    id: str
    provider_id: str
    base_url: str
    protocol_mode: str
    priority: int
    weight: int
    enabled: bool
    test_status: str

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "base_url": self.base_url,
            "protocol_mode": self.protocol_mode,
            "priority": self.priority,
            "weight": self.weight,
            "enabled": self.enabled,
            "test_status": self.test_status,
        }


@dataclass(frozen=True, slots=True)
class ModelView:
    """API read model of a canonical model with its bindings."""

    canonical_name: str
    vendor: str
    family: str
    revision: str | None
    context_window: int | None
    capabilities: tuple[str, ...]
    enabled: bool
    bindings: tuple[dict[str, object], ...] = ()

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        payload: dict[str, object] = {
            "canonical_name": self.canonical_name,
            "vendor": self.vendor,
            "family": self.family,
            "revision": self.revision,
            "context_window": self.context_window,
            "capabilities": list(self.capabilities),
            "enabled": self.enabled,
            "bindings": [dict(binding) for binding in self.bindings],
        }
        return payload


@dataclass(frozen=True, slots=True)
class RuleView:
    """API read model of a routing rule."""

    rule_id: str
    rule_version: int
    canonical_model_id: str
    fallback_model_id: str | None
    description: str
    enabled: bool
    priority: int
    task_labels: tuple[str, ...]
    agent_types: tuple[str, ...]
    workflow_types: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    min_context_tokens: int
    requires_tools: bool
    requires_vision: bool
    cost_classes: tuple[str, ...]
    requires_local: bool
    requires_private: bool
    user_preference_model: str | None

    @classmethod
    def from_row(cls, row: RuleRow) -> RuleView:
        """Project a durable row."""
        return cls(
            rule_id=row.rule_id,
            rule_version=row.rule_version,
            canonical_model_id=row.canonical_model_id,
            fallback_model_id=row.fallback_model_id,
            description=row.description,
            enabled=row.enabled,
            priority=row.priority,
            task_labels=row.task_labels,
            agent_types=row.agent_types,
            workflow_types=row.workflow_types,
            required_capabilities=row.required_capabilities,
            min_context_tokens=row.min_context_tokens,
            requires_tools=row.requires_tools,
            requires_vision=row.requires_vision,
            cost_classes=row.cost_classes,
            requires_local=row.requires_local,
            requires_private=row.requires_private,
            user_preference_model=row.user_preference_model,
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "canonical_model_id": self.canonical_model_id,
            "fallback_model_id": self.fallback_model_id,
            "description": self.description,
            "enabled": self.enabled,
            "priority": self.priority,
            "task_labels": list(self.task_labels),
            "agent_types": list(self.agent_types),
            "workflow_types": list(self.workflow_types),
            "required_capabilities": list(self.required_capabilities),
            "min_context_tokens": self.min_context_tokens,
            "requires_tools": self.requires_tools,
            "requires_vision": self.requires_vision,
            "cost_classes": list(self.cost_classes),
            "requires_local": self.requires_local,
            "requires_private": self.requires_private,
            "user_preference_model": self.user_preference_model,
        }


@dataclass(frozen=True, slots=True)
class ReceiptView:
    """API read model of a routing receipt."""

    id: str
    task_id: str
    role: str | None
    route_lock_id: str
    rule_id: str
    rule_version: int
    provider_id: str
    canonical_model_id: str
    provider_model_id: str
    endpoint_id: str
    fallback_used: bool
    fallback_reason: str | None
    status: str
    error_code: str | None

    @classmethod
    def from_row(cls, row: ReceiptRow) -> ReceiptView:
        """Project a durable row."""
        return cls(
            id=row.id,
            task_id=row.task_id,
            role=row.role,
            route_lock_id=row.route_lock_id,
            rule_id=row.rule_id,
            rule_version=row.rule_version,
            provider_id=row.provider_id,
            canonical_model_id=row.canonical_model_id,
            provider_model_id=row.provider_model_id,
            endpoint_id=row.endpoint_id,
            fallback_used=row.fallback_used,
            fallback_reason=row.fallback_reason,
            status=row.status,
            error_code=row.error_code,
        )

    def to_payload(self) -> dict[str, object]:
        """Serialize for transport."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "role": self.role,
            "route_lock_id": self.route_lock_id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "provider_id": self.provider_id,
            "canonical_model_id": self.canonical_model_id,
            "provider_model_id": self.provider_model_id,
            "endpoint_id": self.endpoint_id,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "status": self.status,
            "error_code": self.error_code,
        }


def lock_view(lock: RouteLockRecord) -> dict[str, object]:
    """Serialize a route lock for transport."""
    payload: dict[str, Any] = lock.to_dict()
    return {key: _freeze(value) for key, value in payload.items()}


def _freeze(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {key: _freeze(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_freeze(item) for item in value]
    return str(value)


@dataclass(frozen=True, slots=True)
class QuotaStateRecord:
    """Durable per-provider quota observation."""

    provider_name: str
    has_quota: bool = True
    remaining_requests_today: int | None = None
    remaining_tokens_today: int | None = None
    reset_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryReconciliation:
    """Outcome of one discovery-snapshot reconciliation (never deletes)."""

    added: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
