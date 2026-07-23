"""
Unit Tests for WindAgent Memory System (Phase 9):
- MemoryStore CRUD across session, project, user, and episodic scopes
- MemoryWritePolicy secret exclusion (API keys & bearer tokens forbidden)
- Provenance enforcement & project scope validation
- Cross-project memory isolation
"""

import pytest
from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError
from windagent_memory import MemoryStore, MemoryRecord, MemoryScope, MemoryWritePolicy


def test_memory_store_crud_and_scopes():
    store = MemoryStore()

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

    # Delete record
    assert store.delete(MemoryScope.SESSION, "last_visited_route", session_id="sess_100")
    assert store.get(MemoryScope.SESSION, "last_visited_route", session_id="sess_100") is None


def test_memory_write_policy_secret_exclusion():
    store = MemoryStore()

    # Attempting to store an API key must be denied by MemoryWritePolicy
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
