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
    ModelRoutingRuleV3ORM,
    ProviderCredentialORM,
    ProviderEndpointORM,
    ProviderRoutingAuditV3ORM,
    ProviderVendorORM,
)
from windagent_storage.repositories.v3_routing_repositories import (
    SQLEndpointBindingRepository,
)
from windagent_storage.security.encryption import encrypt


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SQLProviderManagementRepository(ProviderManagementRepositoryPort):
    """SQL-backed provider vendor/credential/endpoint/model-rule authority."""

    def __init__(self, session: Session):
        self.session = session
        self._binding_repo = SQLEndpointBindingRepository(session)

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
                    "bindings": [],
                    "benchmarks": {},
                    "created_at": model.created_at.isoformat(),
                    "updated_at": model.updated_at.isoformat(),
                },
            )
            item["bindings"].append(
                {
                    "id": binding.id,
                    "endpoint_id": binding.endpoint_id,
                    "provider_id": vendor_id,
                    "provider_model_id": binding.provider_model_id,
                    "equivalence_level": binding.equivalence_level,
                    "confidence": 1.0,
                    "is_active": binding.enabled,
                }
            )
        return list(grouped.values())

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
