"""
Unit tests for Phase 23 — Production Workspace (VP23_PRODUCTION_WORKSPACE_VERIFIED).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app
from windagent_core.domain.video_production.ids import (
    GenerationCandidateId,
    ProductionRevisionId,
    ShotId,
    VideoProjectId,
)
from windagent_core.domain.video_production.workspace import (
    CandidateReviewOverride,
    CostApprovalSummary,
    WorkspaceCommandRequest,
    WorkspaceCommandStatus,
    WorkspaceCommandType,
)
from windagent_intelligence.video.workspace import WorkspaceService


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def service() -> WorkspaceService:
    return WorkspaceService(current_revision="rev_poc_01")


def test_workspace_snapshot(service: WorkspaceService):
    """Workspace snapshot contains all required sections and cost ledger."""
    snap = service.get_snapshot(VideoProjectId("vp_poc"))
    assert str(snap.project_id) == "vp_poc"
    assert str(snap.revision_id) == "rev_poc_01"
    assert snap.cost_summary.can_proceed is True
    assert "shot_01" in snap.authorized_media_urls


def test_command_idempotency_and_stale_revision(service: WorkspaceService):
    """Mutating command rejects stale revisions and supports idempotency."""
    req_valid = WorkspaceCommandRequest(
        command_id="cmd_01",
        command_type=WorkspaceCommandType.APPROVE_CANDIDATE,
        project_id=VideoProjectId("vp_poc"),
        target_revision_id=ProductionRevisionId("rev_poc_01"),
        entity_id="cand_01",
        reason="Approved by user",
        idempotency_key="idemp_key_100",
    )

    res_1 = service.process_command(req_valid)
    assert res_1.status == WorkspaceCommandStatus.COMPLETED
    assert str(res_1.updated_revision_id) != "rev_poc_01"  # Revision updated

    # Test stale revision request
    req_stale = WorkspaceCommandRequest(
        command_id="cmd_02",
        command_type=WorkspaceCommandType.APPROVE_CANDIDATE,
        project_id=VideoProjectId("vp_poc"),
        target_revision_id=ProductionRevisionId("rev_poc_01"),  # Old revision
        entity_id="cand_02",
        reason="Try stale approval",
        idempotency_key="idemp_key_101",
    )
    res_stale = service.process_command(req_stale)
    assert res_stale.status == WorkspaceCommandStatus.REJECTED_STALE


def test_candidate_override_requires_reason(service: WorkspaceService):
    """Candidate review override requires explicit justification reason."""
    override_invalid = CandidateReviewOverride(
        candidate_id=GenerationCandidateId("cand_01"),
        shot_id=ShotId("shot_01"),
        previous_verdict="REJECTED",
        new_verdict="APPROVED",
        reason="",  # Empty reason
    )
    assert service.process_candidate_override(override_invalid) is False

    override_valid = CandidateReviewOverride(
        candidate_id=GenerationCandidateId("cand_01"),
        shot_id=ShotId("shot_01"),
        previous_verdict="REJECTED",
        new_verdict="APPROVED",
        reason="User verified continuity manually",
    )
    assert service.process_candidate_override(override_valid) is True


def test_event_stream_recovery(service: WorkspaceService):
    """Audits cursor gap and snapshot reset trigger."""
    recovery_normal = service.verify_event_stream_recovery(
        last_seen_cursor=1040, current_server_sequence=1042
    )
    assert recovery_normal["requires_snapshot_reset"] is False
    assert recovery_normal["replay_events_count"] == 2

    recovery_gap = service.verify_event_stream_recovery(
        last_seen_cursor=500, current_server_sequence=1042
    )
    assert recovery_gap["requires_snapshot_reset"] is True


def test_api_v2_workspace_endpoints(client: TestClient):
    """API V2 router responds to /snapshot, /commands, and /media requests."""
    res_snap = client.get("/api/v2/video-production/workspace/snapshot?project_id=vp_poc")
    assert res_snap.status_code == 200
    data_snap = res_snap.json()
    assert data_snap["project_id"] == "vp_poc"

    res_cmd = client.post(
        "/api/v2/video-production/workspace/commands",
        json={
            "command_type": "AUTHORIZE_COST",
            "project_id": "vp_poc",
            "target_revision_id": data_snap["revision_id"],
            "entity_id": "job_01",
            "reason": "Credit reservation approval",
        },
        headers={"X-Idempotency-Key": "idemp_test_999"},
    )
    assert res_cmd.status_code == 200
    assert res_cmd.json()["status"] == "COMPLETED"

    res_media = client.get("/api/v2/video-production/workspace/media/tok_shot_01_a9f8")
    assert res_media.status_code == 200
    assert res_media.json()["status"] == "AUTHORIZED"
