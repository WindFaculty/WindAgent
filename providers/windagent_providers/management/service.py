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


class ProviderVendorNotFoundError(Exception):
    """Raised when a management mutation targets an unknown vendor."""

    def __init__(self, vendor_id: str):
        super().__init__(f"Provider '{vendor_id}' not found")
        self.vendor_id = vendor_id


class ProviderInUseError(Exception):
    """Raised when deleting a provider still referenced by model routing rules.

    ``blocking_rules`` lists the enabled rules (role/name/model ids) that must
    be resolved by the user first — deletion never cascades silently.
    """

    def __init__(self, vendor_id: str, blocking_rules: List[Dict[str, Any]]):
        super().__init__(
            f"Provider '{vendor_id}' is still referenced by "
            f"{len(blocking_rules)} enabled routing rule(s)"
        )
        self.vendor_id = vendor_id
        self.blocking_rules = blocking_rules


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
    # Lifecycle (P0.1): update / enable-disable / delete / credentials
    # ------------------------------------------------------------------ #
    def update_provider(
        self,
        vendor_id: str,
        *,
        name: Optional[str] = None,
        base_url: Optional[str] = None,
        protocol_mode: Optional[str] = None,
        enabled: Optional[bool] = None,
        supports_model_discovery: Optional[bool] = None,
        supports_openai_compatible: Optional[bool] = None,
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Edit provider identity/endpoint/enabled state. Never touches secrets."""
        vendor = self._repository.update_provider(
            vendor_id,
            name=name,
            enabled=enabled,
            supports_model_discovery=supports_model_discovery,
            supports_openai_compatible=supports_openai_compatible,
        )
        if vendor is None:
            raise ProviderVendorNotFoundError(vendor_id)
        if base_url is not None or protocol_mode is not None:
            for ep in self._repository.list_endpoints(vendor_id):
                self._repository.update_endpoint(
                    ep.id, base_url=base_url, protocol_mode=protocol_mode
                )
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.update",
                vendor_id=vendor_id,
                reason="provider configuration edited",
                actor=actor,
                metadata={
                    key: value
                    for key, value in {
                        "name": name,
                        "base_url": base_url,
                        "protocol_mode": protocol_mode,
                        "enabled": enabled,
                    }.items()
                    if value is not None
                },
            )
        )
        return self.get_provider(vendor_id)

    def delete_provider(
        self,
        vendor_id: str,
        *,
        allow_disabling_rules: bool = False,
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Delete a provider after an explicit routing-rule dependency check.

        Fails with :class:`ProviderInUseError` while any ENABLED rule still
        references one of the provider's bound canonical models. With
        ``allow_disabling_rules=True`` those conflicting rules are disabled
        first — an explicit user decision recorded in the audit log, never a
        silent cascade.
        """
        if self._repository.get_provider(vendor_id) is None:
            raise ProviderVendorNotFoundError(vendor_id)

        bound_ids = set(self._repository.list_bound_canonical_ids(vendor_id))
        blocking: List[Dict[str, Any]] = []
        if bound_ids:
            for rule in self._repository.list_model_rules(include_disabled=False):
                referenced = (
                    rule.primary_canonical_model_id in bound_ids
                    or (
                        rule.fallback_canonical_model_id is not None
                        and rule.fallback_canonical_model_id in bound_ids
                    )
                )
                if referenced:
                    blocking.append(
                        {
                            "role": rule.role,
                            "name": rule.name,
                            "primary_canonical_model_id": rule.primary_canonical_model_id,
                            "fallback_canonical_model_id": rule.fallback_canonical_model_id,
                        }
                    )

        disabled_roles: List[str] = []
        if blocking:
            if not allow_disabling_rules:
                raise ProviderInUseError(vendor_id, blocking)
            disabled_roles = [rule["role"] for rule in blocking]
            self._repository.set_rules_enabled(disabled_roles, enabled=False)
            for role in disabled_roles:
                self._repository.record_audit(
                    ProviderAuditEvent(
                        action="rule.disable",
                        vendor_id=vendor_id,
                        role=role,
                        reason="provider deleted; dependent routing rule disabled",
                        actor=actor,
                    )
                )

        counts = self._repository.delete_vendor(vendor_id)
        self._repository.record_audit(
            ProviderAuditEvent(
                action="provider.delete",
                vendor_id=vendor_id,
                reason=(
                    f"provider deleted; {counts['endpoints']} endpoint(s), "
                    f"{counts['bindings']} binding(s), {len(disabled_roles)} "
                    "dependent rule(s) disabled"
                ),
                actor=actor,
                metadata={"removed_rows": counts, "disabled_rule_roles": disabled_roles},
            )
        )
        return {
            "provider_id": vendor_id,
            "deleted": counts.get("vendors", 0) > 0,
            "removed_endpoints": counts.get("endpoints", 0),
            "removed_credentials": counts.get("credentials", 0),
            "removed_bindings": counts.get("bindings", 0),
            "disabled_rule_roles": disabled_roles,
        }

    def rotate_credential(
        self,
        vendor_id: str,
        secret: str,
        label: Optional[str] = None,
        *,
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Create or rotate the credential; raw secret encrypted at rest."""
        if self._repository.get_provider(vendor_id) is None:
            raise ProviderVendorNotFoundError(vendor_id)
        record = self._repository.upsert_credential(vendor_id, secret, label)
        summary = self._repository.get_credential_summary(vendor_id) or {}
        self._repository.record_audit(
            ProviderAuditEvent(
                action="credential.rotate",
                vendor_id=vendor_id,
                reason=f"credential rotated to version {record.secret_version}",
                actor=actor,
                metadata={"label": record.label, "secret_version": record.secret_version},
            )
        )
        return {
            "provider_id": vendor_id,
            "configured": True,
            "credential_reference": f"cred:{record.id}",
            "label": summary.get("label", record.label),
            "secret_version": record.secret_version,
            "updated_at": summary.get("updated_at", ""),
        }

    def remove_credential(self, vendor_id: str, *, actor: str = "system") -> Dict[str, Any]:
        """Detach and delete the vendor credential (write-only secret removed)."""
        if self._repository.get_provider(vendor_id) is None:
            raise ProviderVendorNotFoundError(vendor_id)
        removed = self._repository.remove_credentials(vendor_id)
        self._repository.record_audit(
            ProviderAuditEvent(
                action="credential.remove",
                vendor_id=vendor_id,
                reason=f"{removed} credential row(s) removed",
                actor=actor,
            )
        )
        return {
            "provider_id": vendor_id,
            "configured": False,
            "credential_reference": "",
            "label": None,
            "secret_version": 0,
            "updated_at": "",
        }

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_provider(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        vendor = self._repository.get_provider(vendor_id)
        if vendor is None:
            return None
        endpoints = self._repository.list_endpoints(vendor_id)
        credential_summary = self._repository.get_credential_summary(vendor_id) or {}
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
            "enabled": vendor.enabled,
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
                    "credential_label": (
                        credential_summary.get("label")
                        if ep.credential_id
                        and credential_summary.get("credential_reference")
                        == f"cred:{ep.credential_id}"
                        else None
                    ),
                    "credential_updated_at": (
                        credential_summary.get("updated_at")
                        if ep.credential_id
                        and credential_summary.get("credential_reference")
                        == f"cred:{ep.credential_id}"
                        else None
                    ),
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

    def list_all_discovered_models(self) -> List[Dict[str, Any]]:
        """Whole durable registry across every vendor (/api/v3/models source)."""
        return self._repository.list_all_discovered_models()

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
