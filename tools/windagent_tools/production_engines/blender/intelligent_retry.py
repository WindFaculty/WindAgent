"""VP3D Phase 23 - intelligent retry (plan Stage K §4).

Engine-neutral retry kernel at the Blender adapter boundary (no ``bpy``
import).  It consumes Phase 22 ``ReviewFinding`` objects (code, severity,
entity, frame_range, evidence, confidence, suggested_repair, causes) and
turns them into a smallest-possible, budget-bounded repair plan with typed
invalidation and an execution receipt:

```text
FailureClassifier    finding -> owner (asset/rig/scene/camera/lighting/body
                     animation/facial/render/post-production) + smallest
                     repair unit.  Below the confidence threshold the owner
                     stays AMBIGUOUS: uncertainty is kept, never auto-picked.
RepairPlanner        smallest repair unit + revised input revision + the FULL
                     rerun set (related checks + downstream checks), never
                     only the check that failed.  Locked artifacts block.
InvalidationPlanner  dependency graph -> invalidated artifacts; unrelated
                     approved shots stay approved (no over-invalidation).
RetryBudgetPolicy    failure-signature dedupe (same signature never repaired
                     twice), attempt/cost/time budget, repair-loop detection.
RepairExecutionReceipt  outcome: SUCCEEDED / FAILED / ESCALATED / BLOCKED /
                     SKIPPED_DUPLICATE with rerun results.
```

Escalation rules (Stage K §4 backlog item 6): ambiguous owner, repeated same
failure (loop), creative choice needed, or budget exhausted -> human.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

INTELLIGENT_RETRY_SCHEMA_VERSION = "intelligent-retry-1.0.0"

# ---------------------------------------------------------------------------
# Owners / repair units (Stage K §4 backlog items 1-2)
# ---------------------------------------------------------------------------
OWNER_ASSET = "asset"
OWNER_RIG = "rig"
OWNER_SCENE = "scene"
OWNER_CAMERA = "camera"
OWNER_LIGHTING = "lighting"
OWNER_BODY_ANIMATION = "body_animation"
OWNER_FACIAL = "facial"
OWNER_RENDER = "render"
OWNER_POST_PRODUCTION = "post_production"
OWNER_AMBIGUOUS = "ambiguous"
OWNERS = (
    OWNER_ASSET,
    OWNER_RIG,
    OWNER_SCENE,
    OWNER_CAMERA,
    OWNER_LIGHTING,
    OWNER_BODY_ANIMATION,
    OWNER_FACIAL,
    OWNER_RENDER,
    OWNER_POST_PRODUCTION,
    OWNER_AMBIGUOUS,
)

REPAIR_UNIT_ASSET_REVISION = "asset_revision"
REPAIR_UNIT_CAMERA_RECOMPILE = "camera_recompile"
REPAIR_UNIT_FACIAL_TRACK = "facial_track"
REPAIR_UNIT_AFFECTED_FRAMES = "affected_frames"
REPAIR_UNIT_AUDIO_MIX = "audio_mix"
REPAIR_UNIT_RIG_REPAIR = "rig_repair"
REPAIR_UNIT_LIGHTING_FIX = "lighting_fix"
REPAIR_UNIT_FRAME_RANGE = "frame_range_adjust"
REPAIR_UNIT_VRAM_MITIGATION = "vram_mitigation"
REPAIR_UNIT_ASSET_APPROVAL = "asset_approval"
REPAIR_UNIT_HUMAN_REVIEW = "human_review"
REPAIR_UNITS = (
    REPAIR_UNIT_ASSET_REVISION,
    REPAIR_UNIT_CAMERA_RECOMPILE,
    REPAIR_UNIT_FACIAL_TRACK,
    REPAIR_UNIT_AFFECTED_FRAMES,
    REPAIR_UNIT_AUDIO_MIX,
    REPAIR_UNIT_RIG_REPAIR,
    REPAIR_UNIT_LIGHTING_FIX,
    REPAIR_UNIT_FRAME_RANGE,
    REPAIR_UNIT_VRAM_MITIGATION,
    REPAIR_UNIT_ASSET_APPROVAL,
    REPAIR_UNIT_HUMAN_REVIEW,
)

# suggested_repair (Phase 22) -> (owner, smallest repair unit).
REPAIR_SCOPE_MAP = {
    "asset_revision": (OWNER_ASSET, REPAIR_UNIT_ASSET_REVISION),
    "camera_recompile": (OWNER_CAMERA, REPAIR_UNIT_CAMERA_RECOMPILE),
    "facial_only": (OWNER_FACIAL, REPAIR_UNIT_FACIAL_TRACK),
    "affected_frames": (OWNER_RENDER, REPAIR_UNIT_AFFECTED_FRAMES),
    "audio_mix": (OWNER_POST_PRODUCTION, REPAIR_UNIT_AUDIO_MIX),
    "rig_repair": (OWNER_RIG, REPAIR_UNIT_RIG_REPAIR),
    "lighting_fix": (OWNER_LIGHTING, REPAIR_UNIT_LIGHTING_FIX),
    "frame_range_adjust": (OWNER_SCENE, REPAIR_UNIT_FRAME_RANGE),
    "vram_mitigation": (OWNER_RENDER, REPAIR_UNIT_VRAM_MITIGATION),
    "asset_approval": (OWNER_ASSET, REPAIR_UNIT_ASSET_APPROVAL),
    "human_review": (OWNER_AMBIGUOUS, REPAIR_UNIT_HUMAN_REVIEW),
}

# Receipt statuses.
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_ESCALATED = "ESCALATED"
STATUS_BLOCKED = "BLOCKED"
STATUS_SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"

DEFAULT_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_COST = 10.0
DEFAULT_MAX_TIME_SECONDS = 3600.0

# Downstream checks that must rerun after ANY repair (integrity + temporal),
# beyond the check that originally failed (Stage K §4 backlog item 5).
DOWNSTREAM_CHECKS = (
    "FRAME_COUNT_MISMATCH",
    "FRAME_MISSING_RANGE",
    "FRAME_UNDECODABLE",
    "FRAME_DIMENSION_MISMATCH",
    "FRAME_BLACK_OR_CORRUPT",
    "FLICKER_DETECTED",
    "NOISE_BURST",
    "EXPOSURE_DISCONTINUITY",
)


def failure_signature(finding: Mapping[str, Any]) -> str:
    """Stable signature: code + entity + frame range + repair unit.

    Two events for the SAME defect (duplicate dispatch, restart after crash)
    hash identically, so a repair runs once (Stage K §4 item 4 / §5 matrix).
    """
    canonical = json.dumps(
        {
            "code": finding.get("code"),
            "entity": finding.get("entity"),
            "frame_range": finding.get("frame_range"),
            "repair": finding.get("suggested_repair"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# FailureClassifier (backlog item 1: finding -> owner + smallest unit)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RepairClassification:
    """Owner + smallest repair unit for one finding."""

    finding_code: str
    entity: str
    owner: str
    repair_unit: str
    confidence: float
    ambiguous: bool = False
    causes: Tuple[str, ...] = ()
    revised_input_key: str = ""
    revised_input_value: str = ""

    def to_dict(self) -> dict:
        return {
            "finding_code": self.finding_code,
            "entity": self.entity,
            "owner": self.owner,
            "repair_unit": self.repair_unit,
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
            "causes": list(self.causes),
            "revised_input_key": self.revised_input_key,
            "revised_input_value": self.revised_input_value,
        }


class FailureClassifier:
    """Maps a Phase 22 finding to an owner + smallest repair unit.

    Below ``confidence_threshold`` the owner stays AMBIGUOUS with the full
    candidate-cause list: uncertainty is kept, never auto-picked (Stage K §5:
    one defect, many possible causes -> no self-selected repair).
    """

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        self._threshold = confidence_threshold

    def classify(self, finding: Mapping[str, Any]) -> RepairClassification:
        scope = str(finding.get("suggested_repair") or "human_review")
        owner, unit = REPAIR_SCOPE_MAP.get(scope, (OWNER_AMBIGUOUS, REPAIR_UNIT_HUMAN_REVIEW))
        confidence = float(finding.get("confidence") or 0.0)
        causes = tuple(str(c) for c in (finding.get("causes") or ()))
        ambiguous = confidence < self._threshold or owner == OWNER_AMBIGUOUS
        if ambiguous:
            owner = OWNER_AMBIGUOUS
            unit = REPAIR_UNIT_HUMAN_REVIEW
        revised_key, revised_value = self._revised_input(owner, unit, finding)
        return RepairClassification(
            finding_code=str(finding.get("code") or ""),
            entity=str(finding.get("entity") or ""),
            owner=owner,
            repair_unit=unit,
            confidence=confidence,
            ambiguous=ambiguous,
            causes=causes,
            revised_input_key=revised_key,
            revised_input_value=revised_value,
        )

    @staticmethod
    def _revised_input(owner: str, unit: str, finding: Mapping[str, Any]) -> Tuple[str, str]:
        """The minimal input revision a repair rebuilds (backlog item 3)."""
        if unit == REPAIR_UNIT_FACIAL_TRACK:
            return "facial_track", f"{finding.get('entity') or 'facial'}:rev"
        if unit == REPAIR_UNIT_CAMERA_RECOMPILE:
            return "camera", f"{finding.get('entity') or 'camera'}:rev"
        if unit == REPAIR_UNIT_ASSET_REVISION:
            return "asset", f"{finding.get('entity') or 'asset'}:rev"
        if unit == REPAIR_UNIT_AUDIO_MIX:
            return "audio_mix", f"{finding.get('entity') or 'audio'}:rev"
        if unit == REPAIR_UNIT_LIGHTING_FIX:
            return "lighting", f"{finding.get('entity') or 'lighting'}:rev"
        if unit == REPAIR_UNIT_RIG_REPAIR:
            return "rig", f"{finding.get('entity') or 'rig'}:rev"
        if unit == REPAIR_UNIT_FRAME_RANGE:
            return "frame_range", f"{finding.get('entity') or 'scene'}:rev"
        if unit == REPAIR_UNIT_AFFECTED_FRAMES:
            return "render", f"{finding.get('entity') or 'render'}:rev"
        if unit == REPAIR_UNIT_VRAM_MITIGATION:
            return "render_profile", f"{finding.get('entity') or 'render'}:rev"
        return "", ""


# ---------------------------------------------------------------------------
# RepairPlanner (backlog item 2-3: smallest unit + full rerun set + locked guard)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RepairPlan:
    """Smallest repair unit + revised input + FULL rerun check set."""

    plan_id: str
    classification: RepairClassification
    revised_inputs: Mapping[str, str]
    rerun_checks: Tuple[str, ...]  # related + downstream, not just the failure
    locked_artifacts: Tuple[str, ...] = ()
    blocked: bool = False
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "classification": self.classification.to_dict(),
            "revised_inputs": dict(self.revised_inputs),
            "rerun_checks": list(self.rerun_checks),
            "locked_artifacts": list(self.locked_artifacts),
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


class RepairPlanner:
    """Builds the smallest repair plan; locked artifacts block (item 3)."""

    # Checks related to each owner (rerun beyond the failed check itself).
    OWNER_RELATED_CHECKS = {
        OWNER_FACIAL: ("LIP_SYNC_MISMATCH", "IDENTITY_DRIFT"),
        OWNER_CAMERA: (
            "CAMERA_CHARACTER_COLLISION",
            "CAMERA_NON_COMPLIANT",
            "OCCLUSION_ANOMALY",
        ),
        OWNER_ASSET: ("MISSING_TEXTURE", "MISSING_OBJECT", "IDENTITY_DRIFT"),
        OWNER_RIG: ("BROKEN_RIG", "MOTION_QUALITY_DEGRADED"),
        OWNER_LIGHTING: ("LIGHTING_INVALID", "LIGHTING_DRIFT", "EXPOSURE_DISCONTINUITY"),
        OWNER_POST_PRODUCTION: ("AUDIO_TIMING", "NOISE_BURST"),
        OWNER_SCENE: ("FRAME_RANGE_INVALID", "CONTINUITY_BREAK"),
        OWNER_RENDER: ("VRAM_BUDGET_EXCEEDED", "MOTION_QUALITY_DEGRADED"),
    }

    def plan(
        self,
        classification: RepairClassification,
        *,
        finding: Mapping[str, Any],
        locked_artifacts: Sequence[str] = (),
    ) -> RepairPlan:
        plan_id = "rp_" + failure_signature(finding)[:12]
        revised = (
            {classification.revised_input_key: classification.revised_input_value}
            if classification.revised_input_key
            else {}
        )
        related = tuple(
            self.OWNER_RELATED_CHECKS.get(classification.owner, ())
        )
        own = (str(finding.get("code") or ""),) if finding.get("code") else ()
        rerun = tuple(dict.fromkeys(own + related + DOWNSTREAM_CHECKS))
        locked = tuple(str(a) for a in locked_artifacts)
        if classification.owner == OWNER_AMBIGUOUS:
            return RepairPlan(
                plan_id=plan_id,
                classification=classification,
                revised_inputs=revised,
                rerun_checks=rerun,
                locked_artifacts=locked,
                blocked=True,
                block_reason="ambiguous owner: human review required, no auto-repair",
            )
        return RepairPlan(
            plan_id=plan_id,
            classification=classification,
            revised_inputs=revised,
            rerun_checks=rerun,
            locked_artifacts=locked,
            blocked=bool(locked),
            block_reason="repair touches locked artifact(s)" if locked else "",
        )


# ---------------------------------------------------------------------------
# InvalidationPlanner (backlog item 3 + §5: never invalidate unrelated shots)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InvalidationReceipt:
    """Which artifacts a repair invalidates (dependency-scoped)."""

    invalidated_artifacts: Tuple[str, ...]
    preserved_artifacts: Tuple[str, ...]
    dependency_graph: Mapping[str, Tuple[str, ...]]

    def to_dict(self) -> dict:
        return {
            "invalidated_artifacts": list(self.invalidated_artifacts),
            "preserved_artifacts": list(self.preserved_artifacts),
            "dependency_graph": {
                k: list(v) for k, v in self.dependency_graph.items()
            },
        }


class InvalidationPlanner:
    """Invalidates ONLY artifacts that depend on the repaired input.

    ``dependency_graph`` maps artifact_id -> input keys it derives from
    (camera / asset / animation / facial / render profile / audio).  A shot
    that does not depend on the repaired input stays APPROVED (Stage K §5).
    """

    def invalidate(
        self,
        *,
        revised_inputs: Mapping[str, str],
        dependency_graph: Mapping[str, Sequence[str]],
    ) -> InvalidationReceipt:
        invalidated = [
            artifact
            for artifact, deps in dependency_graph.items()
            if any(dep in revised_inputs for dep in deps)
        ]
        preserved = [
            artifact
            for artifact, deps in dependency_graph.items()
            if not any(dep in revised_inputs for dep in deps)
        ]
        return InvalidationReceipt(
            invalidated_artifacts=tuple(sorted(invalidated)),
            preserved_artifacts=tuple(sorted(preserved)),
            dependency_graph={
                k: tuple(v) for k, v in dependency_graph.items()
            },
        )


# ---------------------------------------------------------------------------
# RetryBudgetPolicy (backlog item 4: dedupe + attempt/cost/time + loop detect)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BudgetDecision:
    """Whether a repair may run, and why not."""

    allowed: bool
    reason: str = ""
    attempts: int = 0
    total_cost: float = 0.0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "attempts": self.attempts,
            "total_cost": self.total_cost,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


class RetryBudgetPolicy:
    """Signature dedupe + bounded attempts/cost/time + repair-loop detection.

    A signature that already ran and FAILED escalates to human on the Nth
    repeat instead of looping forever (Stage K §5: retry loop -> human).
    """

    def __init__(
        self,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_cost: float = DEFAULT_MAX_COST,
        max_time_seconds: float = DEFAULT_MAX_TIME_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.max_cost = max_cost
        self.max_time_seconds = max_time_seconds
        self._attempts: Dict[str, int] = {}
        self._cost: Dict[str, float] = {}
        self._first_seen: Dict[str, float] = {}

    def register(self, signature: str, cost: float) -> None:
        self._attempts[signature] = self._attempts.get(signature, 0) + 1
        self._cost[signature] = self._cost.get(signature, 0.0) + cost
        self._first_seen.setdefault(signature, time.monotonic())

    def allow(self, signature: str, cost: float = 1.0) -> BudgetDecision:
        attempts = self._attempts.get(signature, 0)
        total_cost = self._cost.get(signature, 0.0) + cost
        elapsed = (
            time.monotonic() - self._first_seen[signature]
            if signature in self._first_seen
            else 0.0
        )
        if attempts >= self.max_attempts:
            return BudgetDecision(
                False,
                f"repair loop detected: {attempts} attempts for signature {signature[:12]}",
                attempts,
                total_cost,
                elapsed,
            )
        if total_cost > self.max_cost:
            return BudgetDecision(
                False, f"cost budget exhausted: {total_cost:.1f} > {self.max_cost}",
                attempts, total_cost, elapsed,
            )
        if elapsed > self.max_time_seconds:
            return BudgetDecision(
                False,
                f"time budget exhausted: {elapsed:.1f}s > {self.max_time_seconds}s",
                attempts, total_cost, elapsed,
            )
        return BudgetDecision(True, "", attempts, total_cost, elapsed)

    def attempts(self, signature: str) -> int:
        return self._attempts.get(signature, 0)


# ---------------------------------------------------------------------------
# RepairExecutionReceipt (backlog item 5-6)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RepairExecutionReceipt:
    """Outcome of one repair execution."""

    repair_id: str
    signature: str
    status: str
    classification: RepairClassification
    plan: RepairPlan
    invalidation: InvalidationReceipt
    rerun_results: Mapping[str, bool] = field(default_factory=dict)
    attempts: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "repair_id": self.repair_id,
            "signature": self.signature,
            "status": self.status,
            "classification": self.classification.to_dict(),
            "plan": self.plan.to_dict(),
            "invalidation": self.invalidation.to_dict(),
            "rerun_results": dict(self.rerun_results),
            "attempts": self.attempts,
            "reason": self.reason,
        }


class IntelligentRetryCoordinator:
    """Orchestrates classify -> plan -> invalidate -> budget -> execute.

    ``repair_executor`` is an injected callable(plan) -> bool (True when the
    repair actually fixed the input); ``check_runner`` is a callable(checks)
    -> {check_code: passed}.  Both are deterministic in tests; the coordinator
    only decides.  A VLM/reviewer timeout surfaces from Phase 22 as a
    low-confidence finding, which classifies AMBIGUOUS and escalates here -
    it can never become a PASS (Stage K §5).
    """

    def __init__(
        self,
        *,
        classifier: Optional[FailureClassifier] = None,
        planner: Optional[RepairPlanner] = None,
        invalidation: Optional[InvalidationPlanner] = None,
        budget: Optional[RetryBudgetPolicy] = None,
    ) -> None:
        self._classifier = classifier or FailureClassifier()
        self._planner = planner or RepairPlanner()
        self._invalidation = invalidation or InvalidationPlanner()
        self._budget = budget or RetryBudgetPolicy()
        self._in_flight: set[str] = set()
        self._succeeded: set[str] = set()

    def execute(
        self,
        finding: Mapping[str, Any],
        *,
        dependency_graph: Mapping[str, Sequence[str]],
        locked_artifacts: Sequence[str] = (),
        repair_executor: Callable[[RepairPlan], bool],
        check_runner: Callable[[Sequence[str]], Mapping[str, bool]],
        repair_cost: float = 1.0,
    ) -> RepairExecutionReceipt:
        signature = failure_signature(finding)
        classification = self._classifier.classify(finding)

        # Ambiguous / low confidence -> human, no auto-pick (item 6).
        if classification.ambiguous:
            plan = self._planner.plan(classification, finding=finding)
            invalidation = self._invalidation.invalidate(
                revised_inputs={}, dependency_graph=dependency_graph
            )
            return RepairExecutionReceipt(
                repair_id=f"rr_{signature[:12]}",
                signature=signature,
                status=STATUS_ESCALATED,
                classification=classification,
                plan=plan,
                invalidation=invalidation,
                attempts=self._budget.attempts(signature),
                reason="low confidence / ambiguous owner: human review required",
            )

        # Dedupe (item 4 / §5): duplicate event or restart while a repair for
        # the SAME failure signature is in flight, or a replay of a signature
        # that already SUCCEEDED, never runs the repair a second time.
        if signature in self._in_flight or signature in self._succeeded:
            plan = self._planner.plan(classification, finding=finding)
            invalidation = self._invalidation.invalidate(
                revised_inputs={}, dependency_graph=dependency_graph
            )
            return RepairExecutionReceipt(
                repair_id=f"rr_{signature[:12]}",
                signature=signature,
                status=STATUS_SKIPPED_DUPLICATE,
                classification=classification,
                plan=plan,
                invalidation=invalidation,
                attempts=self._budget.attempts(signature),
                reason=(
                    "duplicate event: repair already in flight"
                    if signature in self._in_flight
                    else "duplicate event: signature already repaired successfully"
                ),
            )

        plan = self._planner.plan(
            classification, finding=finding, locked_artifacts=locked_artifacts
        )
        if plan.blocked:
            invalidation = self._invalidation.invalidate(
                revised_inputs={}, dependency_graph=dependency_graph
            )
            return RepairExecutionReceipt(
                repair_id=f"rr_{signature[:12]}",
                signature=signature,
                status=STATUS_BLOCKED,
                classification=classification,
                plan=plan,
                invalidation=invalidation,
                attempts=self._budget.attempts(signature),
                reason=plan.block_reason,
            )

        # Budget + dedupe: same signature twice (duplicate event/restart)
        # runs ONCE; exhausted budgets escalate/block (item 4).
        decision = self._budget.allow(signature, cost=repair_cost)
        if not decision.allowed:
            invalidation = self._invalidation.invalidate(
                revised_inputs={}, dependency_graph=dependency_graph
            )
            status = STATUS_ESCALATED if "loop" in decision.reason else STATUS_BLOCKED
            return RepairExecutionReceipt(
                repair_id=f"rr_{signature[:12]}",
                signature=signature,
                status=status,
                classification=classification,
                plan=plan,
                invalidation=invalidation,
                attempts=decision.attempts,
                reason=decision.reason,
            )

        invalidation = self._invalidation.invalidate(
            revised_inputs=plan.revised_inputs,
            dependency_graph=dependency_graph,
        )

        # Execute + rerun the FULL related + downstream set, not just the
        # failed check (item 5).  The signature is reserved in-flight so a
        # concurrent duplicate event is skipped, then released.
        self._budget.register(signature, cost=repair_cost)
        self._in_flight.add(signature)
        try:
            fixed = repair_executor(plan)
            rerun_results = dict(check_runner(plan.rerun_checks))
        finally:
            self._in_flight.discard(signature)
        all_passed = bool(rerun_results) and all(rerun_results.values())
        status = STATUS_SUCCEEDED if (fixed and all_passed) else STATUS_FAILED
        if status == STATUS_SUCCEEDED:
            self._succeeded.add(signature)
        return RepairExecutionReceipt(
            repair_id=f"rr_{signature[:12]}",
            signature=signature,
            status=status,
            classification=classification,
            plan=plan,
            invalidation=invalidation,
            rerun_results=rerun_results,
            attempts=self._budget.attempts(signature),
            reason="" if status == STATUS_SUCCEEDED else (
                "repair did not fix input" if not fixed
                else "rerun checks still failing"
            ),
        )


__all__ = [
    "INTELLIGENT_RETRY_SCHEMA_VERSION",
    "OWNER_ASSET",
    "OWNER_RIG",
    "OWNER_SCENE",
    "OWNER_CAMERA",
    "OWNER_LIGHTING",
    "OWNER_BODY_ANIMATION",
    "OWNER_FACIAL",
    "OWNER_RENDER",
    "OWNER_POST_PRODUCTION",
    "OWNER_AMBIGUOUS",
    "OWNERS",
    "REPAIR_UNIT_ASSET_REVISION",
    "REPAIR_UNIT_CAMERA_RECOMPILE",
    "REPAIR_UNIT_FACIAL_TRACK",
    "REPAIR_UNIT_AFFECTED_FRAMES",
    "REPAIR_UNIT_AUDIO_MIX",
    "REPAIR_UNIT_RIG_REPAIR",
    "REPAIR_UNIT_LIGHTING_FIX",
    "REPAIR_UNIT_FRAME_RANGE",
    "REPAIR_UNIT_VRAM_MITIGATION",
    "REPAIR_UNIT_ASSET_APPROVAL",
    "REPAIR_UNIT_HUMAN_REVIEW",
    "REPAIR_UNITS",
    "REPAIR_SCOPE_MAP",
    "STATUS_SUCCEEDED",
    "STATUS_FAILED",
    "STATUS_ESCALATED",
    "STATUS_BLOCKED",
    "STATUS_SKIPPED_DUPLICATE",
    "DOWNSTREAM_CHECKS",
    "failure_signature",
    "RepairClassification",
    "FailureClassifier",
    "RepairPlan",
    "RepairPlanner",
    "InvalidationReceipt",
    "InvalidationPlanner",
    "BudgetDecision",
    "RetryBudgetPolicy",
    "RepairExecutionReceipt",
    "IntelligentRetryCoordinator",
]
