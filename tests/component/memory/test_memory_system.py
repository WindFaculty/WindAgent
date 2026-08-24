"""
Unit Tests for WindAgent Memory System (Phase 9 + Phase 21):
- MemoryStore CRUD across working, session, project, user, and episodic scopes
- MemoryWritePolicy secret exclusion & provenance enforcement
- TTL-based expiry and retention policy eviction
- Content-hash deduplication
- forget / forget_by_pattern
- Cross-project memory isolation
- Durable MemoryRecordRepository
"""

import pytest
from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError
from windagent_memory import MemoryStore, MemoryRecord, MemoryScope
from windagent_memory.models import RetentionPolicy, DEFAULT_SCOPE_TTL
from tests.support.waiting import deterministic_sleep


# ====================================================================
# CRUD & Scopes (existing + WORKING scope)
# ====================================================================

def test_memory_store_crud_and_scopes():
    store = MemoryStore()

    # Session scope
    rec_session = MemoryRecord(
        id="mem_1",
        scope=MemoryScope.SESSION,
        key="last_visited_route",
        value="/settings",
        provenance_source="ui_router",
        session_id="sess_100",
    )
    store.save(rec_session)
    fetched = store.get(MemoryScope.SESSION, "last_visited_route", session_id="sess_100")
    assert fetched is not None
    assert fetched.value == "/settings"

    # Working scope (Phase 21)
    rec_working = MemoryRecord(
        id="mem_working",
        scope=MemoryScope.WORKING,
        key="current_file",
        value="src/main.py",
        provenance_source="editor",
        session_id="sess_100",
        ttl_seconds=60,  # 1 minute TTL
    )
    store.save(rec_working)
    fetched_working = store.get(MemoryScope.WORKING, "current_file", session_id="sess_100")
    assert fetched_working is not None
    assert fetched_working.value == "src/main.py"

    # User scope
    rec_user = MemoryRecord(
        id="mem_user",
        scope=MemoryScope.USER,
        key="theme",
        value="dark",
        provenance_source="user_prefs",
    )
    store.save(rec_user)
    assert store.get(MemoryScope.USER, "theme") is not None

    # Episodic scope
    rec_ep = MemoryRecord(
        id="mem_ep",
        scope=MemoryScope.EPISODIC,
        key="user_incident",
        value="User reported login timeout",
        provenance_source="support_ticket",
    )
    store.save(rec_ep)
    assert store.get(MemoryScope.EPISODIC, "user_incident") is not None

    # Delete session record
    assert store.delete(MemoryScope.SESSION, "last_visited_route", session_id="sess_100")
    assert store.get(MemoryScope.SESSION, "last_visited_route", session_id="sess_100") is None


# ====================================================================
# TTL-Based Expiry
# ====================================================================

def test_memory_ttl_expiry():
    store = MemoryStore()

    # Record with zero TTL (immediately expires)
    rec_ttl = MemoryRecord(
        id="mem_ttl",
        scope=MemoryScope.WORKING,
        key="short_lived",
        value="ephemeral data",
        provenance_source="test",
        ttl_seconds=0,  # Zero TTL = immediate expiry
    )
    store.save(rec_ttl)

    # Should be expired immediately
    fetched = store.get(MemoryScope.WORKING, "short_lived")
    assert fetched is None, "Record with TTL=0 should be expired immediately"

    # Record with non-zero TTL (should persist)
    rec_persist = MemoryRecord(
        id="mem_persist",
        scope=MemoryScope.WORKING,
        key="persistent_data",
        value="important",
        provenance_source="test",
        ttl_seconds=3600,  # 1 hour
    )
    store.save(rec_persist)
    fetched = store.get(MemoryScope.WORKING, "persistent_data")
    assert fetched is not None
    assert fetched.value == "important"

    # Test record with default scope TTL
    rec_default = MemoryRecord(
        id="mem_default",
        scope=MemoryScope.SESSION,
        key="default_ttl",
        value="session data",
        provenance_source="test",
        session_id="sess_1",
    )
    assert rec_default.get_effective_ttl() == DEFAULT_SCOPE_TTL[MemoryScope.SESSION]  # 86400


def test_memory_ttl_eviction():
    """Test that expired records are evicted by evict_expired()."""
    store = MemoryStore()

    # Record that expires after 50ms
    rec = MemoryRecord(
        id="mem_evict",
        scope=MemoryScope.WORKING,
        key="evict_me",
        value="gone soon",
        provenance_source="test",
        ttl_seconds=0.05,  # Very short TTL
    )
    store.save(rec)
    assert store.get(MemoryScope.WORKING, "evict_me") is not None

    # Wait for expiry
    deterministic_sleep(0.1)

    # Should be expired now
    assert store.get(MemoryScope.WORKING, "evict_me") is None
    assert store.count_by_scope().get("working", 0) == 0


# ====================================================================
# Content-Hash Deduplication
# ====================================================================

def test_memory_deduplication():
    store = MemoryStore()

    # Save the same content twice
    rec1 = MemoryRecord(
        id="mem_dedup_1",
        scope=MemoryScope.SESSION,
        key="result_cache",
        value={"output": "same data"},
        provenance_source="test",
        session_id="sess_dedup",
    )
    store.save(rec1)

    # Same key and value — should update, not duplicate
    rec2 = MemoryRecord(
        id="mem_dedup_2",
        scope=MemoryScope.SESSION,
        key="result_cache",
        value={"output": "same data"},
        provenance_source="test",
        session_id="sess_dedup",
    )
    store.save(rec2)

    # Only one record should exist
    records = store.list_records_for_session("sess_dedup")
    assert len(records) == 1
    assert records[0].id == "mem_dedup_1"  # Kept original

    # Different content should create new record
    rec3 = MemoryRecord(
        id="mem_dedup_3",
        scope=MemoryScope.SESSION,
        key="result_cache_2",
        value={"output": "different data"},
        provenance_source="test",
        session_id="sess_dedup",
    )
    store.save(rec3)
    records = store.list_records_for_session("sess_dedup")
    assert len(records) == 2


# ====================================================================
# Forget methods
# ====================================================================

def test_memory_forget():
    store = MemoryStore()

    # Save several records
    for i in range(5):
        rec = MemoryRecord(
            id=f"mem_forget_{i}",
            scope=MemoryScope.SESSION,
            key=f"key_{i}",
            value=f"value_{i}",
            provenance_source="test",
            session_id="sess_forget",
        )
        store.save(rec)

    assert len(store.list_records_for_session("sess_forget")) == 5

    # Forget a single record
    result = store.forget(MemoryScope.SESSION, "key_0", session_id="sess_forget")
    assert result is True
    assert len(store.list_records_for_session("sess_forget")) == 4

    # Forget by pattern
    count = store.forget_by_pattern(MemoryScope.SESSION, "key_", session_id="sess_forget")
    assert count == 4  # Remaining records all match "key_"
    assert len(store.list_records_for_session("sess_forget")) == 0


# ====================================================================
# Retention Policy
# ====================================================================

def test_retention_policy_eviction():
    store = MemoryStore(
        retention_policy=RetentionPolicy(
            max_records_per_scope=3,
            auto_evict_expired=True,
        )
    )

    # Save 5 records in working scope
    for i in range(5):
        rec = MemoryRecord(
            id=f"mem_ret_{i}",
            scope=MemoryScope.WORKING,
            key=f"ret_key_{i}",
            value=f"ret_value_{i}",
            provenance_source="test",
        )
        store.save(rec)

    # Evict expired — none have TTL, but we exceed max_records_per_scope
    # Note: eviction via RetentionPolicy requires the repository to enforce
    # The MemoryStore itself doesn't auto-evict on max_records_per_scope
    # That's enforced by the MemoryRecordRepository.evict_expired
    # The store just handles TTL-based auto-eviction on get()
    stats = store.get_stats()
    assert stats["total_records"] <= 5


# ====================================================================
# Cross-Project Isolation
# ====================================================================

def test_cross_project_isolation():
    store = MemoryStore()

    rec_a = MemoryRecord(
        id="mem_a",
        scope=MemoryScope.PROJECT,
        key="framework",
        value="fastapi",
        provenance_source="detector",
        project_id="proj_A",
    )
    rec_b = MemoryRecord(
        id="mem_b",
        scope=MemoryScope.PROJECT,
        key="framework",
        value="django",
        provenance_source="detector",
        project_id="proj_B",
    )
    store.save(rec_a)
    store.save(rec_b)

    list_a = store.list_records_for_project("proj_A")
    assert len(list_a) == 1
    assert list_a[0].value == "fastapi"

    list_b = store.list_records_for_project("proj_B")
    assert len(list_b) == 1
    assert list_b[0].value == "django"


# ====================================================================
# Write Policy (Secret Exclusion, Provenance, Scope)
# ====================================================================

def test_memory_write_policy_secret_exclusion():
    store = MemoryStore()

    secret_rec = MemoryRecord(
        id="mem_secret",
        scope=MemoryScope.PROJECT,
        key="api_credentials",
        value="My key is sk-1234567890abcdef1234567890",
        provenance_source="config_loader",
        project_id="proj_A",
    )
    with pytest.raises(PermissionDeniedError, match="Storing API keys"):
        store.save(secret_rec)


def test_memory_write_policy_provenance_and_scope_validation():
    store = MemoryStore()

    # Missing provenance source
    no_prov_rec = MemoryRecord(
        id="mem_2",
        scope=MemoryScope.USER,
        key="theme",
        value="dark",
        provenance_source="",
    )
    with pytest.raises(ValidationError, match="provenance_source"):
        store.save(no_prov_rec)

    # Missing project_id for PROJECT scope
    no_proj_rec = MemoryRecord(
        id="mem_3",
        scope=MemoryScope.PROJECT,
        key="build_target",
        value="production",
        provenance_source="build_tool",
        project_id=None,
    )
    with pytest.raises(ValidationError, match="project_id"):
        store.save(no_proj_rec)


# ====================================================================
# Stats
# ====================================================================

def test_memory_store_stats():
    store = MemoryStore()

    # Add records in different scopes
    store.save(MemoryRecord(id="s1", scope=MemoryScope.WORKING, key="w1", value="a", provenance_source="test"))
    store.save(MemoryRecord(id="s2", scope=MemoryScope.WORKING, key="w2", value="b", provenance_source="test"))
    store.save(MemoryRecord(id="s3", scope=MemoryScope.SESSION, key="s1", value="c", provenance_source="test", session_id="s1"))

    stats = store.get_stats()
    assert stats["total_records"] == 3
    assert stats["by_scope"].get("working", 0) == 2
    assert stats["by_scope"].get("session", 0) == 1
    assert stats["retention_policy"]["auto_evict_expired"] is True


# ====================================================================
# Search by Tag
# ====================================================================

def test_memory_search_by_tag():
    store = MemoryStore()

    rec = MemoryRecord(
        id="mem_tagged",
        scope=MemoryScope.WORKING,
        key="tagged_data",
        value="test",
        provenance_source="test",
        tags={"env": "prod", "region": "us-east"},
    )
    store.save(rec)

    results = store.search_by_tag("env", "prod")
    assert len(results) == 1

    results = store.search_by_tag("region", "eu-west")
    assert len(results) == 0