"""
Comprehensive Test Suite for Stage F — Human + Agent Collaboration (UI37 & UI38).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app
from windagent_core.domain.video_production.collaboration_proposal import (
    ProposalStatus,
    ProposalType,
    ProductionChangeProposal,
    SensitiveOperationPolicy,
    UniversalProposalService,
    compute_proposal_hash,
)
from windagent_core.domain.video_production.activity_timeline import (
    ActivityCategory,
    ActivityProjector,
    sanitize_text,
)
from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError


@pytest.fixture(autouse=True)
def reset_stores():
    UniversalProposalService.clear_store()
    ActivityProjector.clear_store()


def test_universal_proposal_creation():
    candidate = {"action": "REWRITE", "text": "Polished scene dialogue"}
    proposal = UniversalProposalService.create_proposal(
        project_id="proj_f_01",
        proposal_type=ProposalType.SCREENPLAY_CHANGE,
        target_revision_id="rev_01",
        base_sequence=1,
        creator_actor="agent:script_writer",
        candidate_payload=candidate,
        affected_entities=["sc_01"],
    )

    assert proposal.proposal_id.startswith("prop_")
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.created_by_agent == "agent:script_writer"
    assert proposal.hash == compute_proposal_hash(candidate)
    assert proposal.diff["changes_count"] > 0
    assert proposal.impact["invalidation_intent"] == "INVALIDATE_SHOT_PLAN"


def test_proposal_stale_detection():
    candidate = {"asset_id": "ast_01", "role": "LEAD"}
    proposal = UniversalProposalService.create_proposal(
        project_id="proj_f_02",
        proposal_type=ProposalType.ASSET_BINDING_CHANGE,
        target_revision_id="rev_01",
        base_sequence=1,
        creator_actor="agent:asset_binder",
        candidate_payload=candidate,
    )

    # Current sequence advances past base_sequence (1 -> 2)
    stale_proposal = UniversalProposalService.evaluate_stale_status(
        proposal.proposal_id, current_project_sequence=2
    )

    assert stale_proposal.status == ProposalStatus.REQUIRES_REVIEW


@pytest.mark.asyncio
async def test_proposal_approval_flow():
    candidate = {"action": "UPDATE", "target_scene": "sc_02"}
    proposal = UniversalProposalService.create_proposal(
        project_id="proj_f_03",
        proposal_type=ProposalType.SCREENPLAY_CHANGE,
        target_revision_id="rev_01",
        base_sequence=1,
        creator_actor="agent:assistant",
        candidate_payload=candidate,
    )

    approved = await UniversalProposalService.approve_proposal(
        proposal_id=proposal.proposal_id,
        approver_actor="user:lead_director",
        current_project_sequence=1,
        reason="Looks great for production",
    )

    assert approved.status == ProposalStatus.APPROVED
    assert approved.decision_by == "user:lead_director"
    assert approved.decision_reason == "Looks great for production"
    assert approved.resulting_command_id is not None
    assert approved.resulting_revision_id is not None


def test_proposal_rejection_flow():
    candidate = {"license": "COMMERCIAL_UNAUTHORIZED"}
    proposal = UniversalProposalService.create_proposal(
        project_id="proj_f_04",
        proposal_type=ProposalType.LICENSE_CHANGE,
        target_revision_id="rev_01",
        base_sequence=1,
        creator_actor="agent:compliance",
        candidate_payload=candidate,
    )

    rejected = UniversalProposalService.reject_proposal(
        proposal_id=proposal.proposal_id,
        rejector_actor="user:legal_reviewer",
        reason="License type is unauthorized",
    )

    assert rejected.status == ProposalStatus.REJECTED
    assert rejected.decision_by == "user:legal_reviewer"
    assert rejected.decision_reason == "License type is unauthorized"


@pytest.mark.asyncio
async def test_hash_tamper_detection():
    candidate = {"text": "Original dialogue"}
    proposal = UniversalProposalService.create_proposal(
        project_id="proj_f_05",
        proposal_type=ProposalType.SCREENPLAY_CHANGE,
        target_revision_id="rev_01",
        base_sequence=1,
        creator_actor="agent:writer",
        candidate_payload=candidate,
    )

    # Tamper payload after submission
    proposal.candidate["text"] = "TAMPERED dialogue text!"

    with pytest.raises(ValidationError) as exc_info:
        await UniversalProposalService.approve_proposal(
            proposal_id=proposal.proposal_id,
            approver_actor="user:director",
            current_project_sequence=1,
        )

    assert "tamper detected" in str(exc_info.value)
    assert proposal.status == ProposalStatus.APPLY_FAILED


def test_security_policy_agent_bypass_blocked():
    # Agent attempting direct sensitive operation without approved proposal
    with pytest.raises(PermissionDeniedError) as exc_info:
        SensitiveOperationPolicy.validate_command_execution(
            operation_type=ProposalType.SCREENPLAY_CHANGE,
            actor="agent:rogue_bot",
            approved_proposal=None,
        )

    assert "AGENT_SENSITIVE_OPERATION_BLOCKED" in str(exc_info.value.code)


def test_security_policy_agent_self_approval_prohibited():
    proposal = ProductionChangeProposal(
        proposal_id="prop_test_01",
        proposal_type=ProposalType.ASSET_APPROVAL_CHANGE,
        project_id="proj_f_06",
        target_revision_id="rev_01",
        base_sequence=1,
        candidate={"status": "APPROVED"},
        created_by_agent="agent:self_approver",
        created_at="2026-08-08T12:00:00Z",
        status=ProposalStatus.PENDING,
        hash="test_hash",
    )

    with pytest.raises(PermissionDeniedError) as exc_info:
        SensitiveOperationPolicy.validate_approval_permissions(
            proposal=proposal,
            approver_actor="agent:self_approver",
            prohibit_self_approval=True,
        )

    assert "SELF_APPROVAL_PROHIBITED" in str(exc_info.value.code)


def test_activity_timeline_sanitization_and_projection():
    # Secret and file path sanitization test
    raw_path_text = "Exported to C:\\Users\\Admin\\secret_path\\file.mp4 with sk-1234567890abcdef API key"
    sanitized = sanitize_text(raw_path_text)

    assert "[LOCAL_FILE_PATH]" in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "sk-1234567890abcdef" not in sanitized

    # Activity Projection
    act = ActivityProjector.project_event(
        event_id="evt_01",
        project_id="proj_f_07",
        revision_id="rev_01",
        event_type="PROPOSAL_CREATED",
        actor="agent:script_assistant",
        payload={"proposal_id": "prop_100", "proposal_type": "SCREENPLAY_CHANGE"},
    )

    assert act is not None
    assert act.category == ActivityCategory.PROPOSAL
    assert act.actor == "agent:script_assistant"
    assert len(act.entity_links) == 1
    assert act.entity_links[0].entity_id == "prop_100"


def test_activity_timeline_replay_convergence():
    events = [
        {
            "event_id": "evt_replay_01",
            "project_id": "proj_f_08",
            "revision_id": "rev_01",
            "event_type": "WORKSPACE_COMMAND_UPDATE_SCREENPLAY",
            "actor": "user:director",
            "payload": {"entity_id": "sc_01"},
            "correlation_id": "corr_01",
        },
        {
            "event_id": "evt_replay_02",
            "project_id": "proj_f_08",
            "revision_id": "rev_01",
            "event_type": "PROPOSAL_CREATED",
            "actor": "agent:assistant",
            "payload": {"proposal_id": "prop_200", "proposal_type": "ASSET_BINDING_CHANGE"},
            "correlation_id": "corr_02",
        },
    ]

    first_pass = ActivityProjector.replay_event_stream(events)
    count_pass_1 = len(first_pass)

    # Replay same stream again
    second_pass = ActivityProjector.replay_event_stream(events)
    count_pass_2 = len(second_pass)

    # Output count and identities must be strictly identical (zero duplicate activities)
    assert count_pass_1 == count_pass_2 == 2


def test_api_v2_collaboration_endpoints():
    """Phase 15: the V2 collaboration HTTP surface is retired (410 tombstone).

    The collaboration domain logic above remains canonical; the retired
    /api/v2/collaboration/* routes are pinned here.
    """
    client = TestClient(app)

    create_payload = {
        "project_id": "proj_api_f",
        "proposal_type": "SCREENPLAY_CHANGE",
        "target_revision_id": "rev_01",
        "base_sequence": 1,
        "creator_actor": "agent:api_writer",
        "candidate_payload": {"text": "API proposal text"},
        "affected_entities": ["sc_10"],
    }
    resp = client.post("/api/v2/collaboration/proposals", json=create_payload)
    assert resp.status_code == 410
    assert resp.json()["title"] == "API V2 Retired"

    list_resp = client.get("/api/v2/collaboration/proposals?project_id=proj_api_f")
    assert list_resp.status_code == 410

    detail_resp = client.get("/api/v2/collaboration/proposals/prop_any")
    assert detail_resp.status_code == 410

    rej_resp = client.post(
        "/api/v2/collaboration/proposals/prop_any/reject",
        json={"rejector_actor": "user:editor", "reason": "Requires further revision"},
    )
    assert rej_resp.status_code == 410

    timeline_resp = client.get("/api/v2/collaboration/timeline?project_id=proj_api_f")
    assert timeline_resp.status_code == 410
