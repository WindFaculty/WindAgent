"""SQL concrete repository for the provider-management authority (Phase 10).

Implements ``ProviderManagementRepositoryPort`` from
``windagent_core.contracts.providers.provider_management`` over the dedicated
provider SQL tables (``provider_vendors``, ``provider_credentials``,
``provider_endpoints``, ``canonical_models_v3``, ``endpoint_model_bindings``,
``model_routing_rules_v3``, ``provider_routing_audit_v3``).

Security invariants:
- raw credentials are encrypted at rest with the fail-closed AES-GCM utility
  (``windagent_storage.security.encryption.encrypt``) and never returned by any
  read path;
- endpoint probe material (credential ciphertext) is exposed only through
  ``get_probe_material`` — the trusted service/composition seam;
- audit events are redacted before persistence (``redact_before_persist``).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from windagent_core.contracts.providers.capabilities import DiscoveredModel
from windagent_core.contracts.providers.provider_management import (
    ModelRuleRecord,
    ProviderAuditEvent,
    ProviderCredentialRecord,
    ProviderEndpointRecord,
    ProviderManagementRepositoryPort,
    ProviderProbeMaterial,
    ProviderProbeResult,
    ProviderVendorRecord,
)
from windagent_storage.orm.v3_models import (
    CanonicalModelV3ORM,
    EndpointHealthSampleORM,
    EndpointModelBindingORM,
    EndpointRateLimitWindowORM,
    EndpointRuntimeStateORM,
    ModelDiscoverySnapshotORM,
    ModelRoutingRuleV3ORM,
    ProviderCredentialORM,
    ProviderEndpointORM,
    ProviderRoutingAuditV3ORM,
    ProviderVendorORM,
    RouteAttemptV3ORM,
)
from windagent_storage.factory import create_sql_endpoint_binding_repository
from windagent_storage.security.encryption import encrypt


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aggregate_pricing_class(bindings: List[Dict[str, Any]]) -> str:
    """Truthful model-level pricing class from its provider bindings.

    PAID wins over FREE (the model costs money somewhere it is offered);
    UNKNOWN only when NO binding advertises pricing. Never guessed.
    """
    classes = [b.get("pricing_class", "UNKNOWN") for b in bindings]
    if "PAID" in classes:
        return "PAID"
    if "FREE" in classes:
        return "FREE"
    return "UNKNOWN"


class SQLProviderManagementRepository(ProviderManagementRepositoryPort):
    """SQL-backed provider vendor/credential/endpoint/model-rule authority."""

    def __init__(self, session: Session):
        self.session = session
        self._binding_repo = create_sql_endpoint_binding_repository(session)

    # ------------------------------------------------------------------ #
    # Vendor + credential + endpoint
    # ------------------------------------------------------------------ #
    def add_provider(
        self,
        vendor: ProviderVendorRecord,
        credential: Optional[ProviderCredentialRecord],
        endpoint: ProviderEndpointRecord,
    ) -> ProviderVendorRecord:
        try:
            vendor_orm = ProviderVendorORM(
                id=vendor.id,
                name=vendor.name,
                vendor_type=vendor.vendor_type,
                supports_model_discovery=vendor.supports_model_discovery,
                supports_openai_compatible=vendor.supports_openai_compatible,
                enabled=vendor.enabled,
            )
            self.session.add(vendor_orm)
            self.session.flush()

            credential_id: Optional[str] = None
            if credential is not None:
                ciphertext = None
                if credential.secret_ciphertext:
                    # Fail-closed encryption: a raw secret is never stored. If the
                    # caller already passed ciphertext (e.g. re-import), keep it;
                    # otherwise encrypt the raw secret now.
                    if credential.secret_ciphertext.startswith("enc:v1:"):
                        ciphertext = credential.secret_ciphertext
                    else:
                        ciphertext = encrypt(credential.secret_ciphertext)
                cred_orm = ProviderCredentialORM(
                    id=credential.id,
                    vendor_id=vendor.id,
                    label=credential.label,
                    secret_ciphertext=ciphertext,
                    secret_version=credential.secret_version,
                    is_env_ref=credential.is_env_ref,
                    env_var_name=credential.env_var_name,
                    enabled=credential.enabled,
                )
                self.session.add(cred_orm)
                self.session.flush()
                credential_id = credential.id

            endpoint_orm = ProviderEndpointORM(
                id=endpoint.id,
                vendor_id=vendor.id,
                credential_id=credential_id,
                base_url=endpoint.base_url,
                protocol_mode=endpoint.protocol_mode,
                configured_protocol=endpoint.configured_protocol,
                detected_protocol=endpoint.detected_protocol,
                protocol_confidence=endpoint.protocol_confidence,
                region=endpoint.region,
                priority=endpoint.priority,
                weight=endpoint.weight,
                enabled=endpoint.enabled,
                test_status=endpoint.test_status,
                last_tested_at=endpoint.last_tested_at,
            )
            self.session.add(endpoint_orm)
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_provider(vendor.id) or vendor

    def get_provider(self, vendor_id: str) -> Optional[ProviderVendorRecord]:
        row = self.session.query(ProviderVendorORM).filter_by(id=vendor_id).first()
        if row is None:
            return None
        return ProviderVendorRecord(
            id=row.id,
            name=row.name,
            vendor_type=row.vendor_type,
            supports_model_discovery=row.supports_model_discovery,
            supports_openai_compatible=row.supports_openai_compatible,
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_providers(self) -> List[ProviderVendorRecord]:
        rows = self.session.query(ProviderVendorORM).order_by(ProviderVendorORM.name).all()
        return [
            ProviderVendorRecord(
                id=r.id,
                name=r.name,
                vendor_type=r.vendor_type,
                supports_model_discovery=r.supports_model_discovery,
                supports_openai_compatible=r.supports_openai_compatible,
                enabled=r.enabled,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    def get_endpoint(self, endpoint_id: str) -> Optional[ProviderEndpointRecord]:
        row = self.session.query(ProviderEndpointORM).filter_by(id=endpoint_id).first()
        if row is None:
            return None
        return self._endpoint_to_record(row)

    def list_endpoints(self, vendor_id: str) -> List[ProviderEndpointRecord]:
        rows = (
            self.session.query(ProviderEndpointORM)
            .filter_by(vendor_id=vendor_id)
            .order_by(ProviderEndpointORM.priority.desc())
            .all()
        )
        return [self._endpoint_to_record(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Lifecycle mutations (P0.1)
    # ------------------------------------------------------------------ #
    def update_provider(
        self,
        vendor_id: str,
        *,
        name: Optional[str] = None,
        vendor_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        supports_model_discovery: Optional[bool] = None,
        supports_openai_compatible: Optional[bool] = None,
    ) -> Optional[ProviderVendorRecord]:
        row = self.session.query(ProviderVendorORM).filter_by(id=vendor_id).first()
        if row is None:
            return None
        if name is not None:
            row.name = name
        if vendor_type is not None:
            row.vendor_type = vendor_type
        if enabled is not None:
            row.enabled = enabled
        if supports_model_discovery is not None:
            row.supports_model_discovery = supports_model_discovery
        if supports_openai_compatible is not None:
            row.supports_openai_compatible = supports_openai_compatible
        row.updated_at = _utc_now()
        try:
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_provider(vendor_id)

    def update_endpoint(
        self,
        endpoint_id: str,
        *,
        base_url: Optional[str] = None,
        protocol_mode: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[ProviderEndpointRecord]:
        row = self.session.query(ProviderEndpointORM).filter_by(id=endpoint_id).first()
        if row is None:
            return None
        if base_url:
            row.base_url = base_url
        if protocol_mode:
            row.protocol_mode = protocol_mode
        if enabled is not None:
            row.enabled = enabled
        row.updated_at = _utc_now()
        try:
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_endpoint(endpoint_id)

    def delete_vendor(self, vendor_id: str) -> Dict[str, int]:
        """Delete a vendor plus all provider-owned dependent rows atomically.

        Removal order respects FKs: attempts -> runtime state -> rate windows
        -> health samples -> discovery snapshots -> bindings -> endpoints ->
        credentials -> vendor. Canonical model rows are intentionally kept
        (shared identity, not provider-owned). The removed-row counts are
        returned so the service can record them in the audit trail.
        """
        endpoint_ids = [
            row.id
            for row in (
                self.session.query(ProviderEndpointORM.id)
                .filter_by(vendor_id=vendor_id)
                .all()
            )
        ]
        try:
            binding_ids: List[str] = []
            removed_bindings = 0
            if endpoint_ids:
                binding_ids = [
                    row.id
                    for row in (
                        self.session.query(EndpointModelBindingORM.id)
                        .filter(EndpointModelBindingORM.endpoint_id.in_(endpoint_ids))
                        .all()
                    )
                ]
            removed_attempts = 0
            if binding_ids:
                removed_attempts = (
                    self.session.query(RouteAttemptV3ORM)
                    .filter(RouteAttemptV3ORM.provider_binding_id.in_(binding_ids))
                    .delete(synchronize_session=False)
                )
                removed_bindings = (
                    self.session.query(EndpointModelBindingORM)
                    .filter(EndpointModelBindingORM.id.in_(binding_ids))
                    .delete(synchronize_session=False)
                )
            removed_runtime = 0
            removed_rate_windows = 0
            removed_health = 0
            removed_snapshots = 0
            removed_endpoints = 0
            if endpoint_ids:
                removed_runtime = (
                    self.session.query(EndpointRuntimeStateORM)
                    .filter(EndpointRuntimeStateORM.endpoint_id.in_(endpoint_ids))
                    .delete(synchronize_session=False)
                )
                removed_rate_windows = (
                    self.session.query(EndpointRateLimitWindowORM)
                    .filter(EndpointRateLimitWindowORM.endpoint_id.in_(endpoint_ids))
                    .delete(synchronize_session=False)
                )
                removed_health = (
                    self.session.query(EndpointHealthSampleORM)
                    .filter(EndpointHealthSampleORM.endpoint_id.in_(endpoint_ids))
                    .delete(synchronize_session=False)
                )
                removed_snapshots = (
                    self.session.query(ModelDiscoverySnapshotORM)
                    .filter(ModelDiscoverySnapshotORM.endpoint_id.in_(endpoint_ids))
                    .delete(synchronize_session=False)
                )
                removed_endpoints = (
                    self.session.query(ProviderEndpointORM)
                    .filter_by(vendor_id=vendor_id)
                    .delete(synchronize_session=False)
                )
            removed_credentials = (
                self.session.query(ProviderCredentialORM)
                .filter_by(vendor_id=vendor_id)
                .delete(synchronize_session=False)
            )
            removed_vendors = (
                self.session.query(ProviderVendorORM)
                .filter_by(id=vendor_id)
                .delete(synchronize_session=False)
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {
            "vendors": int(removed_vendors),
            "endpoints": int(removed_endpoints),
            "credentials": int(removed_credentials),
            "bindings": int(removed_bindings),
            "health_samples": int(removed_health),
            "discovery_snapshots": int(removed_snapshots),
            "rate_windows": int(removed_rate_windows),
            "runtime_states": int(removed_runtime),
            "route_attempts": int(removed_attempts),
        }

    def list_model_rules(self, *, include_disabled: bool = False) -> List[ModelRuleRecord]:
        query = self.session.query(ModelRoutingRuleV3ORM)
        if not include_disabled:
            query = query.filter_by(enabled=True)
        rows = query.order_by(
            ModelRoutingRuleV3ORM.priority.asc(), ModelRoutingRuleV3ORM.role.asc()
        ).all()
        return [self._rule_to_record(r) for r in rows]

    def set_rules_enabled(self, roles: List[str], *, enabled: bool) -> int:
        if not roles:
            return 0
        changed = (
            self.session.query(ModelRoutingRuleV3ORM)
            .filter(ModelRoutingRuleV3ORM.role.in_(roles))
            .update({"enabled": enabled, "updated_at": _utc_now()}, synchronize_session=False)
        )
        try:
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return int(changed)

    def upsert_credential(
        self, vendor_id: str, secret: str, label: Optional[str] = None
    ) -> ProviderCredentialRecord:
        """Create or rotate the vendor credential; attach to unlinked endpoints.

        The raw ``secret`` is encrypted at rest here and never returned.
        """
        ciphertext = encrypt(secret) if not secret.startswith("enc:v1:") else secret
        existing = (
            self.session.query(ProviderCredentialORM)
            .filter_by(vendor_id=vendor_id)
            .order_by(ProviderCredentialORM.created_at.asc())
            .first()
        )
        try:
            if existing is None:
                existing = ProviderCredentialORM(
                    id=f"cred-{uuid.uuid4().hex[:12]}",
                    vendor_id=vendor_id,
                    label=label or f"{vendor_id} credential",
                    secret_ciphertext=ciphertext,
                )
                self.session.add(existing)
                self.session.flush()
            else:
                existing.secret_ciphertext = ciphertext
                existing.label = label or existing.label
                existing.secret_version = (existing.secret_version or 1) + 1
                existing.enabled = True
                existing.updated_at = _utc_now()
                self.session.flush()
            # Attach the credential to any vendor endpoint missing one so probe
            # material stays consistent after rotation/removal cycles.
            self.session.query(ProviderEndpointORM).filter(
                ProviderEndpointORM.vendor_id == vendor_id,
                ProviderEndpointORM.credential_id.is_(None),
            ).update({"credential_id": existing.id}, synchronize_session=False)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return ProviderCredentialRecord(
            id=existing.id,
            vendor_id=vendor_id,
            label=existing.label,
            secret_ciphertext=existing.secret_ciphertext,
            secret_version=existing.secret_version,
            is_env_ref=existing.is_env_ref,
            env_var_name=existing.env_var_name,
            enabled=existing.enabled,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    def remove_credentials(self, vendor_id: str) -> int:
        """Detach endpoints from credentials then delete the credential rows."""
        try:
            self.session.query(ProviderEndpointORM).filter_by(vendor_id=vendor_id).update(
                {"credential_id": None}, synchronize_session=False
            )
            removed = (
                self.session.query(ProviderCredentialORM)
                .filter_by(vendor_id=vendor_id)
                .delete(synchronize_session=False)
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return int(removed)

    def list_bound_canonical_ids(self, vendor_id: str) -> List[str]:
        rows = (
            self.session.query(EndpointModelBindingORM.canonical_model_id)
            .join(
                ProviderEndpointORM,
                ProviderEndpointORM.id == EndpointModelBindingORM.endpoint_id,
            )
            .filter(ProviderEndpointORM.vendor_id == vendor_id)
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def get_credential_summary(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """Credential metadata only — never any secret material."""
        cred = (
            self.session.query(ProviderCredentialORM)
            .filter_by(vendor_id=vendor_id)
            .order_by(ProviderCredentialORM.created_at.asc())
            .first()
        )
        if cred is None or not cred.secret_ciphertext:
            return None
        return {
            "credential_reference": f"cred:{cred.id}",
            "label": cred.label,
            "secret_version": cred.secret_version,
            "enabled": cred.enabled,
            "created_at": cred.created_at.isoformat(),
            "updated_at": cred.updated_at.isoformat(),
        }

    # ------------------------------------------------------------------ #
    # Probe material + probe status
    # ------------------------------------------------------------------ #
    def get_probe_material(self, endpoint_id: str) -> Optional[ProviderProbeMaterial]:
        ep = self.session.query(ProviderEndpointORM).filter_by(id=endpoint_id).first()
        if ep is None:
            return None
        vendor = self.session.query(ProviderVendorORM).filter_by(id=ep.vendor_id).first()
        ciphertext: Optional[str] = None
        if ep.credential_id:
            cred = (
                self.session.query(ProviderCredentialORM)
                .filter_by(id=ep.credential_id, enabled=True)
                .first()
            )
            if cred is not None:
                ciphertext = cred.secret_ciphertext
        return ProviderProbeMaterial(
            endpoint_id=ep.id,
            vendor_id=ep.vendor_id,
            vendor_name=vendor.name if vendor else ep.vendor_id,
            base_url=ep.base_url,
            protocol_mode=ep.protocol_mode,
            credential_ciphertext=ciphertext,
            provider_name=vendor.name if vendor else ep.vendor_id,
        )

    def record_probe_result(self, endpoint_id: str, result: ProviderProbeResult) -> None:
        ep = self.session.query(ProviderEndpointORM).filter_by(id=endpoint_id).first()
        if ep is None:
            return
        ep.test_status = "pass" if result.reachable else "fail"
        ep.last_tested_at = result.completed_at
        ep.updated_at = _utc_now()
        self.session.add(
            EndpointHealthSampleORM(
                endpoint_id=endpoint_id,
                healthy=result.reachable,
                latency_ms=result.latency_ms,
                error_message=result.error_code,
                sampled_at=result.completed_at,
            )
        )
        self.session.flush()
        self.session.commit()

    # ------------------------------------------------------------------ #
    # Discovered model bindings
    # ------------------------------------------------------------------ #
    def register_discovered_models(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> List[Dict[str, Any]]:
        return self._binding_repo.register_discovery_snapshot(endpoint_id, discovered_models)

    def reconcile_discovered_models(
        self, endpoint_id: str, discovered_models: List[DiscoveredModel]
    ) -> Dict[str, Any]:
        """P0.2.4 — one sync classified into added/updated/unchanged/unavailable."""
        return self._binding_repo.reconcile_discovery_snapshot(
            endpoint_id, discovered_models
        )

    def resolve_provider_model_id(
        self, endpoint_id: str, canonical_model_id: str
    ) -> Optional[str]:
        """Provider-facing model id of the active binding for a canonical model."""
        row = (
            self.session.query(EndpointModelBindingORM)
            .filter(
                EndpointModelBindingORM.endpoint_id == endpoint_id,
                EndpointModelBindingORM.canonical_model_id == canonical_model_id,
                EndpointModelBindingORM.availability == "active",
            )
            .first()
        )
        if row is None:
            row = (
                self.session.query(EndpointModelBindingORM)
                .filter_by(
                    endpoint_id=endpoint_id,
                    canonical_model_id=canonical_model_id,
                    enabled=True,
                )
                .first()
            )
        return row.provider_model_id if row else None

    def list_all_discovered_models(self) -> List[Dict[str, Any]]:
        """Whole durable registry across every vendor (P0.2 /api/v3/models)."""
        rows = (
            self.session.query(
                CanonicalModelV3ORM,
                EndpointModelBindingORM,
                ProviderEndpointORM,
                ProviderVendorORM,
            )
            .join(
                EndpointModelBindingORM,
                EndpointModelBindingORM.canonical_model_id == CanonicalModelV3ORM.id,
            )
            .join(
                ProviderEndpointORM,
                ProviderEndpointORM.id == EndpointModelBindingORM.endpoint_id,
            )
            .join(
                ProviderVendorORM,
                ProviderVendorORM.id == ProviderEndpointORM.vendor_id,
            )
            .filter(
                CanonicalModelV3ORM.enabled.is_(True),
                EndpointModelBindingORM.availability == "active",
            )
            .order_by(
                CanonicalModelV3ORM.canonical_name.asc(),
                EndpointModelBindingORM.provider_model_id.asc(),
            )
            .all()
        )
        grouped: Dict[str, Dict[str, Any]] = {}
        for model, binding, endpoint, vendor in rows:
            item = grouped.setdefault(
                model.id,
                {
                    "id": model.id,
                    "name": model.canonical_name,
                    "vendor": model.vendor,
                    "family": model.family,
                    "description": "",
                    "context_window": model.context_window or 0,
                    "max_output_tokens": 0,
                    "capabilities": json.loads(model.capabilities_json or "[]"),
                    "modalities": [],
                    "is_local": endpoint.protocol_mode == "ollama",
                    "is_active": model.enabled,
                    "pricing_class": "UNKNOWN",
                    "bindings": [],
                    "benchmarks": {},
                    "created_at": model.created_at.isoformat(),
                    "updated_at": model.updated_at.isoformat(),
                },
            )
            item["bindings"].append(self._binding_payload(binding, vendor.id))
        for item in grouped.values():
            item["pricing_class"] = _aggregate_pricing_class(item["bindings"])
        return list(grouped.values())

    def list_discovered_models(self, vendor_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.session.query(
                CanonicalModelV3ORM,
                EndpointModelBindingORM,
                ProviderEndpointORM,
            )
            .join(
                EndpointModelBindingORM,
                EndpointModelBindingORM.canonical_model_id == CanonicalModelV3ORM.id,
            )
            .join(
                ProviderEndpointORM,
                ProviderEndpointORM.id == EndpointModelBindingORM.endpoint_id,
            )
            .filter(
                ProviderEndpointORM.vendor_id == vendor_id,
                ProviderEndpointORM.enabled.is_(True),
                EndpointModelBindingORM.enabled.is_(True),
                CanonicalModelV3ORM.enabled.is_(True),
            )
            .order_by(
                CanonicalModelV3ORM.canonical_name.asc(),
                EndpointModelBindingORM.provider_model_id.asc(),
            )
            .all()
        )
        grouped: Dict[str, Dict[str, Any]] = {}
        for model, binding, endpoint in rows:
            item = grouped.setdefault(
                model.id,
                {
                    "id": model.id,
                    "name": model.canonical_name,
                    "vendor": model.vendor,
                    "family": model.family,
                    "description": "",
                    "context_window": model.context_window or 0,
                    "max_output_tokens": 0,
                    "capabilities": json.loads(model.capabilities_json or "[]"),
                    "modalities": [],
                    "is_local": endpoint.protocol_mode == "ollama",
                    "is_active": model.enabled,
                    "pricing_class": "UNKNOWN",
                    "bindings": [],
                    "benchmarks": {},
                    "created_at": model.created_at.isoformat(),
                    "updated_at": model.updated_at.isoformat(),
                },
            )
            item["bindings"].append(self._binding_payload(binding, vendor_id))
        for item in grouped.values():
            item["pricing_class"] = _aggregate_pricing_class(item["bindings"])
        return list(grouped.values())

    @staticmethod
    def _binding_payload(binding: EndpointModelBindingORM, vendor_id: str) -> Dict[str, Any]:
        return {
            "id": binding.id,
            "endpoint_id": binding.endpoint_id,
            "provider_id": vendor_id,
            "provider_model_id": binding.provider_model_id,
            "equivalence_level": binding.equivalence_level,
            "confidence": 1.0,
            "is_active": binding.enabled,
            "availability": getattr(binding, "availability", "active"),
            "pricing_class": getattr(binding, "pricing_class", "UNKNOWN"),
            "input_price": getattr(binding, "input_price", None),
            "output_price": getattr(binding, "output_price", None),
            "currency": getattr(binding, "currency", None),
            "last_discovered_at": (
                binding.last_discovered_at.isoformat()
                if getattr(binding, "last_discovered_at", None)
                else None
            ),
        }

    # ------------------------------------------------------------------ #
    # Model rules
    # ------------------------------------------------------------------ #
    def upsert_model_rule(self, rule: ModelRuleRecord) -> ModelRuleRecord:
        target = (
            self.session.query(CanonicalModelV3ORM)
            .filter_by(id=rule.primary_canonical_model_id, enabled=True)
            .first()
        )
        if target is None:
            raise ValueError(
                f"Canonical model '{rule.primary_canonical_model_id}' is not enabled"
            )
        existing = (
            self.session.query(ModelRoutingRuleV3ORM).filter_by(role=rule.role).first()
        )
        if existing is None:
            existing = ModelRoutingRuleV3ORM(role=rule.role)
            self.session.add(existing)
        existing.name = rule.name
        existing.description = rule.description
        existing.primary_canonical_model_id = rule.primary_canonical_model_id
        existing.fallback_canonical_model_id = rule.fallback_canonical_model_id
        existing.enabled = rule.enabled
        existing.priority = rule.priority
        existing.policy_json = rule.policy_json
        existing.updated_at = _utc_now()
        self.session.flush()
        self.session.commit()
        return self._rule_to_record(existing)

    def list_enabled_model_rules(self) -> List[ModelRuleRecord]:
        rows = (
            self.session.query(ModelRoutingRuleV3ORM)
            .filter_by(enabled=True)
            .order_by(ModelRoutingRuleV3ORM.priority.asc(), ModelRoutingRuleV3ORM.role.asc())
            .all()
        )
        return [self._rule_to_record(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Audit
    # ------------------------------------------------------------------ #
    def record_audit(self, event: ProviderAuditEvent) -> str:
        from windagent_core.security.redaction import redact_before_persist

        safe_metadata = redact_before_persist(event.metadata or {})
        row = ProviderRoutingAuditV3ORM(
            id=f"aud-{uuid.uuid4().hex[:12]}",
            action=event.action,
            scope_type="provider",
            scope_id=event.vendor_id,
            canonical_model_id=event.canonical_model_id,
            endpoint_id=event.endpoint_id,
            reason=event.reason,
            actor=event.actor,
            metadata_json=json.dumps(safe_metadata),
        )
        self.session.add(row)
        self.session.flush()
        self.session.commit()
        return str(row.id)

    # ------------------------------------------------------------------ #
    # Serialisation helpers
    # ------------------------------------------------------------------ #
    def _endpoint_to_record(self, r: ProviderEndpointORM) -> ProviderEndpointRecord:
        latest_health = (
            self.session.query(EndpointHealthSampleORM)
            .filter_by(endpoint_id=r.id)
            .order_by(EndpointHealthSampleORM.sampled_at.desc())
            .first()
        )
        models_count = (
            self.session.query(EndpointModelBindingORM)
            .filter_by(endpoint_id=r.id, enabled=True)
            .count()
        )
        return ProviderEndpointRecord(
            id=r.id,
            vendor_id=r.vendor_id,
            credential_id=r.credential_id,
            base_url=r.base_url,
            protocol_mode=r.protocol_mode,
            configured_protocol=r.configured_protocol,
            detected_protocol=r.detected_protocol,
            protocol_confidence=r.protocol_confidence,
            region=r.region,
            priority=r.priority,
            weight=r.weight,
            enabled=r.enabled,
            test_status=r.test_status,
            latency_ms=latest_health.latency_ms if latest_health else 0.0,
            models_count=models_count,
            last_tested_at=r.last_tested_at,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )

    @staticmethod
    def _rule_to_record(r: ModelRoutingRuleV3ORM) -> ModelRuleRecord:
        return ModelRuleRecord(
            role=r.role,
            name=r.name,
            description=r.description,
            primary_canonical_model_id=r.primary_canonical_model_id,
            fallback_canonical_model_id=r.fallback_canonical_model_id,
            enabled=r.enabled,
            priority=r.priority,
            policy_json=r.policy_json,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )


__all__ = ["SQLProviderManagementRepository"]
