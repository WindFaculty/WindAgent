"""
Production Workspace Domain Models & DTOs (Phase 23 — plan 06 §16-§20).

Defines models for Workspace Snapshot, Workspace Commands, Event Projections,
Candidate Reviews, Cost Summaries, and Human Takeover States.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from windagent_core.domain.video_production.ids import (
    GenerationCandidateId,
    ProductionRevisionId,
    ShotId,
    VideoProjectId,
)


class WorkspaceCommandType(str, Enum):
    """Mutating command types supported by API V2 workspace router."""

    UPDATE_SCENE = "UPDATE_SCENE"
    ADD_SHOT = "ADD_SHOT"
    UPDATE_ASSET = "UPDATE_ASSET"
    APPROVE_CANDIDATE = "APPROVE_CANDIDATE"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"
    OVERRIDE_CANDIDATE = "OVERRIDE_CANDIDATE"
    AUTHORIZE_COST = "AUTHORIZE_COST"
    HUMAN_TAKEOVER = "HUMAN_TAKEOVER"
    CANCEL_JOB = "CANCEL_JOB"
    PUBLISH_DELIVERABLE = "PUBLISH_DELIVERABLE"

    # Stage D Universal Asset Commands (UI23)
    IMPORT_ASSET = "IMPORT_ASSET"
    UPLOAD_ASSET = "UPLOAD_ASSET"
    DISCOVER_ASSET = "DISCOVER_ASSET"
    DOWNLOAD_ASSET = "DOWNLOAD_ASSET"
    REQUEST_ASSET_GENERATION = "REQUEST_ASSET_GENERATION"
    NORMALIZE_ASSET = "NORMALIZE_ASSET"
    VALIDATE_ASSET = "VALIDATE_ASSET"
    APPROVE_ASSET = "APPROVE_ASSET"
    REJECT_ASSET = "REJECT_ASSET"
    UPDATE_LICENSE = "UPDATE_LICENSE"
    CREATE_ASSET_REVISION = "CREATE_ASSET_REVISION"
    BIND_ASSET = "BIND_ASSET"
    UNBIND_ASSET = "UNBIND_ASSET"
    ARCHIVE_ASSET = "ARCHIVE_ASSET"



class WorkspaceCommandStatus(str, Enum):
    """Execution outcome of a workspace mutating command."""

    COMPLETED = "COMPLETED"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_LOCKED = "REJECTED_LOCKED"
    IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
    FAILED = "FAILED"


def compute_payload_hash(data: dict[str, Any]) -> str:
    """Canonical SHA-256 hash of command payload for idempotency mismatch checks."""
    canonical_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateReviewOverride:
    """Explicit human override record for a candidate rating."""

    candidate_id: GenerationCandidateId
    shot_id: ShotId
    previous_verdict: str
    new_verdict: str
    reason: str
    override_by: str = "human_operator"


@dataclass(frozen=True)
class CostApprovalSummary:
    """Cost ledger & budget safety summary."""

    project_id: VideoProjectId
    estimated_credits: float
    max_approved_credits: float
    reserved_credits: float
    debited_credits: float
    remaining_credits: float

    @property
    def can_proceed(self) -> bool:
        return self.debited_credits + self.reserved_credits <= self.max_approved_credits


@dataclass(frozen=True)
class HumanTakeoverPanelState:
    """Human takeover panel instructions and state."""

    action_id: str
    state_kind: str
    prompt_text: str
    session_id: str
    created_at: str
    is_active: bool = True


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """Consolidated state snapshot of the production workspace."""

    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    project_status: str
    revision_status: str
    creative_brief_locked: bool
    screenplay_locked: bool
    total_shots: int
    candidates_count: int
    cost_summary: CostApprovalSummary
    human_takeover_state: HumanTakeoverPanelState | None
    current_sequence: int
    authorized_media_urls: dict[str, str] = field(default_factory=dict)
    screenplay: dict[str, Any] = field(default_factory=dict)
    asset_summary: dict[str, Any] = field(default_factory=dict)
    pipeline_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceCommandRequest:
    """Mutating command request sent to API V2."""

    command_id: str
    command_type: WorkspaceCommandType
    project_id: VideoProjectId
    target_revision_id: ProductionRevisionId
    entity_id: str
    reason: str
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    client_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceCommandResult:
    """Response returned by API V2 for mutating command."""

    command_id: str
    status: WorkspaceCommandStatus
    updated_revision_id: ProductionRevisionId
    message: str
    current_sequence: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

