"""
Cross-shot / reference continuity review (plan 05 Phase 20 §25.3,
gate VP20_GENERATION_REVIEW_VERIFIED).

The THIRD tier of the reviewer hierarchy (§24): compares a candidate against
its predecessor/successor using the Phase 10 continuity ledger — screen
direction, wardrobe, prop, lighting and location, plus the required
tail/head frame relation.

Rules:

- cross-shot review reads the CONTINUITY LEDGER (gate condition 5: cross-shot
  review dùng continuity ledger) — it never guesses continuity from the
  candidate alone;
- a blocking continuity defect carries a typed reason code (§25.3);
- predecessor/outgoing vs successor/incoming field mismatches are surfaced
  as blocking defects with evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from windagent_core.domain.video_production.continuity import ContinuityLedger
from windagent_core.domain.video_production.enums import ContinuityIssueCode

from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
from windagent_intelligence.video.reviewers.models import (
    BlockingDefect,
    BlockingReasonCode,
    DimensionResult,
    ReviewDimension,
    ReviewerType,
)

CROSS_SHOT_METRIC_VERSION = "1.0.0"

# Fields whose predecessor.outgoing -> successor.incoming must be consistent.
# NOTE: the Phase 10 ledger state carries camera_side (identity/appearance/
# prop/reference fields); screen_direction lives on the shot SPECIFICATION,
# not in ledger state, so only camera_side is comparable here.
_CONSISTENCY_FIELDS = ("camera_side",)


@dataclass(frozen=True)
class CrossShotReviewResult:
    """Cross-shot continuity outcome for one candidate (§25.3)."""

    candidate_id: str
    dimension_results: Tuple[DimensionResult, ...]
    blocking_defects: Tuple[BlockingDefect, ...]
    continuity_valid: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "dimension_results": [d.to_dict() for d in self.dimension_results],
            "blocking_defects": [b.to_dict() for b in self.blocking_defects],
            "continuity_valid": self.continuity_valid,
        }


class CrossShotReviewer:
    """Compares a candidate to the continuity ledger (plan §25.3)."""

    def __init__(self) -> None:
        self.metric_version = CROSS_SHOT_METRIC_VERSION

    def review(
        self,
        candidate_id: str,
        ledger_receipt: ContinuityLedgerReceipt,
    ) -> CrossShotReviewResult:
        defects: List[BlockingDefect] = []
        evidence: List[str] = []

        ledger: ContinuityLedger = ledger_receipt.ledger

        # 1. Surface every blocking continuity issue from the ledger as a
        #    typed blocking defect (§25.3, gate condition 2: blocking defects
        #    have automated cases).
        for issue in ledger_receipt.blocking_issues:
            code = _map_continuity_code(issue.code)
            defects.append(
                BlockingDefect(
                    code=code,
                    dimension=ReviewDimension.CONTINUITY,
                    message=issue.message,
                    reviewer_type=ReviewerType.CROSS_SHOT,
                    shot_id=str(issue.shot_id) if issue.shot_id else None,
                    evidence=(issue.code.value,),
                )
            )
            evidence.append(f"ledger_issue:{issue.code.value}")

        # 2. Predecessor.outgoing -> successor.incoming consistency for
        #    camera/screen fields (§25.3).
        for predecessor, successor in _adjacent_pairs(ledger):
            for field in _CONSISTENCY_FIELDS:
                before = _field_value(predecessor, field, outgoing=True)
                after = _field_value(successor, field, outgoing=False)
                if before is None or after is None:
                    continue
                if before != after:
                    code = (
                        BlockingReasonCode.SCREEN_DIRECTION_FLIP
                        if field == "screen_direction"
                        else BlockingReasonCode.CAMERA_SIDE_VIOLATION
                    )
                    defects.append(
                        BlockingDefect(
                            code=code,
                            dimension=ReviewDimension.CONTINUITY,
                            message=(
                                f"Cross-shot '{field}' mismatch: predecessor "
                                f"{str(predecessor.shot_id)} ({before}) -> "
                                f"successor {str(successor.shot_id)} ({after})."
                            ),
                            reviewer_type=ReviewerType.CROSS_SHOT,
                            shot_id=str(successor.shot_id),
                            evidence=(f"field={field}", f"before={before}", f"after={after}"),
                        )
                    )
                    evidence.append(f"continuity_mismatch:{field}")

        # 3. Required tail/head frame relation (§25.3): a successor whose
        #    required_state pins a TAIL/FIRST frame must not diverge from the
        #    predecessor's outgoing reference.
        for predecessor, successor in _adjacent_pairs(ledger):
            for field, state in (successor.required_state or {}).items():
                if field.startswith("reference:"):
                    pred_out = _field_value(predecessor, field, outgoing=True)
                    if pred_out is not None and state.value is not None and pred_out != state.value:
                        defects.append(
                            BlockingDefect(
                                code=BlockingReasonCode.TAIL_HEAD_FRAME_RELATION,
                                dimension=ReviewDimension.CONTINUITY,
                                message=(
                                    f"Tail/head frame relation violated: predecessor "
                                    f"{str(predecessor.shot_id)} outgoing {field}={pred_out} "
                                    f"!= successor required {field}={state.value}."
                                ),
                                reviewer_type=ReviewerType.CROSS_SHOT,
                                shot_id=str(successor.shot_id),
                                evidence=(f"field={field}", f"outgoing={pred_out}", f"required={state.value}"),
                            )
                        )
                        evidence.append(f"tail_head_relation:{field}")

        continuity_valid = not defects
        results = (
            DimensionResult(
                dimension=ReviewDimension.CONTINUITY,
                score=1.0 if continuity_valid else 0.0,
                passed=continuity_valid,
                confidence=1.0,
                metric_version=self.metric_version,
                reviewer_type=ReviewerType.CROSS_SHOT,
                blocking_rule=True,
                evidence=tuple(evidence),
            ),
        )

        return CrossShotReviewResult(
            candidate_id=candidate_id,
            dimension_results=results,
            blocking_defects=tuple(defects),
            continuity_valid=continuity_valid,
        )


def _adjacent_pairs(ledger: ContinuityLedger) -> List[Tuple[Any, Any]]:
    entries = list(ledger.entries)
    return [(entries[i], entries[i + 1]) for i in range(len(entries) - 1)]


def _field_value(entry, field: str, *, outgoing: bool) -> Optional[Any]:
    state_map = entry.outgoing_state if outgoing else entry.incoming_state
    state = state_map.get(field)
    return state.value if state is not None else None


def _map_continuity_code(code: ContinuityIssueCode) -> BlockingReasonCode:
    mapping = {
        ContinuityIssueCode.CAMERA_SIDE_VIOLATION: BlockingReasonCode.CAMERA_SIDE_VIOLATION,
        ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE: BlockingReasonCode.PROP_MISMATCH,
        ContinuityIssueCode.CHANGE_OUTSIDE_ALLOWED: BlockingReasonCode.CONTINUITY_VIOLATION,
        ContinuityIssueCode.IDENTITY_HASH_MISMATCH: BlockingReasonCode.IDENTITY_MISMATCH,
        ContinuityIssueCode.PARALLEL_CONFLICT: BlockingReasonCode.CONTINUITY_VIOLATION,
        ContinuityIssueCode.MISSING_REQUIRED_STATE: BlockingReasonCode.CONTINUITY_VIOLATION,
    }
    return mapping.get(code, BlockingReasonCode.CONTINUITY_VIOLATION)


__all__ = [
    "CROSS_SHOT_METRIC_VERSION",
    "CrossShotReviewResult",
    "CrossShotReviewer",
]
