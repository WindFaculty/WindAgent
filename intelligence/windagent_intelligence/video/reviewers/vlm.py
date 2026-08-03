"""
Single-candidate VLM review (plan 05 Phase 20 §25.2,
gate VP20_GENERATION_REVIEW_VERIFIED).

The SECOND tier of the reviewer hierarchy (§24): runs only AFTER the
deterministic gate — VLM is never invoked when the file does not decode or
lacks a video stream (§24 "Không chạy VLM nếu file không decode hoặc thiếu
video stream").

Checks:

- prompt compliance against the structured intent;
- identity/location/prop consistency with the approved references;
- camera/action/motion quality;
- dialogue alignment and visual artifacts.

Fail-closed rules:

- the VLM output must be a parseable JSON document with the contract fields
  (dimensions 0..1, confidence 0..1, model/prompt version) — invalid JSON,
  a timeout, an empty response or a schema violation is a REVIEW_ERROR,
  NEVER a PASS (gate condition 3: low confidence/error không tạo false PASS);
- a model failure or unparseable output is recorded as a blocking
  REVIEW_ERROR defect, not silently downgraded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable

from windagent_intelligence.video.reviewers.dimensions import config_for
from windagent_intelligence.video.reviewers.models import (
    BlockingDefect,
    BlockingReasonCode,
    DimensionResult,
    ReviewDimension,
    ReviewerType,
)

VLM_METRIC_VERSION = "1.0.0"
VLM_PROMPT_VERSION = "1.0.0"
VLM_SCHEMA_VERSION = "1.0.0"

VLM_DIMENSIONS = (
    ReviewDimension.PROMPT_COMPLIANCE,
    ReviewDimension.IDENTITY_CONSISTENCY,
    ReviewDimension.LOCATION_CONSISTENCY,
    ReviewDimension.PROP_CONSISTENCY,
    ReviewDimension.MOTION_QUALITY,
    ReviewDimension.CAMERA_COMPLIANCE,
    ReviewDimension.DIALOGUE_ALIGNMENT,
    ReviewDimension.VISUAL_ARTIFACTS,
)


@dataclass(frozen=True)
class VlmReviewRequest:
    """Typed, provider-neutral VLM review request (§25.2)."""

    candidate_id: str
    media_uri: str
    intent_prompt: str  # structured intent (compiled prompt)
    reference_hashes: Tuple[str, ...] = ()
    model: str = "canonical-vlm"
    prompt_version: str = VLM_PROMPT_VERSION
    schema_version: str = VLM_SCHEMA_VERSION


@dataclass(frozen=True)
class VlmReviewResult:
    """Typed VLM completion result (never raises on model I/O)."""

    candidate_id: str
    content: str  # raw JSON text (or "" on failure)
    model: str = "canonical-vlm"
    prompt_version: str = VLM_PROMPT_VERSION
    timed_out: bool = False


@runtime_checkable
class ReviewModelPort(Protocol):
    """Port for a VLM review completion (adapter implemented at composition)."""

    def review(self, request: VlmReviewRequest) -> VlmReviewResult: ...
    async def areview(self, request: VlmReviewRequest) -> VlmReviewResult: ...


@dataclass(frozen=True)
class VlmReviewOutcome:
    """Parsed + validated VLM outcome for one candidate (§25.2)."""

    candidate_id: str
    dimension_results: Tuple[DimensionResult, ...]
    blocking_defects: Tuple[BlockingDefect, ...]
    review_error: bool = False
    error_reason: str = ""
    model: str = ""
    prompt_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "dimension_results": [d.to_dict() for d in self.dimension_results],
            "blocking_defects": [b.to_dict() for b in self.blocking_defects],
            "review_error": self.review_error,
            "error_reason": self.error_reason,
            "model": self.model,
            "prompt_version": self.prompt_version,
        }


class VlmReviewer:
    """Runs + strictly validates a VLM review (plan §25.2)."""

    def __init__(self) -> None:
        self.metric_version = VLM_METRIC_VERSION

    # -- sync ------------------------------------------------------------
    def review(
        self,
        port: ReviewModelPort,
        request: VlmReviewRequest,
    ) -> VlmReviewOutcome:
        raw = port.review(request)
        return self._evaluate(raw)

    # -- async -----------------------------------------------------------
    async def areview(
        self,
        port: ReviewModelPort,
        request: VlmReviewRequest,
    ) -> VlmReviewOutcome:
        raw = await port.areview(request)
        return self._evaluate(raw)

    # -- validation core ----------------------------------------------------
    def _evaluate(self, raw: VlmReviewResult) -> VlmReviewOutcome:
        candidate_id = raw.candidate_id

        # Fail closed on timeout / empty.
        if raw.timed_out:
            return VlmReviewOutcome(
                candidate_id=candidate_id,
                dimension_results=(),
                blocking_defects=(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=ReviewDimension.PROMPT_COMPLIANCE,
                        message="VLM review timed out — never treated as PASS.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=("timed_out=True",),
                    ),
                ),
                review_error=True,
                error_reason="VLM review timed out",
                model=raw.model,
                prompt_version=raw.prompt_version,
            )
        if not raw.content or not raw.content.strip():
            return VlmReviewOutcome(
                candidate_id=candidate_id,
                dimension_results=(),
                blocking_defects=(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=ReviewDimension.PROMPT_COMPLIANCE,
                        message="VLM returned an empty response — never treated as PASS.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=("content_empty=True",),
                    ),
                ),
                review_error=True,
                error_reason="VLM returned an empty response",
                model=raw.model,
                prompt_version=raw.prompt_version,
            )

        # Parse + validate JSON strictly.
        try:
            payload = json.loads(raw.content)
        except (json.JSONDecodeError, TypeError) as exc:
            return VlmReviewOutcome(
                candidate_id=candidate_id,
                dimension_results=(),
                blocking_defects=(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=ReviewDimension.PROMPT_COMPLIANCE,
                        message="VLM output is not valid JSON — never treated as PASS.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=(f"decode_error={exc}",),
                    ),
                ),
                review_error=True,
                error_reason="VLM output is not valid JSON",
                model=raw.model,
                prompt_version=raw.prompt_version,
            )

        if not isinstance(payload, dict):
            return VlmReviewOutcome(
                candidate_id=candidate_id,
                dimension_results=(),
                blocking_defects=(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=ReviewDimension.PROMPT_COMPLIANCE,
                        message="VLM output JSON is not an object — schema violation.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=(f"payload_type={type(payload).__name__}",),
                    ),
                ),
                review_error=True,
                error_reason="VLM output schema violation: not an object",
                model=raw.model,
                prompt_version=raw.prompt_version,
            )

        return self._from_payload(candidate_id, payload, raw)

    def _from_payload(
        self,
        candidate_id: str,
        payload: Dict[str, Any],
        raw: VlmReviewResult,
    ) -> VlmReviewOutcome:
        defects: List[BlockingDefect] = []
        results: List[DimensionResult] = []

        for dimension in VLM_DIMENSIONS:
            key = dimension.value.lower()
            entry = payload.get(key)
            if not isinstance(entry, dict):
                defects.append(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=dimension,
                        message=f"VLM output missing/invalid '{key}' dimension — schema violation.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=(f"{key}={entry!r}",),
                    )
                )
                continue
            score = entry.get("score")
            confidence = entry.get("confidence")
            if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
                defects.append(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=dimension,
                        message=f"VLM '{key}' score out of range / missing.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=(f"score={score!r}",),
                    )
                )
                continue
            if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
                defects.append(
                    BlockingDefect(
                        code=BlockingReasonCode.REVIEW_ERROR,
                        dimension=dimension,
                        message=f"VLM '{key}' confidence out of range / missing.",
                        reviewer_type=ReviewerType.VLM,
                        shot_id=candidate_id,
                        evidence=(f"confidence={confidence!r}",),
                    )
                )
                continue
            evidence = entry.get("evidence") or []
            if not isinstance(evidence, list):
                evidence = []
            cfg = config_for(dimension)
            results.append(
                DimensionResult(
                    dimension=dimension,
                    score=float(score),
                    passed=float(score) >= cfg.pass_threshold,
                    confidence=float(confidence),
                    metric_version=self.metric_version,
                    reviewer_type=ReviewerType.VLM,
                    blocking_rule=cfg.blocking,
                    evidence=tuple(str(e) for e in evidence),
                )
            )

        review_error = any(d.code == BlockingReasonCode.REVIEW_ERROR for d in defects)
        return VlmReviewOutcome(
            candidate_id=candidate_id,
            dimension_results=tuple(results),
            blocking_defects=tuple(defects),
            review_error=review_error,
            error_reason="VLM output schema violation" if review_error else "",
            model=raw.model,
            prompt_version=raw.prompt_version,
        )


__all__ = [
    "VLM_METRIC_VERSION",
    "VLM_PROMPT_VERSION",
    "VLM_SCHEMA_VERSION",
    "VlmReviewRequest",
    "VlmReviewResult",
    "ReviewModelPort",
    "VlmReviewOutcome",
    "VlmReviewer",
]
