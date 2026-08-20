"""Provider management application service (Phase 10).

``ProviderManagementService`` is the neutral application seam over the
``ProviderManagementRepositoryPort``. It owns the add-provider flow (vendor +
optional credential + endpoint, atomic), provider reads, and the independent
per-role ModelRule upsert/load. It never touches storage/ORM directly and never
returns raw credential material.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from windagent_core.contracts.providers.provider_management import (
    ModelRuleRecord,
    ProviderAuditEvent,
    ProviderCredentialRecord,
    ProviderEndpointRecord,
    ProviderManagementRepositoryPort,
    ProviderVendorRecord,
)


class ProviderAlreadyExistsError(Exception):
    """Raised when adding a provider whose vendor id already exists."""

    def __init__(self, vendor_id: str):
        super().__init__(f"Provider '{vendor_id}' already exists")
        self.vendor_id = vendor_id


class ProviderManagementService:
    """Application service for provider vendor/credential/endpoint/rule authority."""

    def __init__(self, repository: ProviderManagementRepositoryPort) -> None:
        self._repository = repository

    # ------------------------------------------------------------------ #
    # Add provider (atomic vendor + optional credential + endpoint)
    # ------------------------------------------------------------------ #
    def add_provider(
        self,
        *,
        vendor_id: str,
        name: str,
        vendor_type: str = "cloud",
        base_url: str,
        protocol_mode: str = "openai",
        credential_secret: Optional[str] = None,
        credential_label: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        supports_model_discovery: bool = True,
        supports_openai_compatible: bool = True,
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Atomically add a vendor plus optional credential plus endpoint.

        The raw ``credential_secret`` is encrypted at rest by the repository and
        never returned. Returns a public provider summary (no secrets).
        """
        if self._repository.get_provider(vendor_id) is not None:
            raise ProviderAlreadyExistsError(vendor_id)

        vendor = ProviderVendorRecord(
            id=vendor_id,
            name=name,
            vendor_type=vendor_type,
            supports_model_discovery=supports_model_discovery,
            supports_openai_compatible=supports_openai_compatible,
        )
        credential: Optional[ProviderCredentialRecord] = None
        if credential_secret is not None:
            credential = ProviderCredentialRecord(
                id=f"cred-{uuid.uuid4().hex[:12]}",
                vendor_id=vendor_id,
                label=credential_label or f"{name} credential",
                secret_ciphertext=credential_secret,  # repository encrypts at rest
            )
        endpoint = ProviderEndpointRecord(
            id=endpoint_id or f"ep-{vendor_id}-{uuid.uuid4().hex[:6]}",
            vendor_id=vendor_id,
            credential_id=credential.id if credential else None,
            base_url=base_url,
            protocol_mode=protocol_mode,
        )
        self._repository.add_provider(vendor, credential, endpoint)
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.add",
                vendor_id=vendor_id,
                endpoint_id=endpoint.id,
                reason="provider registered with endpoint",
                actor=actor,
                metadata={"protocol_mode": protocol_mode, "vendor_type": vendor_type},
            )
        )
        return self.get_provider(vendor_id)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_provider(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        vendor = self._repository.get_provider(vendor_id)
        if vendor is None:
            return None
        endpoints = self._repository.list_endpoints(vendor_id)
        endpoint_statuses = [_endpoint_status(ep.test_status) for ep in endpoints]
        if "healthy" in endpoint_statuses:
            provider_status = "healthy"
        elif "offline" in endpoint_statuses:
            provider_status = "offline"
        else:
            provider_status = "unconfigured"
        return {
            "id": vendor.id,
            "display_name": vendor.name,
            "type": vendor.vendor_type,
            "status": provider_status if vendor.enabled else "offline",
            "capabilities": [],
            "endpoints": [
                {
                    "id": ep.id,
                    "provider_id": ep.vendor_id,
                    "name": ep.id,
                    "base_url": ep.base_url,
                    "status": _endpoint_status(ep.test_status),
                    "latency_ms": ep.latency_ms,
                    "rate_limit_rpm": 0,
                    "rate_limit_tpm": 0,
                    "credential_reference": (
                        f"cred:{ep.credential_id}" if ep.credential_id else ""
                    ),
                    "is_configured": ep.credential_id is not None,
                    "models_count": ep.models_count,
                    "last_checked_at": (
                        ep.last_tested_at.isoformat() if ep.last_tested_at else ""
                    ),
                }
                for ep in endpoints
            ],
            "models_count": sum(ep.models_count for ep in endpoints),
            "has_credentials": any(ep.credential_id for ep in endpoints),
            "created_at": vendor.created_at.isoformat(),
            "updated_at": vendor.updated_at.isoformat(),
        }

    def list_providers(self) -> List[Dict[str, Any]]:
        return [self.get_provider(v.id) for v in self._repository.list_providers()]

    def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        ep = self._repository.get_endpoint(endpoint_id)
        if ep is None:
            return None
        return {
            "id": ep.id,
            "provider_id": ep.vendor_id,
            "name": ep.id,
            "base_url": ep.base_url,
            "status": _endpoint_status(ep.test_status),
            "latency_ms": ep.latency_ms,
            "rate_limit_rpm": 0,
            "rate_limit_tpm": 0,
            "credential_reference": f"cred:{ep.credential_id}" if ep.credential_id else "",
            "is_configured": ep.credential_id is not None,
            "models_count": ep.models_count,
            "last_checked_at": ep.last_tested_at.isoformat() if ep.last_tested_at else "",
        }

    def list_discovered_models(self, vendor_id: str) -> List[Dict[str, Any]]:
        return self._repository.list_discovered_models(vendor_id)

    # ------------------------------------------------------------------ #
    # Model rules
    # ------------------------------------------------------------------ #
    def upsert_model_rule(
        self,
        *,
        role: str,
        name: str,
        primary_canonical_model_id: str,
        fallback_canonical_model_id: Optional[str] = None,
        description: Optional[str] = None,
        enabled: bool = True,
        priority: int = 1,
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Upsert one independent ModelRule per role/model mapping."""
        rule = self._repository.upsert_model_rule(
            ModelRuleRecord(
                role=role,
                name=name,
                primary_canonical_model_id=primary_canonical_model_id,
                fallback_canonical_model_id=fallback_canonical_model_id,
                description=description,
                enabled=enabled,
                priority=priority,
            )
        )
        self._repository.record_audit(
            ProviderAuditEvent(
                action="rule.assign",
                role=role,
                canonical_model_id=primary_canonical_model_id,
                reason="model rule assigned to role",
                actor=actor,
                metadata={"enabled": enabled, "priority": priority},
            )
        )
        return self._rule_to_dict(rule)

    def list_enabled_model_rules(self) -> List[Dict[str, Any]]:
        return [
            self._rule_to_dict(r)
            for r in self._repository.list_enabled_model_rules()
        ]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _rule_to_dict(r: ModelRuleRecord) -> Dict[str, Any]:
        return {
            "role": r.role,
            "name": r.name,
            "description": r.description,
            "primary_canonical_model_id": r.primary_canonical_model_id,
            "fallback_canonical_model_id": r.fallback_canonical_model_id,
            "enabled": r.enabled,
            "priority": r.priority,
            "policy_json": r.policy_json,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }


def _endpoint_status(test_status: str) -> str:
    if test_status == "pass":
        return "healthy"
    if test_status == "fail":
        return "offline"
    return "unconfigured"


__all__ = [
    "ProviderAlreadyExistsError",
    "ProviderManagementService",
]
