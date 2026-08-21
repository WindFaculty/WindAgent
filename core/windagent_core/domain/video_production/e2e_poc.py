"""
Controlled E2E Video Production PoC Domain Models (Phase 24 — plan 06 §21-§30).

Defines deterministic models for PoC Run Manifests, Traceability Graphs, Browser
Recovery Receipts, Automation Rate Metrics, Cost Reports, and Hardening Handoffs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)


@dataclass(frozen=True)
class PocRunManifest:
    """Freeze run manifest for controlled E2E PoC execution."""

    run_id: str
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    release_scope: str = "Release 0.1"
    planned_scenes: int = 2
    planned_shots: int = 6
    planned_duration_seconds: float = 35.0
    candidate_sha: str = "git_sha_v2_poc_release_0_1"
    tool_versions: dict[str, str] = field(
        default_factory=lambda: {"ffmpeg": "6.1.1", "python": "3.11"}
    )
    created_at: str = "2026-08-02T13:35:00Z"


@dataclass(frozen=True)
class InputRevisionManifest:
    """Frozen input manifest containing content hashes before PoC run."""

    run_id: str
    screenplay_hash: str
    brief_hash: str
    character_bible_hashes: tuple[str, ...]
    location_bible_hashes: tuple[str, ...]
    cinematic_plan_hash: str


@dataclass(frozen=True)
class WorkflowEventReceipt:
    """Step execution receipt for the 14-step E2E runbook."""

    receipt_id: str
    run_id: str
    step_number: int
    step_name: str
    status: str
    timestamp: str
    details: str = ""


@dataclass(frozen=True)
class BrowserRecoveryReceipt:
    """Audit receipt for mandatory browser session recovery test."""

    receipt_id: str
    run_id: str
    session_id: str
    job_id: str
    disconnect_simulated: bool
    pause_verified: bool
    reattach_verified: bool
    job_reconciled: bool
    duplicate_submits_count: int

    @property
    def is_passed(self) -> bool:
        return (
            self.disconnect_simulated
            and self.pause_verified
            and self.reattach_verified
            and self.job_reconciled
            and self.duplicate_submits_count == 0
        )


@dataclass(frozen=True)
class CandidateReviewReport:
    """Comprehensive candidate evaluation and override audit report."""

    run_id: str
    candidates_reviewed: int
    approved_shots_count: int
    identity_defects_count: int
    human_overrides_count: int
    is_acceptable: bool


@dataclass(frozen=True)
class TraceabilityNode:
    """Single artifact node in the Traceability DAG."""

    node_id: str
    artifact_type: str
    content_hash: str
    parent_node_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TraceabilityGraph:
    """Full-chain DAG linking final deliverable back to package revision."""

    graph_id: str
    run_id: str
    deliverable_hash: str
    nodes: tuple[TraceabilityNode, ...]

    @property
    def is_complete(self) -> bool:
        return len(self.nodes) >= 6 and all(len(n.content_hash) > 0 for n in self.nodes)


@dataclass(frozen=True)
class AutomationRateMetric:
    """Automation rate calculation for acceptance gate."""

    total_planned_shots: int
    manual_media_edits_count: int

    @property
    def automation_rate(self) -> float:
        if self.total_planned_shots <= 0:
            return 0.0
        auto_shots = max(0, self.total_planned_shots - self.manual_media_edits_count)
        return auto_shots / self.total_planned_shots

    @property
    def satisfies_threshold(self) -> bool:
        return self.automation_rate >= 0.80


@dataclass(frozen=True)
class CostReport:
    """Cost audit and credit ledger reconciliation report."""

    run_id: str
    max_approved_credits: float
    estimated_credits: float
    debited_credits: float
    remaining_credits: float
    ledger_reconciled: bool

    @property
    def satisfies_budget(self) -> bool:
        return self.debited_credits <= self.max_approved_credits and self.ledger_reconciled


@dataclass(frozen=True)
class HardeningHandoff:
    """Handoff summary package for Phase 25-27 Hardening."""

    run_id: str
    candidate_sha: str
    verdict_status: str
    automation_rate: float
    debited_credits: float
    defect_inventory: tuple[str, ...]
    known_limitations: tuple[str, ...]
