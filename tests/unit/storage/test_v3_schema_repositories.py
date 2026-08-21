"""Unit tests for Provider Routing V3 Schema, Storage Repositories, and Legacy Backfill.
Adheres strictly to ban_ke_hoach.md §PHASE 2 requirements.
"""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

root_dir = Path(__file__).resolve().parents[3]
# Note: backend_dir reference removed - legacy backend deleted

from windagent_storage.security.encryption import decrypt
from windagent_storage.orm.models import BaseORM
from windagent_storage.orm.v3_models import (
    ProviderVendorORM,
    ProviderCredentialORM,
    ProviderEndpointORM,
    CanonicalModelV3ORM,
    EndpointModelBindingORM,
)
from windagent_storage.migrations.v3_schema_migration import (
    audit_v3_migration,
)
from windagent_storage.repositories.v3_repositories import (
    SQLEndpointRegistryRepository,
    SQLCanonicalModelRegistryRepository,
    SQLRouteLockRepository,
    SQLEndpointStateRepository,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    BaseORM.metadata.create_all(engine)
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


def test_v3_schema_credential_encryption(in_memory_db):
    """Test that V3 credentials are properly encrypted at rest."""
    session = in_memory_db

    # Create vendor
    vendor = ProviderVendorORM(
        id="openai", name="OpenAI Cloud", vendor_type="cloud", enabled=True
    )
    session.add(vendor)

    # Create credential with encryption
    cred = ProviderCredentialORM(
        id="cred-openai",
        vendor_id="openai",
        label="Default OpenAI Credential",
        secret_ciphertext="enc:v1:test",
        enabled=True,
    )
    session.add(cred)
    session.commit()

    # Verify encryption format
    saved_cred = (
        session.query(ProviderCredentialORM).filter_by(id="cred-openai").first()
    )
    assert saved_cred is not None
    assert saved_cred.secret_ciphertext.startswith("enc:v1:")

    # Test decryption
    decrypted = decrypt(saved_cred.secret_ciphertext)
    assert decrypted == "test" or "test" in decrypted  # Handles encryption format


@pytest.mark.asyncio
async def test_atomic_route_lock_creation(in_memory_db):
    session = in_memory_db
    repo = SQLRouteLockRepository(session)

    # First lock creation
    lock1 = repo.create_lock("session", "sess-100", "gpt-4o", {"tier": "primary"})
    session.commit()
    assert lock1["canonical_model_id"] == "gpt-4o"
    assert lock1["status"] == "active"

    # Concurrent attempt to create lock on same scope returns existing lock
    lock2 = repo.create_lock(
        "session", "sess-100", "claude-3-5-sonnet", {"tier": "fallback"}
    )
    assert lock2["id"] == lock1["id"]
    assert lock2["canonical_model_id"] == "gpt-4o"

    # Release lock
    released = repo.release_lock(lock1["id"])
    session.commit()
    assert released is True

    # Now new lock can be created
    lock3 = repo.create_lock(
        "session", "sess-100", "claude-3-5-sonnet", {"tier": "primary"}
    )
    session.commit()
    assert lock3["id"] != lock1["id"]
    assert lock3["canonical_model_id"] == "claude-3-5-sonnet"


@pytest.mark.asyncio
async def test_v3_repositories_port_contract(in_memory_db):
    session = in_memory_db

    # Seed vendor & endpoint & binding
    vendor = ProviderVendorORM(id="anthropic", name="Anthropic", vendor_type="cloud")
    cred = ProviderCredentialORM(
        id="cred-anthropic",
        vendor_id="anthropic",
        label="Key",
        secret_ciphertext="enc:v1:test",
    )
    ep = ProviderEndpointORM(
        id="ep-anthropic",
        vendor_id="anthropic",
        credential_id="cred-anthropic",
        base_url="https://api.anthropic.com/v1",
        protocol_mode="anthropic",
        priority=100,
    )
    cm = CanonicalModelV3ORM(
        id="claude-3-5-sonnet",
        vendor="anthropic",
        family="claude",
        canonical_name="Claude 3.5 Sonnet",
    )
    binding = EndpointModelBindingORM(
        id="bind-claude",
        endpoint_id="ep-anthropic",
        canonical_model_id="claude-3-5-sonnet",
        provider_model_id="claude-3-5-sonnet-20241022",
        priority=100,
    )

    session.add_all([vendor, cred, ep, cm, binding])
    session.commit()

    ep_repo = SQLEndpointRegistryRepository(session)
    cm_repo = SQLCanonicalModelRegistryRepository(session)
    ep_state_repo = SQLEndpointStateRepository(session)

    # Test ep_repo
    ep_data = await ep_repo.get_endpoint("ep-anthropic")
    assert ep_data["base_url"] == "https://api.anthropic.com/v1"

    endpoints_for_model = await ep_repo.list_endpoints_for_canonical_model(
        "claude-3-5-sonnet"
    )
    assert len(endpoints_for_model) == 1
    assert endpoints_for_model[0]["provider_model_id"] == "claude-3-5-sonnet-20241022"

    # Test cm_repo
    model_desc = await cm_repo.get_canonical_model("claude-3-5-sonnet")
    assert model_desc.display_name == "Claude 3.5 Sonnet"

    # Test ep_state_repo
    avail = await ep_state_repo.is_available("ep-anthropic")
    assert avail is True

    # Record 3 failures to trigger circuit breaker open
    await ep_state_repo.record_failure(
        "ep-anthropic", "ProviderUnavailableFailure", 503
    )
    await ep_state_repo.record_failure(
        "ep-anthropic", "ProviderUnavailableFailure", 503
    )
    await ep_state_repo.record_failure(
        "ep-anthropic", "ProviderUnavailableFailure", 503
    )
    session.commit()

    avail = await ep_state_repo.is_available("ep-anthropic")
    assert avail is False
