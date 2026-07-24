"""
Unit tests for WindAgent Core Typed IDs (Phase 2).
Verifies UUIDEntityId, OpaqueId, Pydantic v2 serialization, fail-closed validation, and classifier.
"""

import uuid
import pytest
from pydantic import BaseModel
from windagent_core.domain.types import (
    UUIDEntityId, OpaqueId, TaskId, TaskRunId, SessionId, WorkflowId, StepId,
    StepRunId, EventId, ArtifactId, PermissionRequestId, ToolCallId, ModelCallId,
    ProviderId, EndpointId, CanonicalModelId, ProviderModelId, RuntimeRunId,
    RuntimeSessionId, WorkerId, RouteLockId, RouteAttemptId, ExternalRequestId,
    classify_identifier
)
from windagent_core.errors.exceptions import IdentityValidationError


def test_uuid_entity_id_roundtrip():
    raw_uuid = uuid.uuid4()
    task_id = TaskId(raw_uuid)
    assert task_id.value == str(raw_uuid)
    assert task_id.to_uuid() == raw_uuid
    assert str(task_id) == str(raw_uuid)
    assert repr(task_id) == f"TaskId({str(raw_uuid)!r})"

    # String roundtrip
    task_id_str = TaskId(str(raw_uuid))
    assert task_id_str == task_id
    assert task_id_str.value == str(raw_uuid)


def test_uuid_entity_id_generation():
    gen_id = TaskId.generate()
    assert isinstance(gen_id, TaskId)
    assert isinstance(gen_id.to_uuid(), uuid.UUID)


def test_uuid_entity_id_invalid_rejection():
    invalid_inputs = [
        "not-a-uuid",
        "12345",
        "prv_openai",
        "",
        "   ",
        12345,
        ["list"],
    ]
    for invalid in invalid_inputs:
        with pytest.raises(IdentityValidationError):
            TaskId(invalid)


def test_uuid_entity_id_fail_closed_none():
    with pytest.raises(IdentityValidationError):
        TaskId(None)


def test_opaque_id_roundtrip():
    provider_id = ProviderId("openai")
    assert provider_id.value == "openai"
    assert str(provider_id) == "openai"
    assert repr(provider_id) == "ProviderId('openai')"

    worker_id = WorkerId.of("wkr_node_01")
    assert worker_id.value == "wkr_node_01"


def test_opaque_id_has_no_to_uuid():
    provider_id = ProviderId("openai")
    assert not hasattr(provider_id, "to_uuid")


def test_opaque_id_invalid_rejection():
    invalid_inputs = ["", "   ", None, 12345, ["list"]]
    for invalid in invalid_inputs:
        with pytest.raises(IdentityValidationError):
            ProviderId(invalid)


def test_equality_and_hashing():
    u1 = uuid.uuid4()
    t1 = TaskId(u1)
    t2 = TaskId(u1)
    s1 = SessionId(u1)

    assert t1 == t2
    assert t1 == u1
    assert t1 == str(u1)
    # Different ID classes are not equal even with same UUID
    assert t1 != s1

    # Hash checks for sets/dicts
    id_set = {t1, t2, s1}
    assert len(id_set) == 2

    p1 = ProviderId("openai")
    p2 = ProviderId("openai")
    w1 = WorkerId("openai")
    assert p1 == p2
    assert p1 != w1
    assert len({p1, p2, w1}) == 2


class DummyPydanticModel(BaseModel):
    task_id: TaskId
    provider_id: ProviderId


def test_pydantic_v2_serialization():
    u = uuid.uuid4()
    model = DummyPydanticModel(
        task_id=TaskId(u),
        provider_id=ProviderId("openai")
    )
    
    # Model dump dict
    d = model.model_dump()
    assert d["task_id"] == TaskId(u)
    assert d["provider_id"] == ProviderId("openai")

    # JSON serialization
    json_str = model.model_dump_json()
    assert str(u) in json_str
    assert "openai" in json_str

    # JSON deserialization
    deserialized = DummyPydanticModel.model_validate_json(json_str)
    assert isinstance(deserialized.task_id, TaskId)
    assert isinstance(deserialized.provider_id, ProviderId)
    assert deserialized.task_id == TaskId(u)
    assert deserialized.provider_id == ProviderId("openai")


def test_classify_identifier():
    valid_uuid_str = str(uuid.uuid4())
    assert classify_identifier(valid_uuid_str) == "uuid"
    assert classify_identifier("prv_openai_01") == "opaque_prefix"
    assert classify_identifier("wkr_worker_node") == "opaque_prefix"
    assert classify_identifier("some-custom-string-id") == "opaque"
    assert classify_identifier("") == "invalid"
    assert classify_identifier(None) == "invalid"
    assert classify_identifier(12345) == "invalid"
