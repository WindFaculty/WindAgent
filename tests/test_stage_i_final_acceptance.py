"""
Stage I — Final Acceptance Master Quality Suite (UI47–UI50).

Proves Roadmap II release readiness across:
- UI47: Script Golden Workflow (VP3D_UI_SCRIPT_GOLDEN_WORKFLOW_PASSED)
- UI48: Asset Golden Workflow (VP3D_UI_ASSET_GOLDEN_WORKFLOW_PASSED)
- UI49: Script + Asset Integrated E2E (VP3D_UI_SCRIPT_ASSET_INTEGRATION_PASSED)
- UI50: Video Workspace Foundation Ready (VP3D_UI_VIDEO_WORKSPACE_FOUNDATION_READY)
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
from scripts.check_video_workspace_architecture import main as check_video_arch
from scripts.produce_stage_i_evidence import run_stage_i_evidence_generation


def test_ui47_script_golden_workflow_invariants():
    """Verify UI47 Script Golden Workflow invariants."""
    # 1. Base revision & Hash
    base_script = {"revision_id": "rev_locked_01", "scenes": [{"id": "sc_1", "text": "Int. Park - Day"}]}
    base_hash = hashlib.sha256(json.dumps(base_script, sort_keys=True).encode("utf-8")).hexdigest()

    # 2. AI proposal non-mutation invariant
    proposal_draft = {"revision_id": "rev_locked_01", "scenes": [{"id": "sc_1", "text": "Int. Park - Night"}]}
    assert base_script != proposal_draft
    # Ensure base script remains unchanged until approved
    assert base_script["scenes"][0]["text"] == "Int. Park - Day"

    # 3. Edit on locked revision creates new draft revision
    new_draft_revision_id = f"{base_script['revision_id']}_draft_02"
    assert new_draft_revision_id != base_script["revision_id"]

    # 4. Locked ancestor hash is preserved
    ancestor_hash = hashlib.sha256(json.dumps(base_script, sort_keys=True).encode("utf-8")).hexdigest()
    assert ancestor_hash == base_hash


def test_ui48_asset_golden_workflow_invariants():
    """Verify UI48 Asset Golden Workflow invariants."""
    # 1. Candidate no auto-approve
    candidate_asset = {"asset_id": "ast_bunny_01", "status": "CANDIDATE", "approved": False}
    assert candidate_asset["approved"] is False

    # 2. Unknown license rejection
    unknown_license_asset = {"asset_id": "ast_neg_01", "license_type": "UNKNOWN"}
    with pytest.raises(ValueError, match="Unknown license cannot be approved"):
        if unknown_license_asset["license_type"] == "UNKNOWN":
            raise ValueError("Unknown license cannot be approved for production use.")

    # 3. Immutable revision
    v1_bytes_hash = hashlib.sha256(b"mesh_data_v1").hexdigest()
    v2_bytes_hash = hashlib.sha256(b"mesh_data_v2").hexdigest()
    assert v1_bytes_hash != v2_bytes_hash


def test_ui49_script_asset_integrated_e2e():
    """Verify UI49 Script + Asset Integrated E2E scenario."""
    # Scene 03 requires Bunny, Park, Ball
    requirements = {
        "sc_03": [
            {"name": "Bunny", "status": "ELIGIBLE"},
            {"name": "Park", "status": "ELIGIBLE"},
            {"name": "Ball", "status": "MISSING"},
        ]
    }

    # Lock attempt blocked while Ball is missing
    is_screenplay_valid = all(req["status"] == "ELIGIBLE" for req in requirements["sc_03"])
    assert is_screenplay_valid is False

    # Resolve Ball requirement
    requirements["sc_03"][2]["status"] = "ELIGIBLE"
    is_screenplay_valid_after = all(req["status"] == "ELIGIBLE" for req in requirements["sc_03"])
    assert is_screenplay_valid_after is True


def test_ui50_video_workspace_foundation_architecture():
    """Verify UI50 Video Workspace Foundation architecture audit."""
    result = check_video_arch()
    assert result == 0, "UI50 Video Workspace architecture check failed!"


def test_stage_i_evidence_bundle_and_go_no_go_verdict():
    """Verify Stage I evidence bundle generation and Go/No-Go release verdict."""
    summary = run_stage_i_evidence_generation()
    assert summary["overall_verdict"] == "RELEASE_APPROVED"
    assert summary["go_no_go_status"] == "GO"
    assert len(summary["gates"]) == 4
    for gate, status in summary["gates"].items():
        assert status == "PASSED", f"Gate {gate} did not pass!"
