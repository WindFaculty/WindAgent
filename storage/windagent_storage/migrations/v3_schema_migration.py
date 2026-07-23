"""
V3 Provider Subsystem Schema Migration and Deterministic Legacy Backfill.
Adheres strictly to ban_ke_hoach.md §PHASE 2.
Preserves legacy tables untouched for rollback and parity.
"""

from __future__ import annotations
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

root_dir = Path(__file__).resolve().parents[3]
backend_dir = root_dir / "apps" / "backend"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if backend_dir.exists() and str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from utils.encryption import encrypt
from db.models import (
    ModelProviderORM, CanonicalModelORM, ProviderModelBindingORM
)
from storage.windagent_storage.orm.models import BaseORM
from storage.windagent_storage.orm.v3_models import (
    ProviderVendorORM, ProviderCredentialORM, ProviderEndpointORM,
    CanonicalModelV3ORM, EndpointModelBindingORM, RouteLockV3ORM
)


@dataclass
class MigrationAuditReport:
    vendors_migrated: int = 0
    credentials_migrated: int = 0
    endpoints_migrated: int = 0
    canonical_models_migrated: int = 0
    endpoint_bindings_migrated: int = 0
    plaintext_credentials_count: int = 0
    orphan_endpoint_bindings_count: int = 0
    duplicate_active_route_locks_count: int = 0
    migration_status: str = "PASSED"
    warnings: List[str] = field(default_factory=list)


def create_v3_tables(engine: Any) -> None:
    """Idempotently creates all V3 ORM tables."""
    BaseORM.metadata.create_all(engine)


def backfill_legacy_providers(session: Session) -> MigrationAuditReport:
    """
    Deterministically migrates legacy model_providers, model_catalog, canonical_models,
    and provider_model_bindings to V3 schema.
    """
    report = MigrationAuditReport()

    # 1. Backfill Vendors, Credentials, Endpoints from legacy `model_providers`
    legacy_providers = session.query(ModelProviderORM).all() if session.query(ModelProviderORM).first() else []
    
    for legacy_p in legacy_providers:
        vendor_id = legacy_p.id.lower()
        
        # Upsert Vendor
        vendor = session.query(ProviderVendorORM).filter_by(id=vendor_id).first()
        if not vendor:
            vendor = ProviderVendorORM(
                id=vendor_id,
                name=legacy_p.site_name or vendor_id.title(),
                vendor_type=legacy_p.provider_type or "cloud",
                supports_model_discovery=legacy_p.supports_model_discovery,
                supports_openai_compatible=legacy_p.supports_openai_compatible,
                enabled=legacy_p.enabled,
            )
            session.add(vendor)
            report.vendors_migrated += 1

        # Upsert Credential if API key present or env specified
        cred_id = f"cred-{vendor_id}"
        cred = session.query(ProviderCredentialORM).filter_by(id=cred_id).first()
        if not cred:
            raw_key = legacy_p.api_key
            encrypted_key = None
            is_env = bool(legacy_p.api_key_env)
            
            if raw_key:
                if raw_key.startswith("enc:v1:"):
                    encrypted_key = raw_key
                else:
                    encrypted_key = encrypt(raw_key)

            cred = ProviderCredentialORM(
                id=cred_id,
                vendor_id=vendor_id,
                label=f"Default {legacy_p.site_name} Credential",
                secret_ciphertext=encrypted_key,
                is_env_ref=is_env,
                env_var_name=legacy_p.api_key_env,
                enabled=legacy_p.enabled,
            )
            session.add(cred)
            report.credentials_migrated += 1

        # Upsert Endpoint
        ep_id = f"ep-{vendor_id}"
        endpoint = session.query(ProviderEndpointORM).filter_by(id=ep_id).first()
        if not endpoint:
            base_url = legacy_p.base_url or "https://api.openai.com/v1"
            protocol = "openai"
            if "anthropic" in vendor_id:
                protocol = "anthropic"
            elif "google" in vendor_id or "gemini" in vendor_id:
                protocol = "gemini"
            elif "ollama" in vendor_id:
                protocol = "ollama"

            endpoint = ProviderEndpointORM(
                id=ep_id,
                vendor_id=vendor_id,
                credential_id=cred_id,
                base_url=base_url,
                protocol_mode=protocol,
                configured_protocol=protocol,
                detected_protocol=protocol,
                protocol_confidence=1.0,
                priority=legacy_p.priority or 50,
                enabled=legacy_p.enabled,
            )
            session.add(endpoint)
            report.endpoints_migrated += 1

    session.flush()

    # 2. Backfill Canonical Models from legacy `canonical_models` or `model_catalog`
    legacy_canonicals = session.query(CanonicalModelORM).all() if session.query(CanonicalModelORM).first() else []
    
    for legacy_c in legacy_canonicals:
        c_v3 = session.query(CanonicalModelV3ORM).filter_by(id=legacy_c.id).first()
        if not c_v3:
            c_v3 = CanonicalModelV3ORM(
                id=legacy_c.id,
                vendor=legacy_c.vendor,
                family=legacy_c.family,
                canonical_name=legacy_c.canonical_name,
                revision=legacy_c.revision or "latest",
                context_window=legacy_c.context_window or 128000,
                capabilities_json=legacy_c.capabilities_json or "[]",
                tool_call_protocol=legacy_c.tool_call_protocol,
                enabled=legacy_c.enabled,
            )
            session.add(c_v3)
            report.canonical_models_migrated += 1

    session.flush()

    # 3. Backfill Bindings from legacy `provider_model_bindings`
    legacy_bindings = session.query(ProviderModelBindingORM).all() if session.query(ProviderModelBindingORM).first() else []
    
    for legacy_b in legacy_bindings:
        ep_id = f"ep-{legacy_b.provider_id.lower()}"
        # Ensure target endpoint exists
        target_ep = session.query(ProviderEndpointORM).filter_by(id=ep_id).first()
        if not target_ep:
            report.warnings.append(f"Orphan binding skipped: {legacy_b.id} missing endpoint {ep_id}")
            continue

        binding_v3 = session.query(EndpointModelBindingORM).filter_by(id=legacy_b.id).first()
        if not binding_v3:
            binding_v3 = EndpointModelBindingORM(
                id=legacy_b.id,
                endpoint_id=ep_id,
                canonical_model_id=legacy_b.canonical_model_id,
                provider_model_id=legacy_b.provider_model_id,
                model_revision="latest",
                equivalence_level="exact_revision",
                equivalence_fingerprint=f"{legacy_b.canonical_model_id}:{legacy_b.provider_model_id}",
                capabilities_json="[]",
                pricing_overrides_json="{}",
                enabled=legacy_b.enabled,
                priority=legacy_b.priority,
            )
            session.add(binding_v3)
            report.endpoint_bindings_migrated += 1

    session.flush()
    return audit_v3_migration(session, report)


def audit_v3_migration(session: Session, report: Optional[MigrationAuditReport] = None) -> MigrationAuditReport:
    """Audits plaintext credentials, orphan bindings, and duplicate active route locks."""
    if report is None:
        report = MigrationAuditReport()

    # Audit plaintext credentials
    creds = session.query(ProviderCredentialORM).all()
    plaintext_count = 0
    for cred in creds:
        if cred.secret_ciphertext and not cred.secret_ciphertext.startswith("enc:v1:"):
            plaintext_count += 1
    report.plaintext_credentials_count = plaintext_count

    # Audit orphan endpoint bindings
    bindings = session.query(EndpointModelBindingORM).all()
    orphan_count = 0
    for binding in bindings:
        ep = session.query(ProviderEndpointORM).filter_by(id=binding.endpoint_id).first()
        cm = session.query(CanonicalModelV3ORM).filter_by(id=binding.canonical_model_id).first()
        if not ep or not cm:
            orphan_count += 1
    report.orphan_endpoint_bindings_count = orphan_count

    # Audit duplicate active route locks
    active_locks = session.query(RouteLockV3ORM).filter_by(status="active").all()
    scope_map: Dict[str, int] = {}
    duplicate_locks = 0
    for lock in active_locks:
        key = f"{lock.scope_type}:{lock.scope_id}"
        scope_map[key] = scope_map.get(key, 0) + 1
        if scope_map[key] > 1:
            duplicate_locks += 1
    report.duplicate_active_route_locks_count = duplicate_locks

    if plaintext_count > 0 or orphan_count > 0 or duplicate_locks > 0:
        report.migration_status = "FAILED"
    else:
        report.migration_status = "PASSED"

    return report
