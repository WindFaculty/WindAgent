#!/usr/bin/env python3
"""
Phase 20 verification — VP20_GENERATION_REVIEW_VERIFIED (plan 05 §22–§27).

Verifies the candidate review & quality gate layer
(`intelligence/windagent_intelligence/video/reviewers/`: dimensions,
deterministic, vlm, cross_shot, verdict, selection, pipeline) against the
contracts in `docs/video_production/generation_review/`:

  artifacts/video_production/phase_20/
  ├── dimension_catalog_receipt.json    (11 dimensions, thresholds, blocking)
  ├── deterministic_gate_receipt.json   (media/file/safety fail-closed gate)
  ├── vlm_review_receipt.json           (fail-closed, never a false PASS)
  ├── cross_shot_receipt.json           (continuity ledger, typed defects)
  ├── verdict_policy_receipt.json       (blocking wins, low confidence -> human)
  ├── selection_receipt.json            (rank unblocked, override audit, retry)
  ├── pipeline_receipt.json             (§24 hierarchy — VLM gated on det)
  └── phase_verdict.json

Gate conditions (plan 05 §27):
  1. deterministic failures cannot be masked by VLM/human score;
  2. blocking defects carry typed, automated reason codes;
  3. low confidence / error never creates a false PASS;
  4. selection/rejection traces to policy, model and evidence;
  5. cross-shot review uses the continuity ledger.

Deterministic: fixed clock (FIXED_CLOCK) -> receipts byte-identical across
runs (modulo generated_at / verified_at). Supports --no-write / --verify-only.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_20"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_core.domain.video_production.continuity import (  # noqa: E402
    ContinuityFieldState,
    ContinuityLedger,
    ContinuityLedgerEntry,
    ContinuityIssue,
)
from windagent_core.domain.video_production.enums import (  # noqa: E402
    ContinuityFieldSource,
    ContinuityIssueCode,
)
from windagent_core.domain.video_production.ids import (  # noqa: E402
    ContinuityIssueId,
    ContinuityLedgerId,
    ProductionRevisionId,
    SceneId,
    ShotId,
    VideoProjectId,
)
from windagent_intelligence.video.continuity.models import (  # noqa: E402
    ContinuityLedgerReceipt,
)
from windagent_intelligence.video.reviewers import (  # noqa: E402
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
    REVIEW_DIMENSIONS,
    REVIEW_POLICY_VERSION,
    ReviewDimension,
    ReviewPipeline,
    ReviewerType,
    VLM_DIMENSIONS,
    VerdictPolicy,
    VlmReviewer,
    VlmReviewRequest,
    VlmReviewResult,
    config_for,
)

FIXED_CLOCK = 1700000000.0  # deterministic epoch for all receipts


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


# ---------------------------------------------------------------------------
# Fixtures
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
    payload: dict = {}
    for dim in VLM_DIMENSIONS:
        key = dim.value.lower()
        entry = overrides.get(dim) or overrides.get(key)
        if entry is None:
            entry = {"score": 0.9, "confidence": 0.9, "evidence": ["probe"]}
        payload[key] = entry
    return json.dumps(payload)


class _FakePort:
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
) -> DimensionResult:
    cfg = config_for(dimension)
    return DimensionResult(
        dimension=dimension,
        score=score,
        passed=score >= cfg.pass_threshold,
        confidence=confidence,
        metric_version="1.0.0",
        reviewer_type=ReviewerType.VLM,
        blocking_rule=cfg.blocking,
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


def _review(candidate_id: str, verdict: CandidateVerdict, score: float) -> "CandidateReview":
    return CandidateReview(
        review_id=f"rv_{candidate_id}:1.0.0",
        candidate_id=candidate_id,
        request_hash="r" * 64,
        shot_id="s1",
        dimensions=(_dimension(ReviewDimension.MOTION_QUALITY, score),),
        blocking_defects=(),
        verdict=verdict,
        policy_version="1.0.0",
        reason="test",
    )


# ---------------------------------------------------------------------------
# Receipt 1 — dimension catalog (§23)
# ---------------------------------------------------------------------------


def verify_dimension_catalog() -> dict:
    checks = []
    _record(checks, "policy_version_fixed", REVIEW_POLICY_VERSION == "1.0.0", REVIEW_POLICY_VERSION)
    _record(checks, "eleven_dimensions", len(REVIEW_DIMENSIONS) == 11, f"count={len(REVIEW_DIMENSIONS)}")
    _record(checks, "all_dimensions_have_config", all(
        d in REVIEW_DIMENSIONS for d in ReviewDimension
    ), "every enum member has a config")
    blocking = BLOCKING_DIMENSIONS
    _record(checks, "blocking_set_frozen", isinstance(blocking, frozenset), type(blocking).__name__)
    _record(checks, "blocking_core_rules", (
        ReviewDimension.TECHNICAL_VALIDITY in blocking
        and ReviewDimension.SAFETY in blocking
        and ReviewDimension.CONTINUITY in blocking
    ), "technical/safety/continuity are blocking")
    _record(checks, "non_blocking_quality_rules", (
        ReviewDimension.MOTION_QUALITY not in blocking
        and ReviewDimension.DIALOGUE_ALIGNMENT not in blocking
    ), "motion/dialogue are non-blocking")
    resolved = config_for(ReviewDimension.SAFETY)  # raises on unknown dimension
    _record(checks, "config_for_resolves_known", resolved is not None, "known dimension resolves")

    catalog = {
        d.value: {
            "reviewer_type": cfg.reviewer_type.value,
            "pass_threshold": cfg.pass_threshold,
            "confidence_floor": cfg.confidence_floor,
            "blocking": cfg.blocking,
        }
        for d, cfg in sorted(REVIEW_DIMENSIONS.items(), key=lambda kv: kv[0].value)
    }
    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "dimension_catalog",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "policy_version": REVIEW_POLICY_VERSION,
        "catalog": catalog,
    }


# ---------------------------------------------------------------------------
# Receipt 2 — deterministic gate (§25.1, gate condition 1)
# ---------------------------------------------------------------------------


def verify_deterministic_gate() -> dict:
    checks = []
    reviewer = DeterministicReviewer()

    ok = reviewer.review("cand_ok", _facts())
    _record(checks, "valid_video_passes", ok.technical_valid is True and ok.blocking_defects == (),
            f"technical_valid={ok.technical_valid}")

    bad = reviewer.review("cand_bad", _facts(decoder_ok=False))
    _record(checks, "decode_failure_blocks", bad.technical_valid is False, "technical_valid=False")
    _record(checks, "decode_failure_typed", BlockingReasonCode.MEDIA_DECODE_FAILURE in
            {d.code for d in bad.blocking_defects}, "typed reason code")

    nostream = reviewer.review("cand_nostream", _facts(has_video_stream=False))
    _record(checks, "missing_stream_blocks", BlockingReasonCode.MISSING_VIDEO_STREAM in
            {d.code for d in nostream.blocking_defects}, "MISSING_VIDEO_STREAM")

    badhash = reviewer.review("cand_badhash", _facts(content_hash="short"))
    _record(checks, "invalid_hash_blocks", BlockingReasonCode.INVALID_CONTENT_HASH in
            {d.code for d in badhash.blocking_defects}, "INVALID_CONTENT_HASH")

    zero = reviewer.review("cand_zero", _facts(duration_seconds=0.0))
    _record(checks, "zero_duration_blocks", BlockingReasonCode.INVALID_DURATION in
            {d.code for d in zero.blocking_defects}, "INVALID_DURATION")

    nometa = reviewer.review("cand_nometa", _facts(resolution="", frame_rate=0.0))
    _record(checks, "missing_metadata_blocks", BlockingReasonCode.MISSING_MEDIA_METADATA in
            {d.code for d in nometa.blocking_defects}, "MISSING_MEDIA_METADATA")

    ending = reviewer.review("cand_ending", _facts(black_ending=True, truncated_ending=True))
    end_codes = {d.code for d in ending.blocking_defects}
    _record(checks, "black_ending_blocks", BlockingReasonCode.BLACK_ENDING in end_codes, "BLACK_ENDING")
    _record(checks, "truncated_ending_blocks", BlockingReasonCode.TRUNCATED_ENDING in end_codes, "TRUNCATED_ENDING")

    noprov = reviewer.review("cand_noprov", _facts(metadata_provenance_ok=False))
    _record(checks, "missing_provenance_blocks", BlockingReasonCode.MISSING_PROVENANCE in
            {d.code for d in noprov.blocking_defects}, "MISSING_PROVENANCE")

    safety = reviewer.review("cand_safety", _facts(safety_findings=("nsfw-content",)))
    _record(checks, "safety_finding_blocks", BlockingReasonCode.SAFETY_FINDING in
            {d.code for d in safety.blocking_defects}, "SAFETY_FINDING")
    _record(checks, "safety_not_technical", safety.technical_valid is True,
            "safety is a separate blocking dimension")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "deterministic_gate",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "metric_version": reviewer.metric_version,
    }


# ---------------------------------------------------------------------------
# Receipt 3 — VLM review (§25.2, gate condition 3)
# ---------------------------------------------------------------------------


def verify_vlm_review() -> dict:
    checks = []
    reviewer = VlmReviewer()
    request = VlmReviewRequest(
        candidate_id="cand_1",
        media_uri="file:///tmp/cand_1.mp4",
        intent_prompt="intent",
    )

    good = reviewer.review(_FakePort(_good_vlm_result()), request)
    _record(checks, "valid_payload_all_dimensions", len(good.dimension_results) == len(VLM_DIMENSIONS),
            f"dims={len(good.dimension_results)}")
    _record(checks, "valid_payload_all_passed", all(d.passed for d in good.dimension_results),
            "0.9 >= every threshold")
    _record(checks, "no_review_error", good.review_error is False, "clean parse")

    timed = reviewer.review(
        _FakePort(VlmReviewResult(candidate_id="cand_1", content="", timed_out=True)), request)
    _record(checks, "timeout_is_review_error", timed.review_error is True, timed.error_reason)
    _record(checks, "timeout_defect_typed", any(
        d.code == BlockingReasonCode.REVIEW_ERROR for d in timed.blocking_defects), "REVIEW_ERROR defect")

    empty = reviewer.review(
        _FakePort(VlmReviewResult(candidate_id="cand_1", content="   ")), request)
    _record(checks, "empty_response_is_error", empty.review_error is True, empty.error_reason)

    badjson = reviewer.review(
        _FakePort(VlmReviewResult(candidate_id="cand_1", content="{not json")), request)
    _record(checks, "invalid_json_is_error", badjson.review_error is True, badjson.error_reason)

    missing = reviewer.review(
        _FakePort(_good_vlm_result(content=json.dumps(
            {"motion_quality": {"score": 0.9, "confidence": 0.9}}))), request)
    _record(checks, "schema_violation_is_error", missing.review_error is True, missing.error_reason)

    outofrange = reviewer.review(
        _FakePort(_good_vlm_result(content=_vlm_payload(
            identity_consistency={"score": 1.5, "confidence": 0.9}))), request)
    _record(checks, "score_out_of_range_is_error", outofrange.review_error is True, outofrange.error_reason)

    low = reviewer.review(
        _FakePort(_good_vlm_result(content=_vlm_payload(
            identity_consistency={"score": 0.3, "confidence": 0.9, "evidence": ["mismatch"]}))), request)
    ident = next(d for d in low.dimension_results
                 if d.dimension == ReviewDimension.IDENTITY_CONSISTENCY)
    _record(checks, "below_threshold_not_passed", ident.passed is False, f"score={ident.score}")

    # determinism: same payload -> same outcome
    r1 = reviewer.review(_FakePort(_good_vlm_result()), request)
    r2 = reviewer.review(_FakePort(_good_vlm_result()), request)
    _record(checks, "outcome_deterministic", [d.to_dict() for d in r1.dimension_results] ==
            [d.to_dict() for d in r2.dimension_results], "same input -> same scores")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "vlm_review",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "schema_version": "1.0.0",
        "sample_outcome": good.to_dict(),
    }


# ---------------------------------------------------------------------------
# Receipt 4 — cross-shot continuity (§25.3, gate condition 5)
# ---------------------------------------------------------------------------


def verify_cross_shot() -> dict:
    checks = []
    reviewer = CrossShotReviewer()

    clean = reviewer.review("cand_1", _ledger_receipt(
        entries=[
            _entry("s1", outgoing={"camera_side": _state("camera_side", "SIDE_A")}),
            _entry("s2", incoming={"camera_side": _state("camera_side", "SIDE_A")}),
        ],
    ))
    _record(checks, "clean_ledger_valid", clean.continuity_valid is True and clean.blocking_defects == (),
            "consistent camera side")

    flip = reviewer.review("cand_1", _ledger_receipt(
        entries=[
            _entry("s1", outgoing={"camera_side": _state("camera_side", "SIDE_A")}),
            _entry("s2", incoming={"camera_side": _state("camera_side", "SIDE_B")}),
        ],
    ))
    _record(checks, "camera_flip_blocking", BlockingReasonCode.CAMERA_SIDE_VIOLATION in
            {d.code for d in flip.blocking_defects}, "typed defect")
    _record(checks, "camera_flip_evidence", all(d.evidence for d in flip.blocking_defects),
            "defects carry evidence")

    issue = ContinuityIssue(
        issue_id=ContinuityIssueId("ci_1"),
        code=ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE,
        message="prop changes hands without action",
        blocking=True,
        shot_id=ShotId("s2"),
    )
    led = reviewer.review("cand_1", _ledger_receipt(
        entries=[_entry("s1"), _entry("s2")], issues=[issue],
    ))
    _record(checks, "ledger_issue_mapped_typed", BlockingReasonCode.PROP_MISMATCH in
            {d.code for d in led.blocking_defects}, "PROP_UNEXPLAINED_CHANGE -> PROP_MISMATCH")

    tail = reviewer.review("cand_1", _ledger_receipt(
        entries=[
            _entry("s1", outgoing={"reference:tail_frame": _state("reference:tail_frame", "f_a")}),
            _entry("s2", required={"reference:tail_frame": _state("reference:tail_frame", "f_b")}),
        ],
    ))
    _record(checks, "tail_head_relation_violation", BlockingReasonCode.TAIL_HEAD_FRAME_RELATION in
            {d.code for d in tail.blocking_defects}, "required reference mismatch")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "cross_shot",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "metric_version": reviewer.metric_version,
        "ledger_source": "ContinuityLedgerReceipt (Phase 10)",
    }


# ---------------------------------------------------------------------------
# Receipt 5 — verdict policy (§25.4)
# ---------------------------------------------------------------------------


def verify_verdict_policy() -> dict:
    checks = []
    policy = VerdictPolicy()

    def decide(dimensions=(), defects=()):
        return policy.decide(
            candidate_id="cand_1",
            request_hash="r" * 64,
            shot_id="s1",
            dimensions=tuple(dimensions),
            blocking_defects=tuple(defects),
            reviewed_at=FIXED_CLOCK,
        )

    ok = decide(dimensions=(_dimension(ReviewDimension.MOTION_QUALITY, 0.9),))
    _record(checks, "clean_approve", ok.verdict == CandidateVerdict.APPROVE, ok.verdict.value)

    blocking_wins = decide(
        dimensions=(
            _dimension(ReviewDimension.IDENTITY_CONSISTENCY, 0.95),
            _dimension(ReviewDimension.MOTION_QUALITY, 0.9),
        ),
        defects=[BlockingDefect(
            code=BlockingReasonCode.PROP_MISMATCH,
            dimension=ReviewDimension.PROP_CONSISTENCY,
            message="prop changes hands",
            reviewer_type=ReviewerType.CROSS_SHOT,
            shot_id="s1",
        )],
    )
    _record(checks, "blocking_wins_over_aggregate", blocking_wins.verdict == CandidateVerdict.REJECT
            and blocking_wins.average_score() > 0.9,
            f"verdict={blocking_wins.verdict.value} avg={blocking_wins.average_score():.2f}")

    error = decide(defects=[BlockingDefect(
        code=BlockingReasonCode.REVIEW_ERROR,
        dimension=ReviewDimension.PROMPT_COMPLIANCE,
        message="VLM timeout",
        reviewer_type=ReviewerType.VLM,
    )])
    _record(checks, "review_error_never_pass", error.verdict == CandidateVerdict.REVIEW_ERROR,
            error.verdict.value)

    low = decide(dimensions=(_dimension(ReviewDimension.IDENTITY_CONSISTENCY, 0.95, confidence=0.3),))
    _record(checks, "low_confidence_human", low.verdict == CandidateVerdict.HUMAN_REVIEW_REQUIRED,
            low.verdict.value)

    below = decide(dimensions=(_dimension(ReviewDimension.PROMPT_COMPLIANCE, 0.4),))
    _record(checks, "below_threshold_reject", below.verdict == CandidateVerdict.REJECT,
            below.verdict.value)

    # policy version -> review revision identity (§26)
    old = VerdictPolicy(policy_version="1.0.0").decide(
        candidate_id="cand_1", request_hash="r" * 64, shot_id="s1",
        dimensions=(_dimension(ReviewDimension.PROMPT_COMPLIANCE, 0.65),),
        blocking_defects=(), reviewed_at=FIXED_CLOCK,
    )
    new = VerdictPolicy(policy_version="1.1.0").decide(
        candidate_id="cand_1", request_hash="r" * 64, shot_id="s1",
        dimensions=(_dimension(ReviewDimension.PROMPT_COMPLIANCE, 0.65),),
        blocking_defects=(), reviewed_at=FIXED_CLOCK,
    )
    _record(checks, "policy_change_new_revision", old.review_id != new.review_id
            and old.policy_version == "1.0.0" and new.policy_version == "1.1.0",
            f"{old.review_id} != {new.review_id}")
    _record(checks, "old_result_not_rewritten", old.verdict == CandidateVerdict.REJECT,
            "old review keeps its verdict (immutable)")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "verdict_policy",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "policy_version": policy.policy_version,
    }


# ---------------------------------------------------------------------------
# Receipt 6 — candidate selection (§25.5, gate condition 4)
# ---------------------------------------------------------------------------


def verify_selection() -> dict:
    checks = []
    selector = CandidateSelector()

    blocked = _review("cand_blocked", CandidateVerdict.REJECT, 0.99)
    good = _review("cand_good", CandidateVerdict.APPROVE, 0.8)
    better = _review("cand_better", CandidateVerdict.APPROVE, 0.9)

    record = selector.select(
        run_id="run_1", reviews=[blocked, good, better], policy_version="1.0.0",
        reviewed_at=FIXED_CLOCK,
    )
    _record(checks, "ranks_only_unblocked", "cand_blocked" not in record.ranked
            and record.selected_candidate_id == "cand_better",
            f"ranked={record.ranked}")
    _record(checks, "selected_highest_rank", record.selected_candidate_id == "cand_better",
            record.selected_candidate_id or "none")
    _record(checks, "order_independent", CandidateSelector().select(
        run_id="run_1", reviews=[better, blocked, good], policy_version="1.0.0",
        reviewed_at=FIXED_CLOCK,
    ).ranked == record.ranked, "input order never changes result")
    _record(checks, "traces_policy_algorithm", record.algorithm_version and record.policy_version
            and record.reason, f"alg={record.algorithm_version} policy={record.policy_version}")

    # no approvable candidate
    none_sel = selector.select(
        run_id="run_2", reviews=[_review("cand_x", CandidateVerdict.REJECT, 0.9)],
        policy_version="1.0.0", reviewed_at=FIXED_CLOCK,
    )
    _record(checks, "no_approvable_no_selection", none_sel.selected_candidate_id is None,
            "no auto-select of a rejected candidate")

    # human override audited + wins
    override = HumanSelectionOverride(
        override_id="ovr_1",
        candidate_id="cand_blocked",
        actor="director-1",
        decision=CandidateVerdict.APPROVE,
        reason="acceptable after human review",
        recorded_at=FIXED_CLOCK,
    )
    ovr = selector.select(
        run_id="run_3", reviews=[blocked], human_override=override,
        policy_version="1.0.0", reviewed_at=FIXED_CLOCK,
    )
    _record(checks, "override_wins", ovr.selected_candidate_id == "cand_blocked", "override selected")
    _record(checks, "override_audited", ovr.human_override is not None
            and ovr.human_override.actor == "director-1"
            and ovr.human_override.reason, "actor/reason recorded")

    # retry proposal names defects + fields
    rejected = _review("cand_r", CandidateVerdict.REJECT, 0.4)
    rejected = CandidateReview(
        review_id=rejected.review_id, candidate_id=rejected.candidate_id,
        request_hash=rejected.request_hash, shot_id=rejected.shot_id,
        dimensions=rejected.dimensions,
        blocking_defects=(BlockingDefect(
            code=BlockingReasonCode.BLACK_ENDING,
            dimension=ReviewDimension.TECHNICAL_VALIDITY,
            message="ends black",
            reviewer_type=ReviewerType.DETERMINISTIC,
        ),),
        verdict=rejected.verdict, policy_version=rejected.policy_version,
        reason=rejected.reason,
    )
    retry_rec = selector.select(
        run_id="run_4", reviews=[rejected], policy_version="1.0.0", reviewed_at=FIXED_CLOCK,
    )
    _record(checks, "retry_proposal_present", len(retry_rec.retry_proposals) == 1,
            f"proposals={len(retry_rec.retry_proposals)}")
    proposal = retry_rec.retry_proposals[0]
    _record(checks, "retry_proposal_fields", "generation.duration" in proposal.request_field_changes,
            f"fields={proposal.request_field_changes}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "selection",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "algorithm_version": selector.algorithm_version,
        "sample_selection": record.to_dict(),
    }


# ---------------------------------------------------------------------------
# Receipt 7 — pipeline hierarchy (§24, gate conditions 1/3/5)
# ---------------------------------------------------------------------------


def verify_pipeline() -> dict:
    checks = []

    pipeline = ReviewPipeline(
        deterministic=DeterministicReviewer(),
        vlm=VlmReviewer(),
        cross_shot=CrossShotReviewer(),
        verdict=VerdictPolicy(),
        selector=CandidateSelector(),
    )

    # clean candidate -> APPROVE, all tiers ran
    clean_port = _FakePort(_good_vlm_result())
    clean = pipeline.review_candidate(
        candidate_id="cand_ok",
        request_hash="r" * 64,
        shot_id="s1",
        media_facts=_facts(),
        model_port=clean_port,
        intent_prompt="intent",
        media_uri="file:///tmp/cand_ok.mp4",
    )
    _record(checks, "clean_pipeline_approve", clean.review.verdict == CandidateVerdict.APPROVE,
            clean.review.verdict.value)
    _record(checks, "all_tiers_ran", clean.deterministic is not None and clean.vlm is not None,
            "det + vlm ran on clean candidate")

    # gate condition 1: VLM skipped on decode failure; REJECT not masked
    bad_port = _FakePort(_good_vlm_result())  # would pass everything if called
    bad = pipeline.review_candidate(
        candidate_id="cand_bad",
        request_hash="r" * 64,
        shot_id="s1",
        media_facts=_facts(decoder_ok=False),
        model_port=bad_port,
        intent_prompt="intent",
        media_uri="file:///tmp/cand_bad.mp4",
    )
    _record(checks, "vlm_skipped_on_decode_failure", bad_port.calls == 0 and bad.vlm is None,
            "VLM never invoked")
    _record(checks, "decode_failure_not_masked", bad.review.verdict == CandidateVerdict.REJECT,
            "deterministic blocking defect wins")

    # gate condition 3: VLM error -> REVIEW_ERROR
    err = pipeline.review_candidate(
        candidate_id="cand_err",
        request_hash="r" * 64,
        shot_id="s1",
        media_facts=_facts(),
        model_port=_FakePort(VlmReviewResult(candidate_id="cand_err", content="bad")),
        intent_prompt="intent",
        media_uri="file:///tmp/cand_err.mp4",
    )
    _record(checks, "vlm_error_review_error", err.review.verdict == CandidateVerdict.REVIEW_ERROR,
            err.review.verdict.value)

    # gate condition 5: cross-shot via ledger -> camera flip REJECT
    ledger = _ledger_receipt(
        entries=[
            _entry("s1", outgoing={"camera_side": _state("camera_side", "SIDE_A")}),
            _entry("s2", incoming={"camera_side": _state("camera_side", "SIDE_B")}),
        ],
    )
    flip_port = _FakePort(_good_vlm_result())
    flip = pipeline.review_candidate(
        candidate_id="cand_flip",
        request_hash="r" * 64,
        shot_id="s2",
        media_facts=_facts(),
        model_port=flip_port,
        intent_prompt="intent",
        media_uri="file:///tmp/cand_flip.mp4",
        ledger_receipt=ledger,
    )
    _record(checks, "cross_shot_ran_via_ledger", flip.cross_shot is not None, "cross-shot executed")
    _record(checks, "cross_shot_flip_rejects", flip.review.verdict == CandidateVerdict.REJECT,
            flip.review.verdict.value)

    # pipeline selection
    record = pipeline.select(
        run_id="run_1",
        receipts=[clean, err, bad],
        reviewed_at=FIXED_CLOCK,
    )
    _record(checks, "pipeline_select_clean_only", record.selected_candidate_id == "cand_ok",
            f"selected={record.selected_candidate_id} ranked={record.ranked}")

    all_pass = all(c["ok"] for c in checks)
    return {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "workstream": "pipeline",
        "generated_at": utc_now_iso(),
        "check_count": len(checks),
        "all_checks_pass": all_pass,
        "checks": checks,
        "pipeline_version": pipeline.pipeline_version,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(no_write: bool = False) -> int:
    print("Verifying Phase 20 — Candidate review and quality gates...")
    dc = verify_dimension_catalog()
    dg = verify_deterministic_gate()
    vr = verify_vlm_review()
    cs = verify_cross_shot()
    vp = verify_verdict_policy()
    se = verify_selection()
    pl = verify_pipeline()

    all_workstreams = [dc, dg, vr, cs, vp, se, pl]
    overall_pass = all(w["all_checks_pass"] for w in all_workstreams)
    overall_status = "PASSED" if overall_pass else "FAILED"

    gate_reasons = []
    if not overall_pass:
        for w in all_workstreams:
            if not w["all_checks_pass"]:
                for c in w["checks"]:
                    if not c["ok"]:
                        gate_reasons.append(f"[{w['workstream']}] {c['check']}: {c['detail']}")

    verdict = {
        "gate": "VP20_GENERATION_REVIEW_VERIFIED",
        "status": overall_status,
        "verified_at": utc_now_iso(),
        "workstreams": {
            "dimension_catalog": dc["all_checks_pass"],
            "deterministic_gate": dg["all_checks_pass"],
            "vlm_review": vr["all_checks_pass"],
            "cross_shot": cs["all_checks_pass"],
            "verdict_policy": vp["all_checks_pass"],
            "selection": se["all_checks_pass"],
            "pipeline": pl["all_checks_pass"],
        },
        "blocking_reasons": gate_reasons,
    }

    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)
        write_json(PHASE_DIR / "dimension_catalog_receipt.json", dc)
        write_json(PHASE_DIR / "deterministic_gate_receipt.json", dg)
        write_json(PHASE_DIR / "vlm_review_receipt.json", vr)
        write_json(PHASE_DIR / "cross_shot_receipt.json", cs)
        write_json(PHASE_DIR / "verdict_policy_receipt.json", vp)
        write_json(PHASE_DIR / "selection_receipt.json", se)
        write_json(PHASE_DIR / "pipeline_receipt.json", pl)
        write_json(PHASE_DIR / "phase_verdict.json", verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, dc, dg, vr, cs, vp, se, pl),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_20 artifacts untouched.")

    print(f"Phase 20 verdict: {overall_status}")
    print(f"  dimension catalog: {'PASS' if dc['all_checks_pass'] else 'FAIL'}")
    print(f"  deterministic gate: {'PASS' if dg['all_checks_pass'] else 'FAIL'}")
    print(f"  vlm review: {'PASS' if vr['all_checks_pass'] else 'FAIL'}")
    print(f"  cross-shot: {'PASS' if cs['all_checks_pass'] else 'FAIL'}")
    print(f"  verdict policy: {'PASS' if vp['all_checks_pass'] else 'FAIL'}")
    print(f"  selection: {'PASS' if se['all_checks_pass'] else 'FAIL'}")
    print(f"  pipeline: {'PASS' if pl['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, dc, dg, vr, cs, vp, se, pl) -> str:
    return f"""# Phase 20 Report — Candidate Review & Quality Gates

- **Gate:** `VP20_GENERATION_REVIEW_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Dimension Catalog

- Contract: `docs/video_production/generation_review/dimension_catalog_contract.md`
- 11 canonical dimensions, versioned policy, blocking rule set.
- Checks: {dc.get('check_count')}; all pass: {dc.get('all_checks_pass')}

## Deterministic Gate

- Contract: `docs/video_production/generation_review/deterministic_gate_contract.md`
- Media/file/safety fail-closed; typed reason codes; VLM gated (condition 1).
- Checks: {dg.get('check_count')}; all pass: {dg.get('all_checks_pass')}

## VLM Review

- Contract: `docs/video_production/generation_review/vlm_review_contract.md`
- Timeout / invalid JSON / schema violation -> REVIEW_ERROR, never PASS (cond. 3).
- Checks: {vr.get('check_count')}; all pass: {vr.get('all_checks_pass')}

## Cross-shot Continuity

- Contract: `docs/video_production/generation_review/cross_shot_continuity_contract.md`
- Ledger-based predecessor/successor comparison, typed defects (cond. 5).
- Checks: {cs.get('check_count')}; all pass: {cs.get('all_checks_pass')}

## Verdict Policy

- Contract: `docs/video_production/generation_review/verdict_selection_contract.md`
- Blocking defect always wins; low confidence -> human; error never PASS.
- Checks: {vp.get('check_count')}; all pass: {vp.get('all_checks_pass')}

## Candidate Selection

- Contract: `docs/video_production/generation_review/verdict_selection_contract.md`
- Rank unblocked only, order-independent, human override audited (cond. 4).
- Checks: {se.get('check_count')}; all pass: {se.get('all_checks_pass')}

## Pipeline

- Hierarchy §24: deterministic -> VLM (gated) -> cross-shot (ledger) ->
  verdict -> selection; deterministic failures never masked.
- Checks: {pl.get('check_count')}; all pass: {pl.get('all_checks_pass')}

## Evidence

- `dimension_catalog_receipt.json`
- `deterministic_gate_receipt.json`
- `vlm_review_receipt.json`
- `cross_shot_receipt.json`
- `verdict_policy_receipt.json`
- `selection_receipt.json`
- `pipeline_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
