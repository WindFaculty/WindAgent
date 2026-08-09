"""
Golden Scene End-to-End Orchestration Domain (VP3D Phase 25, Stage M).

Pure domain models + fail-closed kernels for the 30-60 second golden scene
production run:

    Script -> IR -> Assets -> Scene -> Animation + Audio -> Facial
    -> Render -> Review/Repair -> FFmpeg -> Final MP4

Acceptance (stage_m.md §3):

1. no manual Blender edits — the orchestrator drives every node;
2. every input/output carries ID, revision, provenance and content hash;
3. cancel/restart at at least one node resumes WITHOUT duplication;
4. character/voice identity and continuity pass;
5. render frames, audio and the final MP4 pass technical verification;
6. a blocking-defect fixture is REJECTED — never a false PASS;
7. the production report states the repair count and every human approval.

The orchestrator walks the node DAG, records a receipt per node, persists a
checkpoint after every node, and derives the verdict fail-closed: any failed /
cancelled node, any blocking review finding, any identity/continuity failure
or any failed technical verification REJECTS the run.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    GoldenSceneNodeKind,
    GoldenSceneNodeStatus,
    GoldenSceneVerdict,
)
from windagent_core.domain.video_production.errors import (
    GoldenSceneBlockingDefectError,
    GoldenSceneResumeMismatchError,
    GoldenSceneValidationError,
)
from windagent_core.domain.video_production.ids import (
    GoldenSceneNodeId,
    GoldenSceneRunId,
    VideoProjectId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic canonical dict for hashing (json round-trip first)."""
    return json.loads(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    )


def compute_content_hash(payload: Dict[str, Any]) -> str:
    """SHA-256 of the canonical payload — determinism is a hard criterion."""
    canonical = json.dumps(
        _canonical_dict(payload), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Node DAG
# ---------------------------------------------------------------------------
GOLDEN_SCENE_DAG: List[GoldenSceneNodeKind] = [
    GoldenSceneNodeKind.SCRIPT,
    GoldenSceneNodeKind.IR,
    GoldenSceneNodeKind.ASSETS,
    GoldenSceneNodeKind.SCENE,
    GoldenSceneNodeKind.ANIMATION_AUDIO,
    GoldenSceneNodeKind.FACIAL,
    GoldenSceneNodeKind.RENDER,
    GoldenSceneNodeKind.REVIEW_REPAIR,
    GoldenSceneNodeKind.FFMPEG,
    GoldenSceneNodeKind.FINAL,
]


# ---------------------------------------------------------------------------
# Human approval / repair entries
# ---------------------------------------------------------------------------
class HumanApprovalEntry(BaseModel):
    """One explicit human approval recorded in the production report."""

    model_config = ConfigDict(frozen=True, extra="allow")

    approval_id: str
    node_kind: GoldenSceneNodeKind
    actor: str
    decision: str  # APPROVED | REJECTED | OVERRIDDEN
    reason: str = ""
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "approval_id": self.approval_id,
                "node_kind": self.node_kind.value,
                "actor": self.actor,
                "decision": self.decision,
                "reason": self.reason,
            }
        )


class RepairEntry(BaseModel):
    """One repair action taken by the Review/Repair node."""

    model_config = ConfigDict(frozen=True, extra="allow")

    repair_id: str
    node_kind: GoldenSceneNodeKind
    finding_code: str
    outcome: str  # REPAIRED | UNREPAIRABLE | SKIPPED_DUPLICATE
    attempt: int = 1

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "repair_id": self.repair_id,
                "node_kind": self.node_kind.value,
                "finding_code": self.finding_code,
                "outcome": self.outcome,
                "attempt": self.attempt,
            }
        )


# ---------------------------------------------------------------------------
# Fixture + run manifest
# ---------------------------------------------------------------------------
class GoldenSceneFixture(BaseModel):
    """The versioned production fixture (stage_m.md §2/§3).

    Two characters, one environment, dialogue, walk + interaction, moving
    camera, lighting, lip-sync, Cycles render profile, audio cues. The fixture
    is the pinned input set of the golden scene run — it never mutates.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    fixture_id: str
    title: str
    planned_duration_seconds: float = 30.0
    fps: int = 24
    screenplay_text: str = ""
    characters: List[Dict[str, Any]] = Field(default_factory=list)
    environment: Dict[str, Any] = Field(default_factory=dict)
    dialogue_lines: List[Dict[str, Any]] = Field(default_factory=list)
    animation_intents: List[Dict[str, Any]] = Field(default_factory=list)
    camera_intents: List[Dict[str, Any]] = Field(default_factory=list)
    lighting_intents: List[Dict[str, Any]] = Field(default_factory=list)
    audio_cues: List[Dict[str, Any]] = Field(default_factory=list)
    render_profile: Dict[str, Any] = Field(default_factory=dict)
    approvals: List[HumanApprovalEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "fixture_id": self.fixture_id,
                "title": self.title,
                "planned_duration_seconds": self.planned_duration_seconds,
                "fps": self.fps,
                "screenplay_text": self.screenplay_text,
                "characters": self.characters,
                "environment": self.environment,
                "dialogue_lines": self.dialogue_lines,
                "animation_intents": self.animation_intents,
                "camera_intents": self.camera_intents,
                "lighting_intents": self.lighting_intents,
                "audio_cues": self.audio_cues,
                "render_profile": self.render_profile,
                "approvals": [a.content_hash() for a in self.approvals],
            }
        )


class GoldenSceneRunManifest(BaseModel):
    """Run manifest — every golden scene run pins its full environment."""

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: GoldenSceneRunId
    project_id: VideoProjectId
    revision_id: str
    fixture_hash: str
    candidate_sha: str
    hardware_baseline: Dict[str, str] = Field(default_factory=dict)
    tool_versions: Dict[str, str] = Field(default_factory=dict)
    budgets: Dict[str, float] = Field(default_factory=dict)
    pinned_seeds: Dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "run_id": str(self.run_id),
                "project_id": str(self.project_id),
                "revision_id": self.revision_id,
                "fixture_hash": self.fixture_hash,
                "candidate_sha": self.candidate_sha,
                "hardware_baseline": self.hardware_baseline,
                "tool_versions": self.tool_versions,
                "budgets": self.budgets,
                "pinned_seeds": self.pinned_seeds,
            }
        )


# ---------------------------------------------------------------------------
# Node spec + receipt + checkpoint
# ---------------------------------------------------------------------------
class GoldenSceneNodeSpec(BaseModel):
    """One pipeline node: kind, DAG dependencies, input artifact references."""

    model_config = ConfigDict(frozen=True, extra="allow")

    node_id: GoldenSceneNodeId
    kind: GoldenSceneNodeKind
    depends_on: List[GoldenSceneNodeKind] = Field(default_factory=list)
    input_refs: List[str] = Field(default_factory=list)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "node_id": str(self.node_id),
                "kind": self.kind.value,
                "depends_on": [k.value for k in self.depends_on],
                "input_refs": self.input_refs,
            }
        )


class GoldenSceneNodeReceipt(BaseModel):
    """One node execution record: hashes in, hashes out, provenance."""

    model_config = ConfigDict(frozen=True, extra="allow")

    node_id: GoldenSceneNodeId
    kind: GoldenSceneNodeKind
    status: GoldenSceneNodeStatus
    attempt: int = 1
    started_at: str = ""
    finished_at: str = ""
    input_hashes: Dict[str, str] = Field(default_factory=dict)
    output_hashes: Dict[str, str] = Field(default_factory=dict)
    provenance: Dict[str, str] = Field(default_factory=dict)
    error: str = ""
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    repairs: List[RepairEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "node_id": str(self.node_id),
                "kind": self.kind.value,
                "status": self.status.value,
                "attempt": self.attempt,
                "input_hashes": self.input_hashes,
                "output_hashes": self.output_hashes,
                "provenance": self.provenance,
            }
        )

    def is_terminal_ok(self) -> bool:
        return self.status in (GoldenSceneNodeStatus.COMPLETED, GoldenSceneNodeStatus.SKIPPED)


class GoldenSceneCheckpoint(BaseModel):
    """Durable per-run checkpoint: node receipts + artifact index.

    Resume semantics (acceptance §3): a node whose receipt is COMPLETED with
    the SAME input hashes is SKIPPED on restart — its outputs are reused and
    the node is NEVER re-executed (no duplicate render / no duplicate side
    effects). A node that was CANCELLED or FAILED re-runs from scratch.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: GoldenSceneRunId
    receipts: List[GoldenSceneNodeReceipt] = Field(default_factory=list)
    artifact_index: Dict[str, str] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())

    def receipt_for(self, kind: GoldenSceneNodeKind) -> Optional[GoldenSceneNodeReceipt]:
        for receipt in self.receipts:
            if receipt.kind == kind:
                return receipt
        return None

    def receipt_by_id(self, node_id: GoldenSceneNodeId) -> Optional[GoldenSceneNodeReceipt]:
        for receipt in self.receipts:
            if receipt.node_id == node_id:
                return receipt
        return None

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "run_id": str(self.run_id),
                "receipts": [r.content_hash() for r in self.receipts],
                "artifact_index": self.artifact_index,
            }
        )


class GoldenSceneResumePlanner:
    """Decides RUN vs SKIP per node given a checkpoint (fail-closed resume).

    A node is SKIPPED only when the checkpoint holds a COMPLETED receipt for
    the same kind AND every current input hash equals the recorded one. Any
    mismatch (changed input, missing receipt, FAILED/CANCELLED status) forces
    a fresh RUN — the golden scene never silently reuses stale output.
    """

    def plan(
        self,
        checkpoint: Optional[GoldenSceneCheckpoint],
        current_input_hashes: Dict[GoldenSceneNodeKind, Dict[str, str]],
    ) -> Dict[GoldenSceneNodeKind, str]:
        decisions: Dict[GoldenSceneNodeKind, str] = {}
        for kind in GOLDEN_SCENE_DAG:
            if checkpoint is None:
                decisions[kind] = "RUN"
                continue
            receipt = checkpoint.receipt_for(kind)
            expected = current_input_hashes.get(kind, {})
            if (
                receipt is not None
                and receipt.status == GoldenSceneNodeStatus.COMPLETED
                and receipt.input_hashes == expected
            ):
                decisions[kind] = "SKIP"
            else:
                decisions[kind] = "RUN"
        return decisions

    def skip_reason(
        self, receipt: Optional[GoldenSceneNodeReceipt]
    ) -> str:
        if receipt is None:
            return "no checkpoint receipt"
        return (
            f"checkpoint {receipt.status.value} attempt={receipt.attempt}"
        )


# ---------------------------------------------------------------------------
# Identity / continuity + technical verification
# ---------------------------------------------------------------------------
class IdentityContinuityReceipt(BaseModel):
    """Character/voice identity + continuity gate (acceptance §4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    character_identity_ok: bool = False
    voice_identity_ok: bool = False
    continuity_ok: bool = False
    blocking_issues: List[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.character_identity_ok
            and self.voice_identity_ok
            and self.continuity_ok
            and not self.blocking_issues
        )

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "character_identity_ok": self.character_identity_ok,
                "voice_identity_ok": self.voice_identity_ok,
                "continuity_ok": self.continuity_ok,
                "blocking_issues": self.blocking_issues,
            }
        )


class TechnicalVerificationReceipt(BaseModel):
    """Render frames / audio / final MP4 technical checks (acceptance §5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    frames_ok: bool = False
    audio_ok: bool = False
    final_mp4_ok: bool = False
    checks: Dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.frames_ok and self.audio_ok and self.final_mp4_ok

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "frames_ok": self.frames_ok,
                "audio_ok": self.audio_ok,
                "final_mp4_ok": self.final_mp4_ok,
                "checks": self.checks,
            }
        )


# ---------------------------------------------------------------------------
# Production report + verdict policy
# ---------------------------------------------------------------------------
class GoldenSceneProductionReport(BaseModel):
    """Final production report (acceptance §7): verdict, repairs, approvals."""

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: GoldenSceneRunId
    verdict: GoldenSceneVerdict
    manifest_hash: str
    fixture_hash: str
    receipts: List[GoldenSceneNodeReceipt] = Field(default_factory=list)
    identity_continuity: IdentityContinuityReceipt = Field(
        default_factory=IdentityContinuityReceipt
    )
    technical_verification: TechnicalVerificationReceipt = Field(
        default_factory=TechnicalVerificationReceipt
    )
    repair_entries: List[RepairEntry] = Field(default_factory=list)
    human_approvals: List[HumanApprovalEntry] = Field(default_factory=list)
    summary: str = ""
    decided_at: str = Field(default_factory=lambda: utc_now().isoformat())

    @property
    def repair_count(self) -> int:
        return len(self.repair_entries)

    def content_hash(self) -> str:
        return compute_content_hash(
            {
                "run_id": str(self.run_id),
                "verdict": self.verdict.value,
                "manifest_hash": self.manifest_hash,
                "fixture_hash": self.fixture_hash,
                "receipts": [r.content_hash() for r in self.receipts],
                "identity_continuity": self.identity_continuity.content_hash(),
                "technical_verification": self.technical_verification.content_hash(),
                "repair_entries": [r.content_hash() for r in self.repair_entries],
                "human_approvals": [a.content_hash() for a in self.human_approvals],
            }
        )


class GoldenSceneVerdictPolicy:
    """Fail-closed verdict derivation — NEVER a false PASS (acceptance §6).

    REJECT when any of:
    - a node receipt is FAILED or CANCELLED (unfinished run);
    - the review/repair node reports a blocking finding that was not
      resolved by a repair;
    - identity/continuity did not pass;
    - technical verification did not pass;
    - the final node did not complete.
    """

    def decide(
        self,
        receipts: List[GoldenSceneNodeReceipt],
        identity_continuity: IdentityContinuityReceipt,
        technical_verification: TechnicalVerificationReceipt,
    ) -> GoldenSceneVerdict:
        by_kind = {r.kind: r for r in receipts}

        # Every node must have a terminal-ok receipt.
        for kind in GOLDEN_SCENE_DAG:
            receipt = by_kind.get(kind)
            if receipt is None:
                return GoldenSceneVerdict.REJECT
            if not receipt.is_terminal_ok():
                return GoldenSceneVerdict.REJECT

        # ANY blocking finding on ANY node that was not repaired -> REJECT.
        # A finding is considered repaired only when a repair entry on the
        # SAME receipt names its code with outcome REPAIRED.
        for receipt in receipts:
            repaired_codes = {
                r.finding_code for r in receipt.repairs if r.outcome == "REPAIRED"
            }
            for finding in receipt.findings:
                if finding.get("blocking") and finding.get("code") not in repaired_codes:
                    return GoldenSceneVerdict.REJECT

        if not identity_continuity.passed:
            return GoldenSceneVerdict.REJECT
        if not technical_verification.passed:
            return GoldenSceneVerdict.REJECT
        return GoldenSceneVerdict.PASS


__all__ = [
    "GoldenSceneNodeKind",
    "GoldenSceneNodeStatus",
    "GoldenSceneVerdict",
    "GOLDEN_SCENE_DAG",
    "GoldenSceneFixture",
    "GoldenSceneRunManifest",
    "GoldenSceneNodeSpec",
    "GoldenSceneNodeReceipt",
    "GoldenSceneCheckpoint",
    "GoldenSceneResumePlanner",
    "IdentityContinuityReceipt",
    "TechnicalVerificationReceipt",
    "RepairEntry",
    "HumanApprovalEntry",
    "GoldenSceneProductionReport",
    "GoldenSceneVerdictPolicy",
    "GoldenSceneBlockingDefectError",
    "GoldenSceneResumeMismatchError",
    "GoldenSceneValidationError",
    "compute_content_hash",
]
