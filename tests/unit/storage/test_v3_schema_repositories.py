"""
Unit tests for Provider Routing V3 Schema, Storage Repositories, and Legacy Backfill.
Adheres strictly to ban_ke_hoach.md §PHASE 2 requirements.
"""

import sys
import pytest
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

root_dir = Path(__file__).resolve().parents[3]
backend_dir = root_dir / "apps" / "backend"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if backend_dir.exists() and str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from utils.encryption import decrypt
from db.models import Base as LegacyBase, ModelProviderORM, CanonicalModelORM, ProviderModelBindingORM
from storage.windagent_storage.orm.models import BaseORM
from storage.windagent_storage.orm.v3_models import (
    ProviderVendorORM, ProviderCredentialORM, ProviderEndpointORM,
    CanonicalModelV3ORM, EndpointModelBindingORM, RouteLockV3ORM, RouteAttemptV3ORM
)
from storage.windagent_storage.migrations.v3_schema_migration import (
    create_v3_tables, backfill_legacy_providers, audit_v3_migration
)
from storage.windagent_storage.repositories.v3_repositories import (
    SQLEndpointRegistryRepository, SQLCanonicalModelRegistryRepository,
    SQLRouteLockRepository, SQLRouteAttemptRepository, SQLQuotaStateRepository,
    SQLEndpointStateRepository, SQLUsageLedgerRepository
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    BaseORM.metadata.create_all(engine)
    LegacyBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_empty_database_migration(in_memory_db):
    session = in_memory_db
    report = audit_v3_migration(session)
    assert report.migration_status == "PASSED"
    assert report.plaintext_credentials_count == 0
    assert report.orphan_endpoint_bindings_count == 0
    assert report.duplicate_active_route_locks_count == 0


def test_legacy_populated_database_backfill(in_memory_db):
    session = in_memory_db

    # Seed legacy tables
    legacy_prov = ModelProviderORM(
        id="openai",
        site_name="OpenAI Cloud",
        api_source="cloud",
        base_url="https://api.openai.com/v1",
        api_key="sk-testkey1234567890abcdef",
        enabled=True,
        priority=100,
    )
    session.add(legacy_prov)

    legacy_canonical = CanonicalModelORM(
        id="gpt-4o",
        vendor="openai",
        family="gpt-4",
        canonical_name="GPT-4o",
        revision="2024-05-13",
        context_window=128000,
        enabled=True,
    )
    session.add(legacy_canonical)

    legacy_binding = ProviderModelBindingORM(
        id="bind-gpt4o-openai",
        canonical_model_id="gpt-4o",
        provider_id="openai",
        provider_model_id="gpt-4o-2024-05-13",
        priority=100,
        enabled=True,
    )
    session.add(legacy_binding)
    session.commit()

    # Run backfill
    report = backfill_legacy_providers(session)
    session.commit()

    assert report.migration_status == "PASSED"
    assert report.vendors_migrated == 1
    assert report.credentials_migrated == 1
    assert report.endpoints_migrated == 1
    assert report.canonical_models_migrated == 1
    assert report.endpoint_bindings_migrated == 1

    # Verify V3 vendor, credential, endpoint created
    vendor = session.query(ProviderVendorORM).filter_by(id="openai").first()
    assert vendor is not None
    assert vendor.name == "OpenAI Cloud"

    cred = session.query(ProviderCredentialORM).filter_by(vendor_id="openai").first()
    assert cred is not None
    assert cred.secret_ciphertext.startswith("enc:v1:")
    # Verify decryption
    decrypted = decrypt(cred.secret_ciphertext)
    assert decrypted == "sk-testkey1234567890abcdef"

    ep = session.query(ProviderEndpointORM).filter_by(vendor_id="openai").first()
    assert ep is not None
    assert ep.base_url == "https://api.openai.com/v1"
    assert ep.protocol_mode == "openai"

    c_v3 = session.query(CanonicalModelV3ORM).filter_by(id="gpt-4o").first()
    assert c_v3 is not None
    assert c_v3.canonical_name == "GPT-4o"

    b_v3 = session.query(EndpointModelBindingORM).filter_by(id="bind-gpt4o-openai").first()
    assert b_v3 is not None
    assert b_v3.canonical_model_id == "gpt-4o"
    assert b_v3.provider_model_id == "gpt-4o-2024-05-13"


def test_credential_encryption_verification(in_memory_db):
    session = in_memory_db
    report = audit_v3_migration(session)
    assert report.plaintext_credentials_count == 0


@pytest.mark.asyncio
async def test_atomic_route_lock_creation(in_memory_db):
    session = in_memory_db
    repo = SQLRouteLockRepository(session)

    # First lock creation
    lock1 = await repo.create_lock("session", "sess-100", "gpt-4o", {"tier": "primary"})
    session.commit()
    assert lock1["canonical_model_id"] == "gpt-4o"
    assert lock1["status"] == "active"

    # Concurrent attempt to create lock on same scope returns existing lock
    lock2 = await repo.create_lock("session", "sess-100", "claude-3-5-sonnet", {"tier": "fallback"})
    assert lock2["id"] == lock1["id"]
    assert lock2["canonical_model_id"] == "gpt-4o"

    # Release lock
    released = await repo.release_lock(lock1["id"])
    session.commit()
    assert released is True

    # Now new lock can be created
    lock3 = await repo.create_lock("session", "sess-100", "claude-3-5-sonnet", {"tier": "primary"})
    session.commit()
    assert lock3["id"] != lock1["id"]
    assert lock3["canonical_model_id"] == "claude-3-5-sonnet"


@pytest.mark.asyncio
async def test_v3_repositories_port_contract(in_memory_db):
    session = in_memory_db

    # Seed vendor & endpoint & binding
    vendor = ProviderVendorORM(id="anthropic", name="Anthropic", vendor_type="cloud")
    cred = ProviderCredentialORM(id="cred-anthropic", vendor_id="anthropic", label="Key", secret_ciphertext="enc:v1:test")
    ep = ProviderEndpointORM(id="ep-anthropic", vendor_id="anthropic", credential_id="cred-anthropic", base_url="https://api.anthropic.com/v1", protocol_mode="anthropic", priority=100)
    cm = CanonicalModelV3ORM(id="claude-3-5-sonnet", vendor="anthropic", family="claude", canonical_name="Claude 3.5 Sonnet")
    binding = EndpointModelBindingORM(id="bind-claude", endpoint_id="ep-anthropic", canonical_model_id="claude-3-5-sonnet", provider_model_id="claude-3-5-sonnet-20241022", priority=100)
    
    session.add_all([vendor, cred, ep, cm, binding])
    session.commit()

    ep_repo = SQLEndpointRegistryRepository(session)
    cm_repo = SQLCanonicalModelRegistryRepository(session)
    ep_state_repo = SQLEndpointStateRepository(session)

    # Test ep_repo
    ep_data = await ep_repo.get_endpoint("ep-anthropic")
    assert ep_data["base_url"] == "https://api.anthropic.com/v1"

    endpoints_for_model = await ep_repo.list_endpoints_for_canonical_model("claude-3-5-sonnet")
    assert len(endpoints_for_model) == 1
    assert endpoints_for_model[0]["provider_model_id"] == "claude-3-5-sonnet-20241022"

    # Test cm_repo
    model_desc = await cm_repo.get_canonical_model("claude-3-5-sonnet")
    assert model_desc.display_name == "Claude 3.5 Sonnet"

    # Test ep_state_repo
    avail = await ep_state_repo.is_available("ep-anthropic")
    assert avail is True

    # Record 3 failures to trigger circuit breaker open
    await ep_state_repo.record_failure("ep-anthropic", "ProviderUnavailableFailure", 503)
    await ep_state_repo.record_failure("ep-anthropic", "ProviderUnavailableFailure", 503)
    await ep_state_repo.record_failure("ep-anthropic", "ProviderUnavailableFailure", 503)
    session.commit()

    avail = await ep_state_repo.is_available("ep-anthropic")
    assert avail is False
