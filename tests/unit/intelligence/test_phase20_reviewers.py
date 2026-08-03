"""
Phase 20 — Candidate review & quality gates unit tests (plan 05 §26, gate
VP20_GENERATION_REVIEW_VERIFIED).

Covers the gate test matrix:
- invalid media does not pass the deterministic gate;
- high identity score but a blocking continuity defect -> REJECT;
- VLM timeout / invalid output -> REVIEW_ERROR, never PASS;
- low confidence -> HUMAN_REVIEW_REQUIRED;
- candidate ordering does not affect the selected result;
- cross-shot prop/wardrobe/camera mismatch (via the continuity ledger);
- human override is audited;
- policy/threshold change produces a NEW review revision, never rewrites old
  results;
plus the five gate conditions:
  1. deterministic failures cannot be masked by a VLM/human score;
  2. blocking defects carry typed, automated reason codes;
  3. low confidence / error never creates a false PASS;
  4. selection/rejection traces to policy, model and evidence;
  5. cross-shot review uses the continuity ledger.
"""

from __future__ import annotations

import json

from windagent_core.domain.video_production.continuity import (
    ContinuityFieldState,
    ContinuityLedger,
    ContinuityLedgerEntry,
    ContinuityIssue,
)
from windagent_core.domain.video_production.enums import (
    ContinuityFieldSource,
    ContinuityIssueCode,
)
from windagent_core.domain.video_production.ids import (
    ContinuityIssueId,
    ContinuityLedgerId,
    ProductionRevisionId,
    SceneId,
    ShotId,
    VideoProjectId,
)

from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
from windagent_intelligence.video.reviewers import (
    BLOCKING_DIMENSIONS,
    BlockingDefect,
    BlockingReasonCode,
    CandidateReview,
    CandidateSelector,
    CandidateVerdict,
    CrossShotReviewer,
    DeterministicReviewer,
    DimensionResult,
    HumanSelectionOverride,
    MediaProbeFacts,
    ReviewDimension,
    ReviewPipeline,
    ReviewerType,
    VerdictPolicy,
    VLM_DIMENSIONS,
    VlmReviewer,
    VlmReviewResult,
    config_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _facts(**overrides) -> MediaProbeFacts:
    defaults = dict(
        content_hash="a" * 64,
        media_type="video",
        decoder_ok=True,
        has_video_stream=True,
        duration_seconds=4.0,
        resolution="1280x720",
        frame_rate=24.0,
        black_ending=False,
        truncated_ending=False,
        metadata_provenance_ok=True,
        safety_findings=(),
    )
    defaults.update(overrides)
    return MediaProbeFacts(**defaults)


def _vlm_payload(**overrides) -> str:
    """A valid VLM JSON payload covering all 8 VLM dimensions (0.9 score)."""
    payload: dict = {}
    for dim in VLM_DIMENSIONS:
        key = dim.value.lower()
        entry = overrides.get(dim) or overrides.get(key)
        if entry is None:
            entry = {"score": 0.9, "confidence": 0.9, "evidence": ["probe"]}
        payload[key] = entry
    return json.dumps(payload)


class _FakePort:
    """In-memory ReviewModelPort adapter for tests."""

    def __init__(self, result: VlmReviewResult):
        self._result = result
        self.calls = 0

    def review(self, request) -> VlmReviewResult:
        self.calls += 1
        return self._result

    async def areview(self, request) -> VlmReviewResult:
        self.calls += 1
        return self._result


def _good_vlm_result(candidate_id: str = "cand_1", content: str | None = None) -> VlmReviewResult:
    return VlmReviewResult(
        candidate_id=candidate_id,
        content=content if content is not None else _vlm_payload(),
        model="canonical-vlm",
        prompt_version="1.0.0",
    )


def _dimension(
    dimension: ReviewDimension,
    score: float,
    *,
    confidence: float = 1.0,
    passed: bool | None = None,
    blocking: bool | None = None,
) -> DimensionResult:
    cfg = config_for(dimension)
    return DimensionResult(
        dimension=dimension,
        score=score,
        passed=passed if passed is not None else score >= cfg.pass_threshold,
        confidence=confidence,
        metric_version="1.0.0",
        reviewer_type=ReviewerType.VLM,
        blocking_rule=blocking if blocking is not None else cfg.blocking,
    )


def _ledger_receipt(*, entries=None, issues=None) -> ContinuityLedgerReceipt:
    ledger = ContinuityLedger(
        ledger_id=ContinuityLedgerId("ledger_phase20"),
        project_id=VideoProjectId("vp_phase20"),
        revision_id=ProductionRevisionId("rev_phase20"),
        entries=list(entries or []),
    )
    return ContinuityLedgerReceipt(
        ledger=ledger,
        issues=list(issues or []),
        ledger_hash="h" * 64,
        source_graph_hash="g" * 64,
        source_plan_hash="p" * 64,
        source_package_hash="c" * 64,
    )


def _state(field: str, value) -> ContinuityFieldState:
    return ContinuityFieldState(
        field=field,
        value=value,
        source=ContinuityFieldSource.PREDECESSOR_OUTPUT,
    )


def _entry(shot_id: str, *, incoming=None, outgoing=None, required=None) -> ContinuityLedgerEntry:
    return ContinuityLedgerEntry(
        shot_id=ShotId(shot_id),
        scene_id=SceneId("scn_01"),
        incoming_state=dict(incoming or {}),
        outgoing_state=dict(outgoing or {}),
        required_state=dict(required or {}),
    )


# ---------------------------------------------------------------------------
# §25.1 / §26 — Deterministic gate
# ---------------------------------------------------------------------------
class TestDeterministicGate:
    def test_valid_video_passes_gate(self):
        result = DeterministicReviewer().review("cand_1", _facts())
        assert result.technical_valid is True
        assert result.blocking_defects == ()
        scores = {d.dimension: d.score for d in result.dimension_results}
        assert scores[ReviewDimension.TECHNICAL_VALIDITY] == 1.0
        assert scores[ReviewDimension.SAFETY] == 1.0

    def test_decode_failure_blocks(self):
        result = DeterministicReviewer().review("cand_1", _facts(decoder_ok=False))
        assert result.technical_valid is False
        codes = {d.code for d in result.blocking_defects}
        assert BlockingReasonCode.MEDIA_DECODE_FAILURE in codes

    def test_missing_video_stream_blocks(self):
        result = DeterministicReviewer().review("cand_1", _facts(has_video_stream=False))
        assert result.technical_valid is False
        assert BlockingReasonCode.MISSING_VIDEO_STREAM in {d.code for d in result.blocking_defects}

    def test_invalid_hash_blocks(self):
        result = DeterministicReviewer().review("cand_1", _facts(content_hash="short"))
        assert result.technical_valid is False
        assert BlockingReasonCode.INVALID_CONTENT_HASH in {d.code for d in result.blocking_defects}

    def test_zero_duration_blocks(self):
        result = DeterministicReviewer().review("cand_1", _facts(duration_seconds=0.0))
        assert result.technical_valid is False
        assert BlockingReasonCode.INVALID_DURATION in {d.code for d in result.blocking_defects}

    def test_missing_metadata_blocks_video(self):
        result = DeterministicReviewer().review(
            "cand_1", _facts(resolution="", frame_rate=0.0)
        )
        assert BlockingReasonCode.MISSING_MEDIA_METADATA in {
            d.code for d in result.blocking_defects
        }

    def test_black_and_truncated_ending_block(self):
        result = DeterministicReviewer().review("cand_1", _facts(black_ending=True, truncated_ending=True))
        codes = {d.code for d in result.blocking_defects}
        assert BlockingReasonCode.BLACK_ENDING in codes
        assert BlockingReasonCode.TRUNCATED_ENDING in codes

    def test_missing_provenance_blocks(self):
        result = DeterministicReviewer().review("cand_1", _facts(metadata_provenance_ok=False))
        assert BlockingReasonCode.MISSING_PROVENANCE in {d.code for d in result.blocking_defects}

    def test_safety_finding_blocks(self):
        result = DeterministicReviewer().review("cand_1", _facts(safety_findings=("nsfw-content",)))
        assert BlockingReasonCode.SAFETY_FINDING in {d.code for d in result.blocking_defects}
        assert result.technical_valid is True  # safety is not technical validity


# ---------------------------------------------------------------------------
# §25.2 / §26 — VLM review: fail closed, never a false PASS
# ---------------------------------------------------------------------------
class TestVlmReviewer:
    def test_valid_payload_scores_and_thresholds(self):
        outcome = VlmReviewer().review(_FakePort(_good_vlm_result()), _vlm_request())
        assert outcome.review_error is False
        assert len(outcome.dimension_results) == len(VLM_DIMENSIONS)
        # 0.9 >= every threshold -> all passed
        assert all(d.passed for d in outcome.dimension_results)

    def test_below_threshold_dimension_fails(self):
        content = _vlm_payload(
            identity_consistency={"score": 0.3, "confidence": 0.9, "evidence": ["mismatch"]}
        )
        outcome = VlmReviewer().review(_FakePort(_good_vlm_result(content=content)), _vlm_request())
        ident = next(d for d in outcome.dimension_results if d.dimension == ReviewDimension.IDENTITY_CONSISTENCY)
        assert ident.passed is False  # 0.3 < 0.7 threshold

    def test_timeout_is_review_error_never_pass(self):
        raw = VlmReviewResult(candidate_id="cand_1", content="", model="m", timed_out=True)
        outcome = VlmReviewer().review(_FakePort(raw), _vlm_request())
        assert outcome.review_error is True
        assert outcome.error_reason
        assert any(d.code == BlockingReasonCode.REVIEW_ERROR for d in outcome.blocking_defects)

    def test_empty_response_is_review_error(self):
        raw = VlmReviewResult(candidate_id="cand_1", content="   ")
        outcome = VlmReviewer().review(_FakePort(raw), _vlm_request())
        assert outcome.review_error is True

    def test_invalid_json_is_review_error(self):
        raw = VlmReviewResult(candidate_id="cand_1", content="{not json")
        outcome = VlmReviewer().review(_FakePort(raw), _vlm_request())
        assert outcome.review_error is True

    def test_schema_violation_missing_dimension_is_review_error(self):
        content = json.dumps({"motion_quality": {"score": 0.9, "confidence": 0.9}})
        outcome = VlmReviewer().review(_FakePort(_good_vlm_result(content=content)), _vlm_request())
        assert outcome.review_error is True  # other 7 dimensions missing

    def test_score_out_of_range_is_review_error(self):
        content = _vlm_payload(identity_consistency={"score": 1.5, "confidence": 0.9})
        outcome = VlmReviewer().review(_FakePort(_good_vlm_result(content=content)), _vlm_request())
        assert outcome.review_error is True

    def test_async_path_matches_sync(self):
        port = _FakePort(_good_vlm_result())
        import asyncio

        async def run():
            return await VlmReviewer().areview(port, _vlm_request())

        outcome = asyncio.run(run())
        assert outcome.review_error is False
        assert port.calls == 1


def _vlm_request():
    from windagent_intelligence.video.reviewers import VlmReviewRequest

    return VlmReviewRequest(
        candidate_id="cand_1",
        media_uri="file:///tmp/cand_1.mp4",
        intent_prompt="intent",
    )


# ---------------------------------------------------------------------------
# §25.3 / §26 — Cross-shot review via the continuity ledger (gate condition 5)
# ---------------------------------------------------------------------------
class TestCrossShotReviewer:
    def test_clean_ledger_is_continuity_valid(self):
        receipt = _ledger_receipt(
            entries=[
                _entry("s1", outgoing={"camera_side": _state("camera_side", "SIDE_A")}),
                _entry("s2", incoming={"camera_side": _state("camera_side", "SIDE_A")}),
            ]
        )
        result = CrossShotReviewer().review("cand_1", receipt)
        assert result.continuity_valid is True
        assert result.blocking_defects == ()

    def test_camera_side_flip_across_shots_is_blocking(self):
        receipt = _ledger_receipt(
            entries=[
                _entry("s1", outgoing={"camera_side": _state("camera_side", "SIDE_A")}),
                _entry("s2", incoming={"camera_side": _state("camera_side", "SIDE_B")}),
            ]
        )
        result = CrossShotReviewer().review("cand_1", receipt)
        assert result.continuity_valid is False
        codes = {d.code for d in result.blocking_defects}
        assert BlockingReasonCode.CAMERA_SIDE_VIOLATION in codes
        # gate condition 2: typed reason code + evidence
        defect = next(d for d in result.blocking_defects)
        assert defect.evidence

    def test_ledger_blocking_issue_surfaces_as_typed_defect(self):
        issue = ContinuityIssue(
            issue_id=ContinuityIssueId("ci_1"),
            code=ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE,
            message="prop changes hands without action",
            blocking=True,
            shot_id=ShotId("s2"),
        )
        receipt = _ledger_receipt(entries=[_entry("s1"), _entry("s2")], issues=[issue])
        result = CrossShotReviewer().review("cand_1", receipt)
        assert result.continuity_valid is False
        assert BlockingReasonCode.PROP_MISMATCH in {d.code for d in result.blocking_defects}

    def test_tail_head_frame_relation_violation(self):
        receipt = _ledger_receipt(
            entries=[
                _entry(
                    "s1",
                    outgoing={"reference:tail_frame": _state("reference:tail_frame", "f_a")},
                ),
                _entry(
                    "s2",
                    required={"reference:tail_frame": _state("reference:tail_frame", "f_b")},
                ),
            ]
        )
        result = CrossShotReviewer().review("cand_1", receipt)
        assert BlockingReasonCode.TAIL_HEAD_FRAME_RELATION in {
            d.code for d in result.blocking_defects
        }


# ---------------------------------------------------------------------------
# §25.4 / §26 — Verdict policy
# ---------------------------------------------------------------------------
class TestVerdictPolicy:
    def _decide(self, dimensions=(), defects=()):
        return VerdictPolicy().decide(
            candidate_id="cand_1",
            request_hash="r" * 64,
            shot_id="s1",
            dimensions=tuple(dimensions),
            blocking_defects=tuple(defects),
        )

    def test_approve_when_all_good(self):
        review = self._decide(dimensions=(_dimension(ReviewDimension.MOTION_QUALITY, 0.9),))
        assert review.verdict == CandidateVerdict.APPROVE

    def test_blocking_defect_wins_over_high_aggregate(self):
        """§26: high identity score but a blocking defect -> REJECT."""
        dimensions = (
            _dimension(ReviewDimension.IDENTITY_CONSISTENCY, 0.95),
            _dimension(ReviewDimension.MOTION_QUALITY, 0.9),
        )
        defect = BlockingDefect(
            code=BlockingReasonCode.PROP_MISMATCH,
            dimension=ReviewDimension.PROP_CONSISTENCY,
            message="prop changes hands",
            reviewer_type=ReviewerType.CROSS_SHOT,
            shot_id="s1",
        )
        review = self._decide(dimensions=dimensions, defects=[defect])
        assert review.verdict == CandidateVerdict.REJECT
        assert review.average_score() > 0.9  # aggregate high, still rejected

    def test_review_error_is_never_pass(self):
        defect = BlockingDefect(
            code=BlockingReasonCode.REVIEW_ERROR,
            dimension=ReviewDimension.PROMPT_COMPLIANCE,
            message="VLM timeout",
            reviewer_type=ReviewerType.VLM,
        )
        review = self._decide(defects=[defect])
        assert review.verdict == CandidateVerdict.REVIEW_ERROR

    def test_below_threshold_is_reject(self):
        review = self._decide(dimensions=(_dimension(ReviewDimension.PROMPT_COMPLIANCE, 0.4),))
        assert review.verdict == CandidateVerdict.REJECT

    def test_low_confidence_routes_to_human(self):
        review = self._decide(
            dimensions=(_dimension(ReviewDimension.MOTION_QUALITY, 0.9, confidence=0.2),)
        )
        assert review.verdict == CandidateVerdict.HUMAN_REVIEW_REQUIRED

    def test_low_confidence_never_false_pass(self):
        """Gate condition 3: a low-confidence high-score dimension -> human, not APPROVE."""
        review = self._decide(
            dimensions=(_dimension(ReviewDimension.IDENTITY_CONSISTENCY, 0.95, confidence=0.3),)
        )
        assert review.verdict == CandidateVerdict.HUMAN_REVIEW_REQUIRED


# ---------------------------------------------------------------------------
# §25.5 / §26 — Selection: order-independent, human override audited
# ---------------------------------------------------------------------------
def _review(candidate_id: str, verdict: CandidateVerdict, score: float) -> CandidateReview:
    return CandidateReview(
        review_id=f"rv_{candidate_id}",
        candidate_id=candidate_id,
        request_hash="r" * 64,
        shot_id="s1",
        dimensions=(_dimension(ReviewDimension.MOTION_QUALITY, score),),
        blocking_defects=(),
        verdict=verdict,
        policy_version="1.0.0",
        reason="test",
    )


class TestCandidateSelector:
    def test_ranks_only_unblocked(self):
        blocked = _review("cand_blocked", CandidateVerdict.REJECT, 0.99)
        good = _review("cand_good", CandidateVerdict.APPROVE, 0.8)
        better = _review("cand_better", CandidateVerdict.APPROVE, 0.9)
        record = CandidateSelector().select(
            run_id="run_1",
            reviews=[blocked, good, better],
            policy_version="1.0.0",
        )
        assert record.selected_candidate_id == "cand_better"  # blocked 0.99 never selected
        assert "cand_blocked" not in record.ranked
        assert record.ranked == ("cand_better", "cand_good")

    def test_candidate_ordering_does_not_affect_result(self):
        """§26: input list order never changes the selected result."""
        a = _review("cand_a", CandidateVerdict.APPROVE, 0.7)
        b = _review("cand_b", CandidateVerdict.APPROVE, 0.9)
        c = _review("cand_c", CandidateVerdict.APPROVE, 0.8)
        r1 = CandidateSelector().select(run_id="run_1", reviews=[a, b, c], policy_version="1.0.0")
        r2 = CandidateSelector().select(run_id="run_1", reviews=[c, a, b], policy_version="1.0.0")
        assert r1.selected_candidate_id == r2.selected_candidate_id == "cand_b"
        assert r1.ranked == r2.ranked

    def test_no_approvable_candidate(self):
        record = CandidateSelector().select(
            run_id="run_1",
            reviews=[_review("cand_x", CandidateVerdict.REJECT, 0.9)],
            policy_version="1.0.0",
        )
        assert record.selected_candidate_id is None
        assert record.reason

    def test_human_override_is_audited_and_wins(self):
        blocked = _review("cand_blocked", CandidateVerdict.REJECT, 0.95)
        override = HumanSelectionOverride(
            override_id="ovr_1",
            candidate_id="cand_blocked",
            actor="director-1",
            decision=CandidateVerdict.APPROVE,
            reason="acceptable after human review",
            recorded_at=123.0,
        )
        record = CandidateSelector().select(
            run_id="run_1",
            reviews=[blocked],
            human_override=override,
            policy_version="1.0.0",
        )
        assert record.selected_candidate_id == "cand_blocked"
        assert record.human_override is not None
        assert record.human_override.actor == "director-1"
        assert record.human_override.reason == "acceptable after human review"
        assert "human override by director-1" in record.reason

    def test_retry_proposal_names_fields(self):
        rejected = _review("cand_r", CandidateVerdict.REJECT, 0.4)
        rejected = CandidateReview(
            review_id=rejected.review_id,
            candidate_id=rejected.candidate_id,
            request_hash=rejected.request_hash,
            shot_id=rejected.shot_id,
            dimensions=rejected.dimensions,
            blocking_defects=(
                BlockingDefect(
                    code=BlockingReasonCode.BLACK_ENDING,
                    dimension=ReviewDimension.TECHNICAL_VALIDITY,
                    message="ends black",
                    reviewer_type=ReviewerType.DETERMINISTIC,
                ),
            ),
            verdict=rejected.verdict,
            policy_version=rejected.policy_version,
            reason=rejected.reason,
        )
        record = CandidateSelector().select(
            run_id="run_1", reviews=[rejected], policy_version="1.0.0"
        )
        assert len(record.retry_proposals) == 1
        proposal = record.retry_proposals[0]
        assert proposal.candidate_id == "cand_r"
        assert "generation.duration" in proposal.request_field_changes

    def test_selection_record_traces_policy_and_algorithm(self):
        """Gate condition 4: selection traces to policy + algorithm version."""
        review = _review("cand_a", CandidateVerdict.APPROVE, 0.8)
        record = CandidateSelector().select(
            run_id="run_1",
            reviews=[review],
            policy_version="1.0.0",
        )
        assert record.algorithm_version
        assert record.policy_version == "1.0.0"
        assert record.reason
        assert record.candidates_reviewed == ("cand_a",)
        # The candidate review itself carries policy + metric version + reviewer
        # type + evidence — the selection record names exactly that candidate.
        assert record.ranked == ("cand_a",)
        assert review.policy_version == "1.0.0"
        assert review.dimensions[0].metric_version
        assert review.dimensions[0].reviewer_type is not None


# ---------------------------------------------------------------------------
# §24 / §26 — Pipeline hierarchy (gate conditions 1, 3, 5)
# ---------------------------------------------------------------------------
class TestReviewPipeline:
    def _pipeline(self) -> ReviewPipeline:
        return ReviewPipeline(
            deterministic=DeterministicReviewer(),
            vlm=VlmReviewer(),
            cross_shot=CrossShotReviewer(),
            verdict=VerdictPolicy(),
            selector=CandidateSelector(),
        )

    def _receipt(self, **overrides):
        pipeline = self._pipeline()
        return pipeline.review_candidate(
            candidate_id=overrides.get("candidate_id", "cand_1"),
            request_hash="r" * 64,
            shot_id="s1",
            media_facts=overrides.get("media_facts", _facts()),
            model_port=_FakePort(_good_vlm_result()),
            intent_prompt="intent",
            reference_hashes=(),
            media_uri="file:///tmp/cand_1.mp4",
            ledger_receipt=overrides.get("ledger_receipt"),
        )

    def test_full_pipeline_approves_clean_candidate(self):
        receipt = self._receipt()
        assert receipt.review.verdict == CandidateVerdict.APPROVE
        assert receipt.deterministic is not None
        assert receipt.vlm is not None
        assert len(receipt.review.dimensions) == 2 + len(VLM_DIMENSIONS)

    def test_vlm_skipped_when_deterministic_fails(self):
        """Gate condition 1 + §24: no VLM run on a non-decode candidate."""
        port = _FakePort(_good_vlm_result())
        pipeline = self._pipeline()
        receipt = pipeline.review_candidate(
            candidate_id="cand_bad",
            request_hash="r" * 64,
            shot_id="s1",
            media_facts=_facts(decoder_ok=False),
            model_port=port,
            intent_prompt="intent",
            media_uri="file:///tmp/cand_bad.mp4",
        )
        assert port.calls == 0  # VLM never invoked
        assert receipt.vlm is None
        assert receipt.review.verdict == CandidateVerdict.REJECT

    def test_deterministic_failure_not_masked_by_high_vlm_score(self):
        """Gate condition 1: even a perfect VLM cannot mask a decode failure."""
        pipeline = self._pipeline()
        receipt = pipeline.review_candidate(
            candidate_id="cand_bad",
            request_hash="r" * 64,
            shot_id="s1",
            media_facts=_facts(decoder_ok=False),
            model_port=_FakePort(_good_vlm_result()),  # would pass every dimension
            intent_prompt="intent",
            media_uri="file:///tmp/cand_bad.mp4",
        )
        assert receipt.review.verdict == CandidateVerdict.REJECT
        assert any(
            d.code != BlockingReasonCode.REVIEW_ERROR for d in receipt.review.blocking_defects
        )

    def test_vlm_review_error_routes_to_review_error(self):
        pipeline = self._pipeline()
        receipt = pipeline.review_candidate(
            candidate_id="cand_1",
            request_hash="r" * 64,
            shot_id="s1",
            media_facts=_facts(),
            model_port=_FakePort(VlmReviewResult(candidate_id="cand_1", content="bad")),
            intent_prompt="intent",
            media_uri="file:///tmp/cand_1.mp4",
        )
        assert receipt.review.verdict == CandidateVerdict.REVIEW_ERROR

    def test_cross_shot_runs_when_ledger_provided(self):
        """Gate condition 5: cross-shot review uses the continuity ledger."""
        receipt = self._receipt(
            ledger_receipt=_ledger_receipt(
                entries=[
                    _entry("s1", outgoing={"camera_side": _state("camera_side", "SIDE_A")}),
                    _entry("s2", incoming={"camera_side": _state("camera_side", "SIDE_B")}),
                ]
            )
        )
        assert receipt.cross_shot is not None
        assert receipt.review.verdict == CandidateVerdict.REJECT  # camera flip blocking

    def test_select_uses_pipeline_verdicts(self):
        pipeline = self._pipeline()
        r1 = self._receipt(candidate_id="cand_a")
        r2 = self._receipt(candidate_id="cand_b")
        r_bad = pipeline.review_candidate(
            candidate_id="cand_bad",
            request_hash="r" * 64,
            shot_id="s1",
            media_facts=_facts(decoder_ok=False),
            model_port=_FakePort(_good_vlm_result()),
            intent_prompt="intent",
            media_uri="file:///tmp/cand_bad.mp4",
        )
        record = pipeline.select(run_id="run_1", receipts=[r1, r2, r_bad])
        assert record.selected_candidate_id in ("cand_a", "cand_b")
        assert "cand_bad" not in record.ranked


# ---------------------------------------------------------------------------
# §26 — Policy/threshold change creates a NEW revision, never rewrites old
# ---------------------------------------------------------------------------
class TestPolicyVersioning:
    def test_review_records_policy_version(self):
        review = VerdictPolicy(policy_version="1.0.0").decide(
            candidate_id="cand_1",
            request_hash="r" * 64,
            shot_id="s1",
            dimensions=(_dimension(ReviewDimension.MOTION_QUALITY, 0.9),),
            blocking_defects=(),
        )
        assert review.policy_version == "1.0.0"

    def test_new_policy_version_produces_new_review_revision(self):
        dims = (_dimension(ReviewDimension.PROMPT_COMPLIANCE, 0.65),)  # 0.65 < 0.7 -> REJECT
        old = VerdictPolicy(policy_version="1.0.0").decide(
            candidate_id="cand_1", request_hash="r" * 64, shot_id="s1",
            dimensions=dims, blocking_defects=(),
        )
        # A threshold change is a NEW policy version (e.g. 1.1.0). The SAME
        # candidate under the new version is a new review; the old review is
        # untouched (immutable dataclass + its own version).
        new = VerdictPolicy(policy_version="1.1.0").decide(
            candidate_id="cand_1", request_hash="r" * 64, shot_id="s1",
            dimensions=dims, blocking_defects=(),
        )
        assert old.policy_version == "1.0.0"
        assert new.policy_version == "1.1.0"
        assert old.review_id != new.review_id  # revision identity differs
        assert old.verdict == new.verdict  # same inputs, same verdict semantics
        assert old.reviewed_at == new.reviewed_at == 0.0

    def test_catalog_version_is_frozen_in_dimension_catalog(self):
        from windagent_intelligence.video.reviewers import REVIEW_POLICY_VERSION

        assert REVIEW_POLICY_VERSION == "1.0.0"
        # blocking dimensions are a stable set
        assert ReviewDimension.TECHNICAL_VALIDITY in BLOCKING_DIMENSIONS
        assert ReviewDimension.SAFETY in BLOCKING_DIMENSIONS
        assert ReviewDimension.PROMPT_COMPLIANCE in BLOCKING_DIMENSIONS
        assert ReviewDimension.MOTION_QUALITY not in BLOCKING_DIMENSIONS
