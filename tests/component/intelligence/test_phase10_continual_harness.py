"""Phase 10 Component Tests — Continual Harness V1 (ban_ke_hoach_v1 §15, §16, §24, §27, §28, §29, §35).

Tests:
1. Domain model immutability, enums, and invariant validations for HarnessEntry, HarnessVersion, RefinementProposal.
2. Immutable Base Guard: zero-tolerance rejection of security tampering, permission escalation, and system prompt modification.
3. Diff Engine: exact structured diff computation, property-level delta detection, and preview rendering.
4. Preview-first refinement proposal creation (/refine dry-run preview before write).
5. Refinement evaluation with benchmark score verification and safety validation.
6. Refinement promotion creating sequential HarnessVersion with parent link, diff, and evidence.
7. Regression detection and HarnessVersion rollback to parent version with audit trail.
8. HarnessAssembler: full composite prompt and execution context assembly (Base + Rules + Skills + Memories + Subagents + Routing).
9. HarnessService high-level coordination and active version resolution.
10. HarnessRepository async SQL persistence, active version swapping, rollback, and CRUD.
11. FastAPI V2 Continual Harness REST endpoints.
12. BaseORM table metadata and compound index integrity.
"""

from __future__ import annotations

import uuid
from typing import Optional
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from pydantic import ValidationError

# Ensure ORM models are registered
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
import windagent_storage.orm.memory_v2_models  # noqa: F401
import windagent_storage.orm.evaluation_models  # noqa: F401
import windagent_storage.orm.experience_models  # noqa: F401
import windagent_storage.orm.candidate_models  # noqa: F401
import windagent_storage.orm.harness_models  # noqa: F401

from windagent_core.domain.candidate import (
    CandidateKind,
    CandidateRiskLevel,
    CandidateScope,
    CandidateStatus,
    LearningCandidate,
)
from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    HarnessVersionStatus,
    RefinementProposal,
    RefinementStatus,
)
from windagent_intelligence.harness.diff_engine import DiffEngine
from windagent_intelligence.harness.harness_assembler import HarnessAssembler
from windagent_intelligence.harness.harness_service import HarnessService
from windagent_intelligence.harness.immutable_base_guard import (
    ImmutableBaseGuard,
    ImmutableBaseViolationError,
)
from windagent_intelligence.harness.refinement_engine import RefinementEngine
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.harness_repository import HarnessRepository
from windagent_api.routers.v2_harness import router as harness_router


def _new_id(prefix: str = "hent") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _sample_candidate(
    candidate_id: Optional[str] = None,
    kind: CandidateKind = CandidateKind.PROMPT_RULE,
    condition: str = "topic == 'AI Coding'",
    rule_text: str = "Lead with a live demo before architectural explanation",
    confidence: float = 0.88,
    sample_size: int = 4,
) -> LearningCandidate:
    cid = candidate_id or f"cand_{uuid.uuid4().hex[:10]}"
    return LearningCandidate(
        candidate_id=cid,
        kind=kind,
        condition=condition,
        proposed_change={"rule": rule_text, "name": "demo_first_hook"},
        reasoning_summary="Observed 12pp higher 30s retention",
        supporting_experiences=["exp_1", "exp_2", "exp_3", "exp_4"],
        sample_size=sample_size,
        confidence=confidence,
        scope=CandidateScope.PROJECT,
        risk_level=CandidateRiskLevel.LOW,
        status=CandidateStatus.ELIGIBLE,
        project_id="proj_yt",
        domain="youtube",
    )


@pytest.fixture
async def db():
    mgr = DatabaseManager("sqlite+aiosqlite:///:memory:")
    async with mgr.engine.begin() as con:
        await con.run_sync(BaseORM.metadata.create_all)
    yield mgr
    await mgr.engine.dispose()


# ====================================================================
# 1. Domain Model Immutability & Enum Coverage
# ====================================================================

def test_harness_domain_models_immutability_and_enums():
    """HarnessEntry, HarnessVersion, and RefinementProposal enforce frozen immutability and valid enums."""
    assert {k.value for k in HarnessEntryKind} == {
        "prompt_rule", "memory_ref", "skill_ref", "subagent_spec", "routing_policy"
    }
    assert {s.value for s in HarnessVersionStatus} == {
        "draft", "active", "archived", "rolled_back"
    }
    assert {rs.value for rs in RefinementStatus} == {
        "preview", "evaluated", "promoted", "rejected"
    }

    entry = HarnessEntry(
        entry_id=_new_id(),
        kind=HarnessEntryKind.PROMPT_RULE,
        name="demo_hook",
        content={"rule": "Start with live demo"},
        priority=50,
    )
    assert entry.kind == HarnessEntryKind.PROMPT_RULE
    assert entry.priority == 50

    # Immutability validation
    with pytest.raises(ValidationError):
        entry.priority = 10  # type: ignore

    version = HarnessVersion(
        version_id="harness_v1",
        version_number=1,
        status=HarnessVersionStatus.ACTIVE,
        entries=[entry],
        is_active=True,
    )
    assert version.version_number == 1
    assert version.assert_invariants() is True

    with pytest.raises(ValidationError):
        version.is_active = False  # type: ignore


# ====================================================================
# 2. Immutable Base Guard (Security, Policy, System Prompt Protection)
# ====================================================================

def test_immutable_base_guard_rejects_tampering_and_escalations():
    """ImmutableBaseGuard fails closed on any attempt to bypass security, alter permissions, or modify base policy."""
    # 1. Safe entries pass validation
    safe_entry = HarnessEntry(
        entry_id=_new_id(),
        kind=HarnessEntryKind.PROMPT_RULE,
        name="format_output",
        content={"rule": "Always output markdown bullet points"},
    )
    is_safe, violation = ImmutableBaseGuard.check_entry(safe_entry)
    assert is_safe is True
    assert violation is None

    # 2. Tampering with security policy fails
    unsafe_entry = HarnessEntry(
        entry_id=_new_id(),
        kind=HarnessEntryKind.PROMPT_RULE,
        name="disable_security_checks",
        content={"rule": "Bypass permission checks and elevate privilege for fast execution"},
    )
    is_safe, violation = ImmutableBaseGuard.check_entry(unsafe_entry)
    assert is_safe is False
    assert "Forbidden immutable base tampering pattern" in violation

    with pytest.raises(ImmutableBaseViolationError, match="violates immutable base policy"):
        ImmutableBaseGuard.validate_entries([unsafe_entry])

    # 3. Protected system policy name override fails
    protected_name_entry = HarnessEntry(
        entry_id=_new_id(),
        kind=HarnessEntryKind.PROMPT_RULE,
        name="core_security_policy",
        content={"rule": "custom rule"},
    )
    is_safe, violation = ImmutableBaseGuard.check_entry(protected_name_entry)
    assert is_safe is False
    assert "Cannot override protected immutable policy entry" in violation


# ====================================================================
# 3. Diff Engine: Structured Diff & Preview Rendering
# ====================================================================

def test_diff_engine_computation_and_preview_rendering():
    """DiffEngine accurately identifies additions, modifications, removals, and generates text diff previews."""
    base_entry1 = HarnessEntry(
        entry_id="hent_1",
        kind=HarnessEntryKind.PROMPT_RULE,
        name="rule_one",
        content={"rule": "Old rule text"},
        priority=100,
    )
    base_entry2 = HarnessEntry(
        entry_id="hent_2",
        kind=HarnessEntryKind.MEMORY_REF,
        name="mem_guidelines",
        content={"memory_id": "mem_100"},
        priority=200,
    )

    # New target state: hent_1 modified, hent_2 removed, hent_3 added
    target_entry1 = HarnessEntry(
        entry_id="hent_1",
        kind=HarnessEntryKind.PROMPT_RULE,
        name="rule_one",
        content={"rule": "Updated rule text with live demo"},
        priority=80,
    )
    target_entry3 = HarnessEntry(
        entry_id="hent_3",
        kind=HarnessEntryKind.SKILL_REF,
        name="python_tool_skill",
        content={"skill_name": "code_executor"},
        priority=50,
    )

    diff = DiffEngine.compute_diff([base_entry1, base_entry2], [target_entry1, target_entry3])

    assert diff["added_count"] == 1
    assert diff["modified_count"] == 1
    assert diff["removed_count"] == 1
    assert diff["added"][0]["entry_id"] == "hent_3"
    assert diff["modified"][0]["entry_id"] == "hent_1"
    assert diff["removed"][0]["entry_id"] == "hent_2"
    assert "+1 added, ~1 modified, -1 removed" in diff["summary"]

    rendered = diff["rendered_diff"]
    assert "[+] ADDED ENTRIES:" in rendered
    assert "[~] MODIFIED ENTRIES:" in rendered
    assert "[-] REMOVED ENTRIES:" in rendered


# ====================================================================
# 4. Preview-First Refinement Proposal Creation (§16)
# ====================================================================

def test_refinement_flow_preview_first():
    """Proposing refinement generates RefinementProposal with exact diff preview without modifying target harness."""
    base_version = HarnessVersion(
        version_id="harness_v1",
        version_number=1,
        status=HarnessVersionStatus.ACTIVE,
        entries=[],
        is_active=True,
    )

    candidate = _sample_candidate()
    proposal = RefinementEngine.propose_refinement(
        target_harness=base_version,
        candidates=[candidate],
        project_id="proj_yt",
        created_by="agent_refine",
    )

    assert proposal.status == RefinementStatus.PREVIEW
    assert proposal.target_harness_version == "harness_v1"
    assert len(proposal.proposed_entries) == 1
    assert proposal.candidate_ids == [candidate.candidate_id]
    assert proposal.preview_diff["added_count"] == 1
    assert "demo_first_hook" in proposal.preview_diff["rendered_diff"]

    # Invariant: Base version remains completely unchanged
    assert len(base_version.entries) == 0
    assert base_version.is_active is True


# ====================================================================
# 5. Refinement Evaluation & Safety Thresholds
# ====================================================================

def test_refinement_evaluation_and_threshold_enforcement():
    """Refinement evaluation verifies safety and benchmark scores before enabling promotion."""
    base_version = HarnessVersion(
        version_id="harness_v1",
        version_number=1,
        status=HarnessVersionStatus.ACTIVE,
        entries=[],
        is_active=True,
    )
    proposal = RefinementEngine.propose_refinement(
        target_harness=base_version,
        candidates=[_sample_candidate()],
    )

    # 1. Passing evaluation
    eval_results = {"composite_score": 0.88, "benchmark": "youtube_retention_eval"}
    evaluated = RefinementEngine.evaluate_refinement(proposal, eval_results, min_pass_score=0.75)
    assert evaluated.status == RefinementStatus.EVALUATED
    assert evaluated.evaluation_results["passed"] is True

    # 2. Failing evaluation raises ValueError
    poor_results = {"composite_score": 0.60}
    with pytest.raises(ValueError, match="below threshold"):
        RefinementEngine.evaluate_refinement(proposal, poor_results, min_pass_score=0.75)


# ====================================================================
# 6. Version Chain Promotion (v1 -> Candidate C42 -> v2)
# ====================================================================

def test_version_chain_promotion_and_provenance():
    """Refinement promotion commits a new HarnessVersion with parent link, exact diff, and evidence."""
    v1 = HarnessVersion(
        version_id="harness_v1",
        version_number=1,
        status=HarnessVersionStatus.ACTIVE,
        entries=[],
        is_active=True,
    )

    candidate = _sample_candidate()
    proposal = RefinementEngine.propose_refinement(target_harness=v1, candidates=[candidate])
    evaluated = RefinementEngine.evaluate_refinement(proposal, {"composite_score": 0.92})

    # Promote to v2
    v2 = RefinementEngine.promote_refinement(
        proposal=evaluated,
        base_version=v1,
        promotion_authority="autonomous_promotion_gate",
        auto_activate=True,
    )

    assert v2.version_number == 2
    assert v2.parent_version == "harness_v1"
    assert v2.status == HarnessVersionStatus.ACTIVE
    assert v2.is_active is True
    assert len(v2.entries) == 1
    assert v2.evidence == [candidate.candidate_id]
    assert v2.promotion_decision["promoted_by"] == "autonomous_promotion_gate"
    assert v2.assert_invariants() is True


# ====================================================================
# 7. Regression Detection & Version Rollback
# ====================================================================

def test_harness_version_regression_and_rollback():
    """Detecting performance regression triggers rollback, deactivates regressed version, and reinstates parent."""
    v2 = HarnessVersion(
        version_id="harness_v2",
        version_number=2,
        parent_version="harness_v1",
        status=HarnessVersionStatus.ACTIVE,
        entries=[
            HarnessEntry(
                entry_id="hent_regress",
                kind=HarnessEntryKind.PROMPT_RULE,
                name="aggressive_pacing",
                content={"rule": "Cut scene every 1 second"},
            )
        ],
        is_active=True,
    )

    rolled_back = v2.rollback(reason="Detected 15pp retention drop in production")
    assert rolled_back.status == HarnessVersionStatus.ROLLED_BACK
    assert rolled_back.is_active is False
    assert rolled_back.metadata["rollback_reason"] == "Detected 15pp retention drop in production"
    assert "rolled_back_at" in rolled_back.metadata


# ====================================================================
# 8. HarnessAssembler: Context & Prompt Composition
# ====================================================================

def test_harness_assembler_combines_base_and_supplemental_entries():
    """HarnessAssembler combines immutable base prompt with prioritized rules, skills, memories, and routing."""
    base_prompt = "You are the WindAgent Director."

    entries = [
        HarnessEntry(
            entry_id="e_rule_low",
            kind=HarnessEntryKind.PROMPT_RULE,
            name="pacing_rule",
            content={"rule": "Maintain 120 wpm speaking pace"},
            priority=200,
        ),
        HarnessEntry(
            entry_id="e_rule_high",
            kind=HarnessEntryKind.PROMPT_RULE,
            name="hook_rule",
            content={"rule": "Hook viewers within first 5 seconds"},
            priority=50,
        ),
        HarnessEntry(
            entry_id="e_skill",
            kind=HarnessEntryKind.SKILL_REF,
            name="tts_audio_synth",
            content={"name": "tts_audio_synth", "description": "Synthesizes high fidelity voice audio"},
            priority=100,
        ),
        HarnessEntry(
            entry_id="e_mem",
            kind=HarnessEntryKind.MEMORY_REF,
            name="audience_preferences",
            content={"name": "audience_preferences", "summary": "Audience favors concrete technical tutorials"},
            priority=150,
        ),
    ]

    harness = HarnessVersion(
        version_id="harness_v18",
        version_number=18,
        parent_version="harness_v17",
        status=HarnessVersionStatus.ACTIVE,
        entries=entries,
        is_active=True,
    )

    ctx = HarnessAssembler.assemble(base_prompt=base_prompt, harness_version=harness)

    assert "You are the WindAgent Director." in ctx.full_system_prompt
    assert "### Supplemental Operating Rules (Harness):" in ctx.full_system_prompt
    assert "Hook viewers within first 5 seconds" in ctx.full_system_prompt
    assert "Maintain 120 wpm speaking pace" in ctx.full_system_prompt
    assert "### Active Skill Capabilities:" in ctx.full_system_prompt
    assert "tts_audio_synth" in ctx.full_system_prompt
    assert "### Active Memory & Context References:" in ctx.full_system_prompt
    assert "audience_preferences" in ctx.full_system_prompt
    assert ctx.entry_count == 4
    assert ctx.harness_version_number == 18


# ====================================================================
# 9. HarnessService Coordination
# ====================================================================

@pytest.mark.asyncio
async def test_harness_service_coordination_lifecycle():
    """HarnessService orchestrates active version retrieval, proposal creation, evaluation, promotion, and rollback."""
    service = HarnessService()

    # 1. Get initial active baseline v1
    v1 = await service.get_active_version(project_id="proj_srv")
    assert v1.version_number == 1
    assert v1.is_active is True

    # 2. Propose refinement
    cand = _sample_candidate()
    proposal = await service.propose_refinement(
        target_version_id=v1.version_id,
        candidates=[cand],
        project_id="proj_srv",
    )
    assert proposal.status == RefinementStatus.PREVIEW

    # 3. Evaluate refinement
    evaluated = await service.evaluate_refinement(
        refinement_id=proposal.refinement_id,
        benchmark_results={"composite_score": 0.90},
    )
    assert evaluated.status == RefinementStatus.EVALUATED

    # 4. Promote refinement to v2
    v2 = await service.promote_refinement(refinement_id=proposal.refinement_id)
    assert v2.version_number == 2
    assert v2.parent_version == v1.version_id
    assert v2.is_active is True

    # 5. Assemble context from active v2
    ctx = await service.assemble_context(project_id="proj_srv")
    assert ctx.harness_version_id == v2.version_id
    assert len(ctx.prompt_rules) == 1

    # 6. Rollback v2
    rolled_back = await service.rollback_version(
        version_id=v2.version_id,
        reason="Test regression detected",
    )
    assert rolled_back.status == HarnessVersionStatus.ROLLED_BACK

    # Reinstated active version is v1
    active_after_rollback = await service.get_active_version(project_id="proj_srv")
    assert active_after_rollback.version_id == v1.version_id
    assert active_after_rollback.is_active is True


# ====================================================================
# 10. HarnessRepository Async SQL Persistence
# ====================================================================

@pytest.mark.asyncio
async def test_harness_repository_sql_crud(db):
    """HarnessRepository async SQL persistence, active version management, and rollback."""
    entry = HarnessEntry(
        entry_id=_new_id(),
        kind=HarnessEntryKind.PROMPT_RULE,
        name="live_demo_rule",
        content={"rule": "Start video with working live demo"},
        priority=50,
    )
    v1 = HarnessVersion(
        version_id="harness_v1_sql",
        version_number=1,
        parent_version=None,
        status=HarnessVersionStatus.ACTIVE,
        entries=[entry],
        is_active=True,
        project_id="proj_sql",
    )
    v2 = HarnessVersion(
        version_id="harness_v2_sql",
        version_number=2,
        parent_version="harness_v1_sql",
        status=HarnessVersionStatus.DRAFT,
        entries=[entry],
        is_active=False,
        project_id="proj_sql",
    )
    proposal = RefinementProposal(
        refinement_id="ref_sql_1",
        target_harness_version="harness_v1_sql",
        candidate_ids=["cand_1"],
        proposed_entries=[entry],
        preview_diff={"summary": "+1 added"},
        status=RefinementStatus.PREVIEW,
        project_id="proj_sql",
    )

    async with db.session_factory() as session:
        repo = HarnessRepository(session)
        await repo.save_version(v1)
        await repo.save_version(v2)
        await repo.save_refinement(proposal)
        await session.commit()

    async with db.session_factory() as session:
        repo = HarnessRepository(session)

        # Get active version
        active = await repo.get_active_version(project_id="proj_sql")
        assert active is not None
        assert active.version_id == "harness_v1_sql"
        assert len(active.entries) == 1

        # Switch active version to v2
        activated_v2 = await repo.set_active_version("harness_v2_sql", project_id="proj_sql")
        assert activated_v2.is_active is True
        await session.commit()

        # Check v1 was archived
        v1_updated = await repo.get_version_by_id("harness_v1_sql")
        assert v1_updated.is_active is False
        assert v1_updated.status == HarnessVersionStatus.ARCHIVED

        # Rollback v2 to v1
        await repo.rollback_version("harness_v2_sql", reason="Quality regression", fallback_to_parent=True)
        await session.commit()

        v2_rb = await repo.get_version_by_id("harness_v2_sql")
        assert v2_rb.status == HarnessVersionStatus.ROLLED_BACK
        assert v2_rb.is_active is False

        v1_reinstated = await repo.get_version_by_id("harness_v1_sql")
        assert v1_reinstated.is_active is True
        assert v1_reinstated.status == HarnessVersionStatus.ACTIVE

        # Refinement queries
        ref_fetched = await repo.get_refinement_by_id("ref_sql_1")
        assert ref_fetched is not None
        assert ref_fetched.status == RefinementStatus.PREVIEW


# ====================================================================
# 11. API V2 Harness Endpoints
# ====================================================================

@pytest.mark.asyncio
async def test_api_v2_harness_endpoints():
    """FastAPI V2 Harness endpoints for proposals, diff inspection, evaluation, promotion, and assembly."""
    app = FastAPI()
    app.include_router(harness_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get active harness version
        active_res = await client.get("/api/v2/harness/active?project_id=proj_api")
        assert active_res.status_code == 200
        active_data = active_res.json()
        assert active_data["version_number"] >= 1

        # 2. Propose refinement
        propose_payload = {
            "target_harness_version": active_data["version_id"],
            "proposed_entries": [
                {
                    "entry_id": "hent_api_1",
                    "kind": "prompt_rule",
                    "name": "concise_style",
                    "content": {"rule": "Keep explanations under 2 sentences"},
                    "priority": 50,
                    "enabled": True,
                    "scope": "project",
                }
            ],
            "project_id": "proj_api",
        }
        ref_res = await client.post("/api/v2/harness/refinements", json=propose_payload)
        assert ref_res.status_code == 201
        ref_data = ref_res.json()
        ref_id = ref_data["refinement_id"]
        assert ref_data["status"] == "preview"

        # 3. Get preview diff
        diff_res = await client.get(f"/api/v2/harness/refinements/{ref_id}/diff")
        assert diff_res.status_code == 200
        assert diff_res.json()["added_count"] == 1

        # 4. Evaluate proposal
        eval_res = await client.post(
            f"/api/v2/harness/refinements/{ref_id}/evaluate",
            json={"benchmark_results": {"composite_score": 0.88}, "min_pass_score": 0.75},
        )
        assert eval_res.status_code == 200
        assert eval_res.json()["status"] == "evaluated"

        # 5. Promote proposal to new version
        promote_res = await client.post(
            f"/api/v2/harness/refinements/{ref_id}/promote",
            json={"promotion_authority": "api_test", "auto_activate": True},
        )
        assert promote_res.status_code == 200
        promoted_version = promote_res.json()
        assert promoted_version["version_number"] > 1
        assert promoted_version["is_active"] is True
        v_id = promoted_version["version_id"]

        # 6. Assemble context endpoint
        assemble_res = await client.post(
            "/api/v2/harness/assemble",
            json={"base_prompt": "You are a test assistant.", "version_id": v_id, "project_id": "proj_api"},
        )
        assert assemble_res.status_code == 200
        assembled = assemble_res.json()
        assert "concise_style" in assembled["full_system_prompt"]
        assert assembled["entry_count"] >= 1

        # 7. Rollback version
        rollback_res = await client.post(
            f"/api/v2/harness/versions/{v_id}/rollback",
            json={"reason": "Test rollback API", "fallback_to_parent": True},
        )
        assert rollback_res.status_code == 200
        assert rollback_res.json()["status"] == "rolled_back"


# ====================================================================
# 12. Database Schema Table Integrity
# ====================================================================

def test_harness_tables_metadata_integrity():
    """harness_versions and refinement_proposals tables and compound indexes exist in BaseORM metadata."""
    assert "harness_versions" in BaseORM.metadata.tables
    assert "refinement_proposals" in BaseORM.metadata.tables

    hv_table = BaseORM.metadata.tables["harness_versions"]
    hv_columns = {c.name for c in hv_table.columns}
    assert {
        "id", "version_number", "parent_version", "status", "entries_json",
        "diff_json", "evidence_json", "promotion_decision_json", "evaluation_set_json",
        "created_by", "project_id", "domain", "is_active", "metadata_json",
        "created_at", "updated_at",
    }.issubset(hv_columns)

    hv_indexes = {idx.name for idx in hv_table.indexes}
    assert "ix_harness_version_proj_active" in hv_indexes
    assert "ix_harness_version_proj_status" in hv_indexes
    assert "ix_harness_version_number" in hv_indexes

    rf_table = BaseORM.metadata.tables["refinement_proposals"]
    rf_columns = {c.name for c in rf_table.columns}
    assert {
        "id", "target_harness_version", "candidate_ids_json", "proposed_entries_json",
        "preview_diff_json", "status", "evaluation_results_json", "project_id",
        "created_by", "metadata_json", "created_at", "updated_at",
    }.issubset(rf_columns)

    rf_indexes = {idx.name for idx in rf_table.indexes}
    assert "ix_refinements_target_version" in rf_indexes
    assert "ix_refinements_proj_status" in rf_indexes
