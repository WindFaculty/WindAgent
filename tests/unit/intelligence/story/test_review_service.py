"""Plan B B7 unit tests: ReviewService + ReviseService (loop semantics)."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.verification.produce_b6_evidence import (
    GOLDEN_CANON,
    GOLDEN_SCREENPLAY_DRAFT,
    GOLDEN_WORLD,
)
from scripts.verification.produce_b7_evidence import (
    GOLDEN_BEATS,
    GOLDEN_DRAFT,
    GOLDEN_OUTLINE,
    GOLDEN_REVISION_RESPONSE,
    GOLDEN_REVIEW_CLEAN,
    GOLDEN_REVIEW_WEAK,
)

from windagent_core.domain.story.review import ReviewFinding, ReviewReport
from windagent_core.domain.story.validation import ValidationSeverity
from windagent_intelligence.story.prompts import (
    FixtureModelPort,
    StoryModelBoundary,
)
from windagent_intelligence.story.prompts.structured import (
    StoryEmptyResponseError,
    StorySchemaFailure,
)
from windagent_intelligence.story.review.service import (
    ReviewService,
    ReviseService,
    ReviseValidationFailure,
)


def _run(coro):
    return asyncio.run(coro)


def _review_service(response: str) -> ReviewService:
    return ReviewService(StoryModelBoundary(FixtureModelPort(responses={"review": response})))


def _revise_service(response: str) -> ReviseService:
    return ReviseService(StoryModelBoundary(FixtureModelPort(responses={"revise": response})))


def _clean_response() -> str:
    return json.dumps(GOLDEN_REVIEW_CLEAN, ensure_ascii=False)


def _weak_response() -> str:
    return json.dumps(GOLDEN_REVIEW_WEAK, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Review happy path + verdicts
# ---------------------------------------------------------------------------


def test_review_clean_verdict_pass():
    result = _run(_review_service(_clean_response()).generate(GOLDEN_DRAFT))
    assert result.report.verdict == "PASS"
    assert result.report.finding_count == 0
    assert result.model_provenance.prompt_id == "story.review.assess"
    assert result.validation["pass"] is True


def test_review_weak_score_creates_warning_finding():
    result = _run(_review_service(_weak_response()).generate(GOLDEN_DRAFT))
    assert result.report.verdict == "PASS_WITH_WARNINGS"
    assert result.report.blocking_findings == []
    codes = {f.code for f in result.report.findings}
    assert codes == {"MODEL_DIMENSION_SCORE"}
    finding = result.report.findings[0]
    assert finding.source == "model" and finding.dimension == "age_fit"
    age_fit = next(d for d in result.report.dimensions if d.dimension == "age_fit")
    assert age_fit.score == 0.4


def test_review_blocking_deterministic_finding_requires_review():
    from windagent_core.domain.story.screenplay import ScreenplayDraft

    bad = json.loads(json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False))
    bad["scenes"][0]["action_description"] = ""
    bad["scenes"][0]["dialogue"] = []
    bad["scenes"][0]["narration"] = ""
    flawed = ScreenplayDraft(**bad)
    result = _run(_review_service(_clean_response()).generate(
        flawed, outline=GOLDEN_OUTLINE, beat_sheet=GOLDEN_BEATS,
        canon=GOLDEN_CANON, world=GOLDEN_WORLD,
    ))
    assert result.report.verdict == "REVIEW_REQUIRED"
    assert {f.code for f in result.report.findings} == {"FIELD_EMPTY"}
    assert result.report.findings[0].source == "deterministic"
    assert result.report.findings[0].dimension == "format"
    format_dim = next(d for d in result.report.dimensions if d.dimension == "format")
    assert format_dim.score == 0.0


def test_review_empty_response_is_transient():
    with pytest.raises(StoryEmptyResponseError):
        _run(_review_service("").generate(GOLDEN_DRAFT))


def test_review_not_json_fails_schema():
    with pytest.raises(StorySchemaFailure):
        _run(_review_service("prose").generate(GOLDEN_DRAFT))


def test_review_fenced_json_repaired_once():
    response = "```json\n" + _clean_response() + "\n```"
    result = _run(_review_service(response).generate(GOLDEN_DRAFT))
    assert result.model_provenance.repair_count == 1
    assert result.report.verdict == "PASS"


# ---------------------------------------------------------------------------
# Revise: bounded loop semantics
# ---------------------------------------------------------------------------


def test_revise_happy_path_new_immutable_draft():
    result = _run(_revise_service(json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False)).generate(
        GOLDEN_DRAFT, _weak_report(),
        outline=GOLDEN_OUTLINE, beat_sheet=GOLDEN_BEATS, canon=GOLDEN_CANON, world=GOLDEN_WORLD,
    ))
    assert result.new_draft.draft_id != GOLDEN_DRAFT.draft_id
    assert result.proposal.draft_id == GOLDEN_DRAFT.draft_id
    assert result.proposal.review_report_id == _weak_report().report_id
    assert result.proposal.iteration_number == 2
    assert not result.diff.is_empty
    assert result.diff.summary["MODIFIED"] == 2
    assert result.provenance.prompt_id == "story.revise.rewrite"


def test_revise_refuses_clean_report():
    clean = _run(_review_service(_clean_response()).generate(GOLDEN_DRAFT)).report
    port = FixtureModelPort(responses={"revise": json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False)})
    service = ReviseService(StoryModelBoundary(port))
    with pytest.raises(ReviseValidationFailure):
        _run(service.generate(GOLDEN_DRAFT, clean))
    assert port.requests == []  # never called the provider


def test_revise_refuses_same_draft_id():
    with pytest.raises(ReviseValidationFailure) as exc:
        _run(_revise_service(json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False)).generate(GOLDEN_DRAFT, _weak_report()))
    assert "immutable" in str(exc.value)


def test_revise_refuses_empty_change():
    identical = json.loads(json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False))
    identical["draft_id"] = "draft_identical"
    with pytest.raises(ReviseValidationFailure) as exc:
        _run(_revise_service(json.dumps(identical, ensure_ascii=False)).generate(GOLDEN_DRAFT, _weak_report()))
    assert "no structural change" in str(exc.value)


def test_revise_refuses_domain_invalid_new_draft():
    bad = json.loads(json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False))
    bad["scenes"][0]["source_beat_ids"] = []
    with pytest.raises(ReviseValidationFailure):
        _run(_revise_service(json.dumps(bad, ensure_ascii=False)).generate(
            GOLDEN_DRAFT, _weak_report(),
            outline=GOLDEN_OUTLINE, beat_sheet=GOLDEN_BEATS, canon=GOLDEN_CANON, world=GOLDEN_WORLD,
        ))


def test_revise_stops_when_budget_exhausted():
    exhausted = ReviewReport(
        **{**_weak_report().to_canonical_dict(), "review_iteration": 3, "maximum_iterations": 3}
    )
    port = FixtureModelPort(responses={"revise": json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False)})
    service = ReviseService(StoryModelBoundary(port))
    with pytest.raises(ReviseValidationFailure) as exc:
        _run(service.generate(GOLDEN_DRAFT, exhausted))
    assert "budget exhausted" in str(exc.value)
    assert port.requests == []  # loop stops BEFORE another provider call


def test_revise_old_draft_never_mutated():
    before = GOLDEN_DRAFT.content_hash()
    _run(_revise_service(json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False)).generate(GOLDEN_DRAFT, _weak_report()))
    assert GOLDEN_DRAFT.content_hash() == before


# ---------------------------------------------------------------------------
# Stale proposal binding
# ---------------------------------------------------------------------------


def test_revise_rejects_report_for_different_draft():
    other = ReviewReport(
        **{**_weak_report().to_canonical_dict(), "draft_id": "draft_other"}
    )
    with pytest.raises(ReviseValidationFailure):
        _run(_revise_service(json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False)).generate(GOLDEN_DRAFT, other))


def _weak_report() -> ReviewReport:
    return ReviewReport(
        report_id="report_rabbit_kite",
        draft_id=GOLDEN_DRAFT.draft_id,
        review_iteration=1,
        findings=[
            ReviewFinding(
                code="MODEL_DIMENSION_SCORE",
                severity=ValidationSeverity.WARNING,
                location="dimensions/age_fit",
                evidence="age_fit score 0.4 below threshold 0.5",
                source="model",
                dimension="age_fit",
            )
        ],
        verdict="PASS_WITH_WARNINGS",
        quality_summary="1 finding (0 blocking, 1 warnings).",
        maximum_iterations=3,
    )
