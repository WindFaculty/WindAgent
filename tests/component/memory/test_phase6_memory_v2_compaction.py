"""Phase 6 Component Tests — Memory V2 & Context Compaction (ban_ke_hoach_v1 §11)."""
from __future__ import annotations

import uuid
import pytest

# Ensure ORM models are registered
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
import windagent_storage.orm.memory_v2_models  # noqa: F401

from windagent_core.domain.memory_v2 import (
    DEFAULT_SCOPE_TTL,
    LearningMetadata,
    MemoryRecordV2,
    MemoryScope,
    ValidationStatus,
)
from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError
from windagent_memory import MemoryStore
from windagent_memory.write_policy import MemoryWritePolicy
from windagent_context.compaction import ContextCompactor
from windagent_context.builder import ContextBuilder
from windagent_orchestration.long_running import CheckpointService, MemoryContextService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.agent_checkpoint_repository import AgentCheckpointRepository
from windagent_storage.repositories.memory_v2_repository import MemoryV2Repository


def _new_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def db():
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:")
    async with mgr.engine.begin() as con:
        await con.run_sync(BaseORM.metadata.create_all)
    yield mgr
    await mgr.engine.dispose()


def memory_service(dbmgr: DatabaseManager) -> MemoryContextService:
    compactor = ContextCompactor()
    return MemoryContextService(
        store=MemoryStore(),
        compactor=compactor,
        builder=ContextBuilder(compactor=compactor),
        session_factory=dbmgr.session_factory,
        memory_repo_factory=lambda s: MemoryV2Repository(s),
    )


def checkpoint_service(dbmgr: DatabaseManager) -> CheckpointService:
    return CheckpointService(
        session_factory=dbmgr.session_factory,
        checkpoint_repo_factory=lambda s: AgentCheckpointRepository(s),
    )


# ====================================================================
# 1. Memory V2 Scopes & CRUD across all 8 scopes
# ====================================================================

@pytest.mark.asyncio
async def test_memory_v2_crud_all_eight_scopes():
    store = MemoryStore()
    all_scopes = [
        MemoryScope.WORKING,
        MemoryScope.SESSION,
        MemoryScope.PROJECT,
        MemoryScope.USER,
        MemoryScope.EPISODIC,
        MemoryScope.SEMANTIC,
        MemoryScope.PROCEDURAL,
        MemoryScope.POLICY,
    ]

    for sc in all_scopes:
        rec = MemoryRecordV2(
            id=_new_id(sc.value),
            scope=sc,
            key=f"test_{sc.value}",
            value={"content": f"data for {sc.value}"},
            provenance_source="test_suite",
            project_id="proj_1" if sc in {MemoryScope.PROJECT, MemoryScope.SEMANTIC, MemoryScope.PROCEDURAL} else None,
            session_id="sess_1" if sc in {MemoryScope.SESSION, MemoryScope.WORKING, MemoryScope.EPISODIC} else None,
        )
        store.save(rec)
        fetched = store.get(
            sc,
            f"test_{sc.value}",
            project_id="proj_1" if rec.project_id else None,
            session_id="sess_1" if rec.session_id else None,
        )
        assert fetched is not None
        assert fetched.value == {"content": f"data for {sc.value}"}


# ====================================================================
# 2. Learning Metadata & Validation Statuses
# ====================================================================

def test_learning_metadata_validation_statuses():
    meta_unval = LearningMetadata(validation_status=ValidationStatus.UNVALIDATED)
    assert not meta_unval.is_validated()
    assert not meta_unval.is_terminal()

    meta_prom = LearningMetadata(
        validation_status=ValidationStatus.PROMOTED,
        confidence=0.95,
        sample_size=5,
        evidence_refs=["run_1", "run_2"],
    )
    assert meta_prom.is_validated()
    assert not meta_prom.is_terminal()

    meta_super = LearningMetadata(validation_status=ValidationStatus.SUPERSEDED)
    assert not meta_super.is_validated()
    assert meta_super.is_terminal()


# ====================================================================
# 3. Learning Admission Gate & Policy Writes
# ====================================================================

def test_learning_admission_gate_policy_checks():
    policy_validator = MemoryWritePolicy(min_promotion_confidence=0.7, min_promotion_sample_size=3)

    # Unvalidated policy with low confidence in PROPOSED status is allowed as proposed
    proposed = MemoryRecordV2(
        id=_new_id("policy"),
        scope=MemoryScope.POLICY,
        key="format_rule",
        value="use short paragraphs",
        provenance_source="script_agent",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROPOSED,
            confidence=0.3,
            sample_size=1,
        ),
    )
    policy_validator.validate_and_enforce(proposed)  # should pass

    # Promoted policy with low confidence (<0.7) must be rejected
    invalid_prom = MemoryRecordV2(
        id=_new_id("policy"),
        scope=MemoryScope.POLICY,
        key="format_rule",
        value="use short paragraphs",
        provenance_source="script_agent",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=0.4,
            sample_size=5,
            evidence_refs=["run_1"],
        ),
    )
    with pytest.raises(ValidationError):
        policy_validator.validate_and_enforce(invalid_prom)

    # Promoted policy without evidence_refs must be rejected
    invalid_no_evid = MemoryRecordV2(
        id=_new_id("policy"),
        scope=MemoryScope.POLICY,
        key="format_rule",
        value="use short paragraphs",
        provenance_source="script_agent",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=0.9,
            sample_size=5,
            evidence_refs=[],
        ),
    )
    with pytest.raises(ValidationError):
        policy_validator.validate_and_enforce(invalid_no_evid)

    # Valid promoted policy passes
    valid_prom = MemoryRecordV2(
        id=_new_id("policy"),
        scope=MemoryScope.POLICY,
        key="format_rule",
        value="use short paragraphs",
        provenance_source="script_agent",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=0.85,
            sample_size=4,
            evidence_refs=["run_42", "run_43"],
        ),
    )
    policy_validator.validate_and_enforce(valid_prom)


# ====================================================================
# 4. Secret Exclusion & Provenance Requirements
# ====================================================================

def test_secret_exclusion_and_provenance_in_memory():
    validator = MemoryWritePolicy()

    # Secret in value regex
    rec_secret = MemoryRecordV2(
        id=_new_id("mem"),
        scope=MemoryScope.WORKING,
        key="api_config",
        value="use token sk-abcd123456789012345678901",
        provenance_source="test",
    )
    with pytest.raises(PermissionDeniedError):
        validator.validate_and_enforce(rec_secret)

    # Missing provenance
    rec_no_prov = MemoryRecordV2(
        id=_new_id("mem"),
        scope=MemoryScope.WORKING,
        key="key1",
        value="val1",
        provenance_source="",
    )
    with pytest.raises(ValidationError):
        validator.validate_and_enforce(rec_no_prov)


# ====================================================================
# 5. Memory Superseding Lineage
# ====================================================================

@pytest.mark.asyncio
async def test_memory_superseding_lineage():
    store = MemoryStore()

    # Version 1 of a rule
    r1id = _new_id("rule")
    r1 = MemoryRecordV2(
        id=r1id,
        scope=MemoryScope.POLICY,
        key="hook_strategy",
        value="use startling facts",
        provenance_source="eval_01",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=0.80,
            sample_size=3,
            evidence_refs=["run_1"],
        ),
    )
    store.save(r1)

    fetched_r1 = store.get_by_id(r1id)
    assert fetched_r1 is not None
    assert fetched_r1.learning_metadata.validation_status == ValidationStatus.PROMOTED

    # Version 2 that supersedes Version 1
    r2id = _new_id("rule")
    r2 = MemoryRecordV2(
        id=r2id,
        scope=MemoryScope.POLICY,
        key="hook_strategy_v2",
        value="use demo-first hook",
        provenance_source="eval_02",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=0.92,
            sample_size=8,
            evidence_refs=["run_1", "run_2"],
            supersedes_id=r1id,
        ),
    )
    store.save(r2)

    # Record 1 should now be SUPERSEDED
    fetched_r1_after = store.get_by_id(r1id)
    assert fetched_r1_after is not None
    assert fetched_r1_after.learning_metadata.validation_status == ValidationStatus.SUPERSEDED
    assert fetched_r1_after.learning_metadata.is_terminal()

    # Record 2 is PROMOTED
    fetched_r2 = store.get_by_id(r2id)
    assert fetched_r2 is not None
    assert fetched_r2.learning_metadata.validation_status == ValidationStatus.PROMOTED


# ====================================================================
# 6. Deduplication & TTL Across V2 Scopes
# ====================================================================

def test_memory_v2_deduplication_and_ttl():
    store = MemoryStore()

    # Semantic and Policy memories have no TTL (Persistent)
    rec_sem = MemoryRecordV2(
        id=_new_id("sem"),
        scope=MemoryScope.SEMANTIC,
        key="audience_preference",
        value="developers prefer concrete code examples",
        provenance_source="analytics",
        project_id="proj_1",
    )
    assert rec_sem.get_effective_ttl() == DEFAULT_SCOPE_TTL[MemoryScope.SEMANTIC]
    assert rec_sem.get_effective_ttl() is None  # persistent

    store.save(rec_sem)

    # Deduplication: saving identical content updates timestamp, no new entry
    rec_sem_dup = MemoryRecordV2(
        id=_new_id("sem_dup"),
        scope=MemoryScope.SEMANTIC,
        key="audience_preference",
        value="developers prefer concrete code examples",
        provenance_source="analytics_v2",
        project_id="proj_1",
    )
    store.save(rec_sem_dup)

    assert store.get_by_id(rec_sem.id) is not None
    assert store.count_by_scope().get("semantic") == 1


# ====================================================================
# 7. Context Compaction & Checkpoint Integration
# ====================================================================

@pytest.mark.asyncio
async def test_compaction_and_checkpoint_integration(db):
    ms = memory_service(db)
    cs = checkpoint_service(db)
    agent = _new_id("agent")

    messages = [
        {"role": "user", "content": "Hello, lets discuss the design."},
        {"role": "assistant", "content": "We must follow policy R12 for safety."},  # critical
        {"role": "user", "content": "What about formatting?"},
        {"role": "assistant", "content": "This is just a routine explanation of formats."},
        {"role": "user", "content": "Decision: use Json outputs."},  # critical
        {"role": "assistant", "content": "Agreed. Proceeding."},
        {"role": "user", "content": "Final question on step 4."},
        {"role": "assistant", "content": "Step 4 is ready."},
    ]

    compacted, ckout = await ms.compact_and_checkpoint(
        agent_run_id=agent,
        messages=messages,
        max_keep_recent=4,
        checkpoint_service=cs,
        session_id="sess_01",
    )

    assert len(compacted) < len(messages)
    # Compacted output still includes the preserved critical decision/policy messages
    all_contents = " ".join(str(m.get("content", "")) for m in compacted)
    assert "SYSTEM SUMMARY" in all_contents
    assert "policy R12" in all_contents
    assert "Decision" in all_contents

    # Durable checkpoint was persisted at compaction boundary
    assert ckout is not None
    kind_val = ckout.get("kind") if isinstance(ckout, dict) else getattr(ckout, "kind")
    assert kind_val == "compaction"
    snapshot_val = ckout.get("snapshot") if isinstance(ckout, dict) else getattr(ckout, "snapshot")
    assert snapshot_val["stage"] == "compaction"
    assert snapshot_val["messages_before"] == 8


# ====================================================================
# 8. Prompt Context Assembly Prioritization
# ====================================================================

@pytest.mark.asyncio
async def test_prompt_context_assembly_prioritization(db):
    ms = memory_service(db)

    # 1. Policy rule (validated)
    await ms.save_memory(MemoryRecordV2(
        id=_new_id("pol"),
        scope=MemoryScope.POLICY,
        key="audit_policy",
        value="always check permissions before tool calls",
        provenance_source="security_audit",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=1.0,
            sample_size=10,
            evidence_refs=["sec_r1"],
        ),
    ))

    # 2. Semantic knowledge
    await ms.save_memory(MemoryRecordV2(
        id=_new_id("sem"),
        scope=MemoryScope.SEMANTIC,
        key="yt_audience",
        value="demo-first videos have +12pp retention",
        provenance_source="yt_analytics",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.VALIDATED,
            confidence=0.85,
            sample_size=3,
            evidence_refs=["ep042"],
        ),
    ))

    # Assemble prompt context
    compacted, fitted, trunc, manifest = await ms.assemble_prompt_context(
        task_prompt="Generate a new youtube video script",
        messages=[{"role": "user", "content": "Start project"}],
    )

    assert len(fitted) >= 2
    contents = [it.content for it in fitted]
    assert any("POLICY RULE" in c for c in contents)
    assert any("KNOWLEDGE" in c for c in contents)


# ====================================================================
# 9. Memory V2 Repository SQL And CAS Durability
# ====================================================================

@pytest.mark.asyncio
async def test_memory_v2_repository_sql_cas(db):
    r1_id = _new_id("mem_sql")
    rec = MemoryRecordV2(
        id=r1_id,
        scope=MemoryScope.SEMANTIC,
        key="coding_best_practices",
        value="use pytest for all gates",
        provenance_source="ci_guidelines",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.VALIDATED,
            confidence=0.88,
            sample_size=6,
            evidence_refs=["ci_run_10"],
        ),
    )

    # 1. Insert into SQL
    async with db.session_factory() as session:
        repo = MemoryV2Repository(session)
        saved = await repo.save_record(rec)
        await session.commit()
        assert saved is not None
        assert saved.version == 1

    # 2. Retrieve from SQL
    async with db.session_factory() as session:
        repo = MemoryV2Repository(session)
        fetched = await repo.get_by_id(r1_id)
        assert fetched is not None
        assert fetched.key == "coding_best_practices"
        assert fetched.learning_metadata.confidence == 0.88

    # 3. CAS successful update
    fetched.value = "use pytest and ruff for all gates"
    async with db.session_factory() as session:
        repo = MemoryV2Repository(session)
        updated = await repo.save_record(fetched, expected_version=1)
        await session.commit()
        assert updated is not None
        assert updated.version == 2

    # 4. CAS conflict (stale version)
    async with db.session_factory() as session:
        repo = MemoryV2Repository(session)
        conflict_res = await repo.save_record(fetched, expected_version=1)  # expected 1 but actual is 2
        assert conflict_res is None  # CAS rejection


# ====================================================================
# 10. Restart Visibility & Durability
# ====================================================================

@pytest.mark.asyncio
async def test_restart_visibility_memory_and_compaction(db):
    ms1 = memory_service(db)
    cs1 = checkpoint_service(db)
    agent_id = _new_id("agent")

    # Save a validated policy and checkpoint compaction
    policy_id = _new_id("policy")
    await ms1.save_memory(MemoryRecordV2(
        id=policy_id,
        scope=MemoryScope.POLICY,
        key="safety_gate",
        value="no database mutations in read-only modes",
        provenance_source="audit",
        learning_metadata=LearningMetadata(
            validation_status=ValidationStatus.PROMOTED,
            confidence=0.99,
            sample_size=20,
            evidence_refs=["audit_report_1"],
        ),
    ))

    await ms1.compact_and_checkpoint(
        agent_run_id=agent_id,
        messages=[{"role": "user", "content": "input"}, {"role": "assistant", "content": "output"}],
        checkpoint_service=cs1,
    )

    # Simulate service restart (create brand new service instances over same DB)
    ms2 = memory_service(db)
    cs2 = checkpoint_service(db)

    policy_after = await ms2.get_memory(MemoryScope.POLICY, "safety_gate")
    assert policy_after is not None
    assert policy_after.value == "no database mutations in read-only modes"
    assert policy_after.learning_metadata.is_validated()

    cks = await cs2.list_checkpoints(agent_id)
    assert len(cks) == 1
    ck0_kind = cks[0].get("kind") if isinstance(cks[0], dict) else getattr(cks[0], "kind")
    assert ck0_kind == "compaction"
