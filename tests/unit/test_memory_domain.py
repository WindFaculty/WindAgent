"""Unit tests for Memory domain models, write policy, and scopes (Phase 14)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from windagent.modules.memory.domain.errors import (
    MemoryPermissionDeniedError,
    MemoryValidationError,
)
from windagent.modules.memory.domain.models import (
    LearningMetadata,
    MemoryRecord,
    compute_content_hash,
)
from windagent.modules.memory.domain.policy import MemoryWritePolicy
from windagent.modules.memory.domain.scope import (
    DEFAULT_SCOPE_TTL,
    MemoryScope,
    ValidationStatus,
)


def test_scope_and_ttl_defaults() -> None:
    assert MemoryScope.WORKING.value == "working"
    assert MemoryScope.SESSION.value == "session"
    assert MemoryScope.PROJECT.value == "project"
    assert MemoryScope.USER.value == "user"
    assert MemoryScope.EPISODIC.value == "episodic"
    assert MemoryScope.SEMANTIC.value == "semantic"
    assert MemoryScope.PROCEDURAL.value == "procedural"
    assert MemoryScope.POLICY.value == "policy"

    assert DEFAULT_SCOPE_TTL[MemoryScope.WORKING] == 3600
    assert DEFAULT_SCOPE_TTL[MemoryScope.SESSION] == 86400
    assert DEFAULT_SCOPE_TTL[MemoryScope.PROJECT] is None
    assert DEFAULT_SCOPE_TTL[MemoryScope.USER] is None
    assert DEFAULT_SCOPE_TTL[MemoryScope.EPISODIC] == 604800
    assert DEFAULT_SCOPE_TTL[MemoryScope.SEMANTIC] is None
    assert DEFAULT_SCOPE_TTL[MemoryScope.PROCEDURAL] is None
    assert DEFAULT_SCOPE_TTL[MemoryScope.POLICY] is None


def test_learning_metadata_and_validation_status() -> None:
    meta = LearningMetadata(
        confidence=0.85,
        sample_size=10,
        validation_status=ValidationStatus.VALIDATED,
        evidence_refs=("ref_1", "ref_2"),
    )
    assert meta.is_validated() is True
    assert meta.is_terminal() is False

    d = meta.to_dict()
    assert d["confidence"] == 0.85
    assert d["sample_size"] == 10
    assert d["validation_status"] == "validated"

    restored = LearningMetadata.from_dict(d)
    assert restored == meta

    rejected = LearningMetadata(validation_status=ValidationStatus.REJECTED)
    assert rejected.is_terminal() is True
    assert rejected.is_validated() is False


def test_content_hash_deterministic() -> None:
    h1 = compute_content_hash("api_endpoint", {"url": "https://api.example.com", "retries": 3})
    h2 = compute_content_hash("api_endpoint", {"retries": 3, "url": "https://api.example.com"})
    assert h1 == h2
    assert len(h1) == 64


def test_memory_record_expiry() -> None:
    now = datetime.now(UTC)
    rec_working = MemoryRecord(
        id="mem_1",
        scope=MemoryScope.WORKING,
        key="temp_key",
        value="temp_val",
        provenance_source="test",
        created_at=now,
        updated_at=now,
    )
    assert rec_working.get_effective_ttl() == 3600
    assert rec_working.is_expired(reference_time=now) is False

    # 2 hours later -> expired
    later = datetime.fromtimestamp(now.timestamp() + 7200, tz=UTC)
    assert rec_working.is_expired(reference_time=later) is True

    # Persistent scope -> never expires
    rec_project = MemoryRecord(
        id="mem_2",
        scope=MemoryScope.PROJECT,
        key="config",
        value={"db": "pg"},
        provenance_source="test",
        project_id="proj_1",
        created_at=now,
        updated_at=now,
    )
    assert rec_project.get_effective_ttl() is None
    assert rec_project.is_expired(reference_time=later) is False


def test_write_policy_secret_exclusion() -> None:
    policy = MemoryWritePolicy()

    # Secret in value
    rec_secret = MemoryRecord(
        id="mem_sec",
        scope=MemoryScope.WORKING,
        key="api_token",
        value="sk-1234567890abcdefghijklmnopqrstuvwxyz",
        provenance_source="test",
    )
    with pytest.raises(MemoryPermissionDeniedError) as exc_info:
        policy.validate_and_enforce(rec_secret)
    assert "Storing API keys, tokens, or passwords" in str(exc_info.value)

    # Secret in key
    rec_sec_key = MemoryRecord(
        id="mem_sec_k",
        scope=MemoryScope.WORKING,
        key="password='supersecret'",
        value="data",
        provenance_source="test",
    )
    with pytest.raises(MemoryPermissionDeniedError):
        policy.validate_and_enforce(rec_sec_key)


def test_write_policy_provenance_and_scope_isolation() -> None:
    policy = MemoryWritePolicy(enforce_provenance=True)

    # Missing provenance
    rec_no_prov = MemoryRecord(
        id="mem_np",
        scope=MemoryScope.WORKING,
        key="key1",
        value="val1",
        provenance_source="",
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_no_prov)
    assert "Missing mandatory provenance_source" in str(exc.value)

    # Project scope without project_id
    rec_proj = MemoryRecord(
        id="mem_p",
        scope=MemoryScope.PROJECT,
        key="p_key",
        value="p_val",
        provenance_source="user",
        project_id=None,
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_proj)
    assert "requires a valid project_id" in str(exc.value)

    # Session scope without session_id
    rec_sess = MemoryRecord(
        id="mem_s",
        scope=MemoryScope.SESSION,
        key="s_key",
        value="s_val",
        provenance_source="user",
        session_id=None,
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_sess)
    assert "requires a valid session_id" in str(exc.value)


def test_write_policy_learning_admission_gate() -> None:
    policy = MemoryWritePolicy(min_promotion_confidence=0.5, min_promotion_sample_size=2)

    # Invalid confidence
    rec_bad_conf = MemoryRecord(
        id="mem_bc",
        scope=MemoryScope.SEMANTIC,
        key="k",
        value="v",
        provenance_source="system",
        learning_metadata=LearningMetadata(confidence=1.5),
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_bad_conf)
    assert "Invalid confidence score" in str(exc.value)

    # Policy memory with low confidence
    rec_low_conf = MemoryRecord(
        id="mem_lc",
        scope=MemoryScope.POLICY,
        key="rule_1",
        value="Always retry 429",
        provenance_source="eval",
        learning_metadata=LearningMetadata(
            confidence=0.3,
            sample_size=5,
            validation_status=ValidationStatus.VALIDATED,
            evidence_refs=("run_1",),
        ),
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_low_conf)
    assert "confidence 0.3 < threshold 0.5" in str(exc.value)

    # Policy memory with small sample size
    rec_small_sample = MemoryRecord(
        id="mem_ss",
        scope=MemoryScope.POLICY,
        key="rule_2",
        value="Always retry 429",
        provenance_source="eval",
        learning_metadata=LearningMetadata(
            confidence=0.9,
            sample_size=1,
            validation_status=ValidationStatus.VALIDATED,
            evidence_refs=("run_1",),
        ),
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_small_sample)
    assert "sample size 1 < threshold 2" in str(exc.value)

    # Policy memory without evidence or source runs
    rec_no_ev = MemoryRecord(
        id="mem_ne",
        scope=MemoryScope.POLICY,
        key="rule_3",
        value="Always retry 429",
        provenance_source="eval",
        learning_metadata=LearningMetadata(
            confidence=0.9,
            sample_size=5,
            validation_status=ValidationStatus.PROMOTED,
            evidence_refs=(),
            source_run_ids=(),
        ),
    )
    with pytest.raises(MemoryValidationError) as exc:
        policy.validate_and_enforce(rec_no_ev)
    assert "without evidence_refs or source_run_ids" in str(exc.value)

    # Valid policy memory passes
    rec_valid = MemoryRecord(
        id="mem_ok",
        scope=MemoryScope.POLICY,
        key="rule_valid",
        value="Always use UTC",
        provenance_source="harness",
        learning_metadata=LearningMetadata(
            confidence=0.95,
            sample_size=10,
            validation_status=ValidationStatus.PROMOTED,
            evidence_refs=("run_123",),
        ),
    )
    policy.validate_and_enforce(rec_valid)  # No exception
