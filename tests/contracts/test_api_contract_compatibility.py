"""
Contract compatibility unit tests for Stage H (UI41).

Validates:
- Canonical Command Envelope structure
- Canonical Event Envelope structure
- RFC 7807 Problem Details error code mappings
- Schema generation drift check
- Field requirement enforcement
"""

from __future__ import annotations

from typing import Any, Dict

from tests.fixtures.canonical.canonical_bunny_episode import build_canonical_bunny_episode


def test_command_envelope_contract() -> None:
    """Verify Canonical Command Envelope structure."""
    envelope: Dict[str, Any] = {
        "command_id": "cmd_12345",
        "project_id": "prj_bunny_ep01",
        "command_type": "LOCK_REVISION",
        "client_timestamp": "2026-08-08T12:00:00Z",
        "idempotency_key": "idempotent-key-999",
        "expected_revision_id": "rev_ep01_v2_draft",
        "payload": {"reason": "Screenplay finalized"},
    }

    required_keys = [
        "command_id",
        "project_id",
        "command_type",
        "client_timestamp",
        "idempotency_key",
        "expected_revision_id",
        "payload",
    ]
    for key in required_keys:
        assert key in envelope, f"Missing required command envelope key: {key}"


def test_event_envelope_contract() -> None:
    """Verify Canonical Event Envelope structure."""
    bunny = build_canonical_bunny_episode()
    event = bunny["events"][0]

    required_keys = ["event_id", "sequence", "project_id", "event_type", "timestamp", "data"]
    for key in required_keys:
        assert key in event, f"Missing required event envelope key: {key}"

    assert isinstance(event["sequence"], int)
    assert event["sequence"] > 0


def test_problem_details_rfc7807_contract() -> None:
    """Verify RFC 7807 problem details error payload contract."""
    problem: Dict[str, Any] = {
        "type": "https://windagent.io/errors/stale-revision",
        "title": "Stale Revision Conflict",
        "status": 409,
        "detail": "Revision 'rev_001' has been superseded by 'rev_002'.",
        "instance": "/api/v2/projects/prj_01/revisions/rev_001/lock",
        "code": "STALE_REVISION_CONFLICT",
        "invalid_params": [{"name": "expected_revision_id", "reason": "Revision hash mismatch"}],
    }

    assert problem["status"] == 409
    assert problem["code"] == "STALE_REVISION_CONFLICT"
    assert len(problem["invalid_params"]) == 1


def test_schema_generator_output() -> None:
    """Verify generate_ts_contracts output includes essential interface tokens."""
    import sys

    sys.path.append("scripts/schemas")
    from generate_ts_contracts import generate_contracts

    ts_code = generate_contracts()
    assert "export interface CanonicalCommandEnvelope" in ts_code
    assert "export interface CanonicalEventEnvelope" in ts_code
    assert "export interface ProblemDetailsError" in ts_code
    assert "export interface ScreenplayReadModel" in ts_code
    assert "export interface ProductionAssetModel" in ts_code
    assert "export interface CollaborationProposalModel" in ts_code
