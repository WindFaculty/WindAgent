"""Plan B B7 contract tests over the committed review/revision fixtures.

Every committed fixture must match live behavior: the prompt catalog entries
(``story.review.assess`` + ``story.revise.rewrite``), the golden review loop
(clean PASS, weak PASS_WITH_WARNINGS, bounded revision with diff), the
invalid-output corpora results re-run through the real services, and the
handler/task-type surface. This is the fixture-side half of STORY_REVIEW_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.verification.produce_b7_evidence import (
    REVIEW_CORPUS,
    REVISE_CORPUS,
    golden_review_loop,
    run_review_corpus,
    run_revise_corpus,
)

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.review import (
    ReviewReport,
    RevisionProposal,
    StoryDiff,
    validate_review_report,
    validate_revision_proposal,
    validate_story_diff,
)
from windagent_intelligence.story import (
    HANDLER_REGISTRY,
    registered_story_task_types,
)
from windagent_intelligence.story.prompts import (
    prompt_for,
    prompt_manifest,
    validate_registry_invariants,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_review"
)
PROMPTS_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_prompts"
)


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load(name: str):
    return json.loads((REVIEW_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt catalog entries
# ---------------------------------------------------------------------------


def test_review_prompts_registered_non_legacy_schema_first():
    review = prompt_for("story.review.assess")
    assert review.version == "1.1.0"
    assert review.legacy is False
    assert review.output_format == "json"
    assert review.output_schema["title"] == "ReviewOutput"
    assert "narrative_score" in review.output_schema["properties"]

    revise = prompt_for("story.revise.rewrite")
    assert revise.version == "1.1.0"
    assert revise.legacy is False
    assert revise.output_format == "json"
    assert revise.output_schema["title"] == "ScreenplayRevisionOutput"
    assert revise.output_schema["properties"]["scenes"]["minItems"] == 3
    assert validate_registry_invariants() == []


def test_review_prompts_in_committed_manifest():
    committed = json.loads((PROMPTS_DIR / "prompt_manifest.json").read_text(encoding="utf-8"))
    live = json.loads(_canonical_bytes(prompt_manifest()))
    assert committed == live
    for prompt_id, schema_name in (
        ("story.review.assess", "ReviewOutput.json"),
        ("story.revise.rewrite", "ScreenplayRevisionOutput.json"),
    ):
        row = committed["entries"][prompt_id]
        assert row["legacy"] is False
        assert row["output_schema_ref"] == f"schemas/{schema_name}"
        assert (PROMPTS_DIR / "schemas" / schema_name).exists()
        assert row["content_hash"] == prompt_for(prompt_id).content_hash


def test_manifest_checksum_matches_committed_file():
    checksums = load("checksums.json")
    raw = (PROMPTS_DIR / "prompt_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["prompt_manifest"]


# ---------------------------------------------------------------------------
# Golden review loop
# ---------------------------------------------------------------------------


def test_golden_loop_matches_live_generation():
    committed = load("review_loop_golden.json")
    live = golden_review_loop()
    assert committed == live
    assert committed["clean_verdict"] == "PASS"
    assert committed["weak_verdict"] == "PASS_WITH_WARNINGS"
    assert committed["revision_proposal"]["iteration_number"] == 2
    assert committed["revised_draft"]["draft_id"] == "draft_rabbit_kite_r2"
    assert committed["review_model_provenance"]["prompt_id"] == "story.review.assess"
    assert committed["revise_provenance"]["prompt_id"] == "story.revise.rewrite"


def test_golden_artifacts_self_consistent():
    committed = load("review_loop_golden.json")
    clean = ReviewReport(**committed["clean_review"])
    weak = ReviewReport(**committed["weak_review"])
    assert validate_review_report(clean).is_pass()
    assert validate_review_report(weak).is_pass()
    assert clean.verdict == "PASS" and weak.verdict == "PASS_WITH_WARNINGS"
    assert weak.blocking_findings == []

    proposal = RevisionProposal(**committed["revision_proposal"])
    assert validate_revision_proposal(proposal, weak).is_pass()
    assert proposal.draft_id == weak.draft_id
    assert proposal.review_report_id == weak.report_id

    diff = StoryDiff(**committed["story_diff"])
    assert validate_story_diff(diff).is_pass()
    assert diff.from_draft_id == committed["clean_review"]["draft_id"]
    assert diff.to_draft_id == committed["revised_draft"]["draft_id"]
    assert diff.summary["MODIFIED"] >= 1

    # A clean review of the revised draft converges: no findings -> PASS.
    assert clean.finding_count == 0


def test_golden_loop_converges_or_stops_deterministically():
    committed = load("review_loop_golden.json")
    # Iteration budget: proposal 2/3 -> one more revision allowed, then stop.
    assert committed["revision_proposal"]["iteration_number"] < committed["revision_proposal"]["maximum_iterations"]


# ---------------------------------------------------------------------------
# Invalid-output corpora
# ---------------------------------------------------------------------------


def test_corpus_results_match_live_behavior():
    committed = load("invalid_output_corpus_results.json")
    assert committed["review"] == run_review_corpus()
    assert committed["revise"] == run_revise_corpus()


def test_every_review_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["review"]["results"]}
    for case in REVIEW_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
            assert row["report_verdict"] == case["report_verdict"], case["case"]
            assert set(row["finding_codes"]) == set(case.get("finding_codes", [])), case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_every_revise_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["revise"]["results"]}
    for case in REVISE_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
            if "diff_summary" in case:
                assert row["diff_summary"] == case["diff_summary"], case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_corpus_checksums_match_committed():
    checksums = load("checksums.json")
    assert hashlib.sha256(_canonical_bytes(REVIEW_CORPUS)).hexdigest() == checksums["review_corpus"]
    assert hashlib.sha256(_canonical_bytes(REVISE_CORPUS)).hexdigest() == checksums["revise_corpus"]
    combined = {"review": run_review_corpus(), "revise": run_revise_corpus()}
    assert hashlib.sha256(_canonical_bytes(combined)).hexdigest() == checksums["results"]


# ---------------------------------------------------------------------------
# Handler surface + approval boundary
# ---------------------------------------------------------------------------


def test_handlers_match_frozen_task_types():
    assert set(registered_story_task_types()) == {
        StudioTaskType.IDEA_GENERATE.value,
        StudioTaskType.IDEA_EVALUATE.value,
        StudioTaskType.BIBLE_GENERATE.value,
        StudioTaskType.BEATS_GENERATE.value,
        StudioTaskType.OUTLINE_GENERATE.value,
        StudioTaskType.SCREENPLAY_GENERATE.value,
        StudioTaskType.REVIEW.value,
        StudioTaskType.REVISE.value,
        StudioTaskType.LOCK.value,
    }
    assert set(HANDLER_REGISTRY) == {
        StudioTaskType.IDEA_GENERATE,
        StudioTaskType.IDEA_EVALUATE,
        StudioTaskType.BIBLE_GENERATE,
        StudioTaskType.BEATS_GENERATE,
        StudioTaskType.OUTLINE_GENERATE,
        StudioTaskType.SCREENPLAY_GENERATE,
        StudioTaskType.REVIEW,
        StudioTaskType.REVISE,
        StudioTaskType.LOCK,
    }


def test_review_handlers_import_no_infrastructure():
    import inspect

    from windagent_intelligence.story import runtime_handlers as module

    source = inspect.getsource(module.review)
    for forbidden in ("sqlalchemy", "storage", "queue", "WorkflowEngine", "alembic"):
        assert forbidden not in source, f"review handlers leak {forbidden}"
    assert "StoryModelBoundary" in source
    assert "FixtureModelPort" not in source


def test_review_handler_roundtrip_via_fixture_port():
    import asyncio

    from scripts.verification.produce_b7_evidence import GOLDEN_REVIEW_CLEAN
    from windagent_core.domain.story.screenplay import ScreenplayDraft
    from windagent_intelligence.story import ReviewHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    draft = ScreenplayDraft(**load("review_loop_golden.json")["revised_draft"])
    port = FixtureModelPort(responses={"review": json.dumps(GOLDEN_REVIEW_CLEAN, ensure_ascii=False)})
    handler = ReviewHandler(port)
    result = asyncio.run(handler.handle(draft))
    assert result.report.verdict == "PASS"
    assert handler.task_type == StudioTaskType.REVIEW


def test_revise_handler_roundtrip_via_fixture_port():
    import asyncio

    from scripts.verification.produce_b6_evidence import GOLDEN_SCREENPLAY_DRAFT
    from scripts.verification.produce_b7_evidence import GOLDEN_REVISION_RESPONSE, _weak_report
    from windagent_core.domain.story.ids import ScreenplayDraftId
    from windagent_core.domain.story.screenplay import ScreenplayDraft
    from windagent_intelligence.story import ReviseHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    draft = ScreenplayDraft(**GOLDEN_SCREENPLAY_DRAFT)
    port = FixtureModelPort(responses={"revise": json.dumps(GOLDEN_REVISION_RESPONSE, ensure_ascii=False)})
    handler = ReviseHandler(port)
    result = asyncio.run(handler.handle(draft, _weak_report()))
    assert result.proposal.draft_id == draft.draft_id
    assert result.diff.from_draft_id == draft.draft_id
    assert result.diff.to_draft_id == ScreenplayDraftId("draft_rabbit_kite_r2")
    assert handler.task_type == StudioTaskType.REVISE
