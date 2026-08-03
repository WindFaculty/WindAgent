"""
Deterministic validation reviewer (plan 05 Phase 20 §25.1,
gate VP20_GENERATION_REVIEW_VERIFIED).

The FIRST tier of the reviewer hierarchy (§24): file/media/decoder validity,
hash, duration, resolution, frame rate, stream presence, black/truncated
ending, required candidate metadata/provenance, and safety file checks.

Fail-closed rules:

- a candidate whose file does not decode, or that lacks a video stream for a
  video, is BLOCKED at the deterministic gate — a VLM/human score can NEVER
  mask a deterministic failure (gate condition 1);
- every finding carries a typed reason code + evidence;
- the reviewer is fully deterministic and offline: probe facts are injected
  (the ffprobe adapter lives outside this layer), it never runs subprocesses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from windagent_intelligence.video.reviewers.models import (
    BlockingDefect,
    BlockingReasonCode,
    DimensionResult,
    ReviewDimension,
    ReviewerType,
)

DETERMINISTIC_METRIC_VERSION = "1.0.0"


@dataclass(frozen=True)
class MediaProbeFacts:
    """Deterministic probe facts injected by the caller (ffprobe adapter).

    The reviewer itself never decodes media; it applies rules to these facts
    so the gate stays offline and deterministic.
    """

    content_hash: str
    media_type: str  # image | video | audio | unknown
    decoder_ok: bool
    has_video_stream: bool
    duration_seconds: float
    resolution: str  # e.g. "1280x720" or ""
    frame_rate: float
    black_ending: bool
    truncated_ending: bool
    metadata_provenance_ok: bool
    safety_findings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DeterministicReviewResult:
    """Outcome of the deterministic gate for one candidate."""

    candidate_id: str
    dimension_results: Tuple[DimensionResult, ...]
    blocking_defects: Tuple[BlockingDefect, ...]
    technical_valid: bool

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "dimension_results": [d.to_dict() for d in self.dimension_results],
            "blocking_defects": [b.to_dict() for b in self.blocking_defects],
            "technical_valid": self.technical_valid,
        }


class DeterministicReviewer:
    """Applies the deterministic media/file/safety rules (plan §25.1)."""

    def __init__(self) -> None:
        self.metric_version = DETERMINISTIC_METRIC_VERSION

    def review(self, candidate_id: str, facts: MediaProbeFacts) -> DeterministicReviewResult:
        defects: List[BlockingDefect] = []

        # 1. Hash / file / decoder validity (§25.1)
        if not facts.content_hash or len(facts.content_hash) != 64:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.INVALID_CONTENT_HASH,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Candidate content hash is missing or not a 64-char SHA-256.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=(f"content_hash={facts.content_hash or ''}",),
                )
            )
        if not facts.decoder_ok:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.MEDIA_DECODE_FAILURE,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Media file does not decode — VLM review must not run.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=("decoder_ok=False",),
                )
            )
        if facts.media_type == "video" and not facts.has_video_stream:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.MISSING_VIDEO_STREAM,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Video candidate lacks a video stream — VLM review must not run.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=("has_video_stream=False",),
                )
            )

        # 2. Duration / resolution / frame rate / stream (§25.1)
        if facts.duration_seconds <= 0:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.INVALID_DURATION,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Candidate duration is zero or negative.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=(f"duration_seconds={facts.duration_seconds}",),
                )
            )
        if facts.media_type == "video" and (not facts.resolution or facts.frame_rate <= 0):
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.MISSING_MEDIA_METADATA,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Video candidate is missing resolution or a valid frame rate.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=(f"resolution={facts.resolution!r}", f"frame_rate={facts.frame_rate}"),
                )
            )

        # 3. Black/truncated ending + sample-frame decode (§25.1)
        if facts.black_ending:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.BLACK_ENDING,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Candidate ends in black frames.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=("black_ending=True",),
                )
            )
        if facts.truncated_ending:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.TRUNCATED_ENDING,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Candidate ending is truncated.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=("truncated_ending=True",),
                )
            )

        # 4. Required candidate metadata/provenance (§25.1)
        if not facts.metadata_provenance_ok:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.MISSING_PROVENANCE,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="Candidate metadata/provenance is missing.",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=("metadata_provenance_ok=False",),
                )
            )

        # 5. Safety file checks (§25.1)
        for finding in facts.safety_findings:
            defects.append(
                BlockingDefect(
                    code=BlockingReasonCode.SAFETY_FINDING,
                    dimension=ReviewDimension.SAFETY,
                    message=f"Safety finding: {finding}",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                    shot_id=candidate_id,
                    evidence=(finding,),
                )
            )

        technical_valid = not any(
            d.dimension == ReviewDimension.TECHNICAL_VALIDITY for d in defects
        )

        # Dimension results: TECHNICAL_VALIDITY + SAFETY from the same facts.
        results = (
            DimensionResult(
                dimension=ReviewDimension.TECHNICAL_VALIDITY,
                score=1.0 if technical_valid else 0.0,
                passed=technical_valid,
                confidence=1.0,
                metric_version=self.metric_version,
                reviewer_type=ReviewerType.DETERMINISTIC,
                blocking_rule=True,
                evidence=tuple(d.message for d in defects if d.dimension == ReviewDimension.TECHNICAL_VALIDITY),
            ),
            DimensionResult(
                dimension=ReviewDimension.SAFETY,
                score=1.0 if not facts.safety_findings else 0.0,
                passed=not facts.safety_findings,
                confidence=1.0,
                metric_version=self.metric_version,
                reviewer_type=ReviewerType.DETERMINISTIC,
                blocking_rule=True,
                evidence=tuple(facts.safety_findings),
            ),
        )

        return DeterministicReviewResult(
            candidate_id=candidate_id,
            dimension_results=results,
            blocking_defects=tuple(defects),
            technical_valid=technical_valid,
        )


__all__ = [
    "DETERMINISTIC_METRIC_VERSION",
    "MediaProbeFacts",
    "DeterministicReviewResult",
    "DeterministicReviewer",
]
