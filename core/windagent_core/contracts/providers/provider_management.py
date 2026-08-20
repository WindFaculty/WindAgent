"""Neutral provider-management contracts for WindAgent Core (Phase 10).

Core owns the provider-management data records and the repository port.
Provider infrastructure services depend only on these records/ports; the
concrete SQL repository lives in ``windagent_storage`` and is injected by the
API/Worker composition roots. Provider infrastructure never imports storage/ORM.

Security invariants enforced by the repository implementation:
- raw credentials are encrypted at rest (``enc:v1:`` ciphertext) and never
  returned by any read path;
- endpoint probe material (including the credential ciphertext) is exposed
  only through ``get_probe_material`` — the trusted service/composition seam;
- audit events are redacted before persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from windagent_core.contracts.providers.capabilities import DiscoveredModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass
class ProviderVendorRecord:
    """A physical provider vendor (cloud, local, or custom)."""

    id: str
    name: str
    vendor_type: str = "cloud"  # cloud | local | custom
    supports_model_discovery: bool = True
    supports_openai_compatible: bool = True
    enabled: bool = True
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass
class ProviderCredentialRecord:
    """A credential bound to a vendor. The secret is always ciphertext."""

    id: str
    vendor_id: str
    label: str
    secret_ciphertext: Optional[str] = None  # enc:v1:... — never plaintext
    secret_version: int = 1
    is_env_ref: bool = False
    env_var_name: Optional[str] = None
    enabled: bool = True
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass
class ProviderEndpointRecord:
    """A physical network endpoint for a provider vendor."""

    id: str
    vendor_id: str
    credential_id: Optional[str] = None
    base_url: str = ""
    protocol_mode: str = "openai"  # openai | anthropic | gemini | ollama
    configured_protocol: Optional[str] = None
    detected_protocol: Optional[str] = None
    protocol_confidence: float = 1.0
    region: str = "global"
    priority: int = 50
    weight: int = 100
    enabled: bool = True
    test_status: str = "untested"  # untested | pass | fail
    latency_ms: float = 0.0
    models_count: int = 0
    last_tested_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass
class ModelRuleRecord:
    """One independent role -> canonical model routing rule (per role)."""

    role: str
    name: str
    primary_canonical_model_id: str
    fallback_canonical_model_id: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 1
    policy_json: str = "{}"
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass
class ProviderProbeMaterial:
    """Endpoint probe material exposed ONLY to the trusted service seam.

    Carries the credential ciphertext so the probe service can build a real
    adapter. This record must never cross an API/UI boundary.
    """

    endpoint_id: str
    vendor_id: str
    vendor_name: str
    base_url: str
    protocol_mode: str
    credential_ciphertext: Optional[str] = None
    provider_name: str = "openai_compatible"


@dataclass
class ProviderProbeResult:
    """Server-derived result of a real adapter health probe + model discovery."""

    endpoint_id: str
    reachable: bool
    latency_ms: float
    auth_valid: bool
    error_code: Optional[str] = None
    message: str = ""
    discovered_models: List[str] = field(default_factory=list)
    completed_at: datetime = field(default_factory=_utc_now)


@dataclass
class ProviderAuditEvent:
    """Redacted durable audit event for provider add/probe/discovery/rule."""

    action: str  # provider.add | provider.probe | provider.discovery | rule.assign
    vendor_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    role: Optional[str] = None
    canonical_model_id: Optional[str] = None
    reason: Optional[str] = None
    actor: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Repository port
# ---------------------------------------------------------------------------


@runtime_checkable
class ProviderManagementRepositoryPort(Protocol):
    """Durable provider vendor/credential/endpoint/model-rule authority.

    Implemented by ``SQLProviderManagementRepository`` in ``windagent_storage``.
    All methods are synchronous (matching the existing routing repository
    pattern); services wrap them in their own transaction boundaries.
    """

    # -- vendor + credential + endpoint ------------------------------------ #
    def add_provider(
        self,
        vendor: ProviderVendorRecord,
        credential: Optional[ProviderCredentialRecord],
        endpoint: ProviderEndpointRecord,
    ) -> ProviderVendorRecord:
        """Atomically add a vendor plus optional credential plus endpoint."""
        ...

    def get_provider(self, vendor_id: str) -> Optional[ProviderVendorRecord]:
        """Return a vendor record (never any credential secret)."""
        ...

    def list_providers(self) -> List[ProviderVendorRecord]:
        """Return all vendor records (never any credential secret)."""
        ...

    def get_endpoint(self, endpoint_id: str) -> Optional[ProviderEndpointRecord]:
        """Return an endpoint record (never any credential secret)."""
        ...

    def list_endpoints(self, vendor_id: str) -> List[ProviderEndpointRecord]:
        """Return all endpoints for a vendor (never any credential secret)."""
        ...

    # -- probe material + probe status ------------------------------------- #
    def get_probe_material(self, endpoint_id: str) -> Optional[ProviderProbeMaterial]:
        """Return endpoint probe material (credential ciphertext) to the trusted seam."""
        ...

    def record_probe_result(self, endpoint_id: str, result: ProviderProbeResult) -> None:
        """Persist probe status/timestamp for an endpoint."""
        ...

    # -- discovered model bindings ----------------------------------------- #
    def register_discovered_models(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> List[Dict[str, Any]]:
        """Persist discovered endpoint/model bindings; return binding records."""
        ...

    def list_discovered_models(self, vendor_id: str) -> List[Dict[str, Any]]:
        """List canonical models and bindings discovered for one vendor."""
        ...

    # -- model rules -------------------------------------------------------- #
    def upsert_model_rule(self, rule: ModelRuleRecord) -> ModelRuleRecord:
        """Upsert one independent ModelRule per role/model mapping."""
        ...

    def list_enabled_model_rules(self) -> List[ModelRuleRecord]:
        """Load enabled rules deterministically (priority asc, then role)."""
        ...

    # -- audit -------------------------------------------------------------- #
    def record_audit(self, event: ProviderAuditEvent) -> str:
        """Record a redacted durable audit event."""
        ...


__all__ = [
    "ProviderVendorRecord",
    "ProviderCredentialRecord",
    "ProviderEndpointRecord",
    "ModelRuleRecord",
    "ProviderProbeMaterial",
    "ProviderProbeResult",
    "ProviderAuditEvent",
    "ProviderManagementRepositoryPort",
]
