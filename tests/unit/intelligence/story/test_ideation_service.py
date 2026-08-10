"""B3 services: generation via StoryModelBoundary + deterministic evaluation."""

from __future__ import annotations

import json

import pytest

from windagent_core.domain.story.ideation import (
    SELECTION_POLICY_AUTO,
    SELECTION_POLICY_HUMAN_REQUIRED,
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
    SCORE_RUBRIC_VERSION,
)
from windagent_core.domain.story.ids import CreativeBriefId
from windagent_intelligence.story.ideation.service import (
    IdeaEvaluationService,
    IdeaGenerationService,
    IdeaValidationFailure,
)
from windagent_intelligence.story.prompts import (
    FixtureModelPort,
    StoryModelBoundary,
    StorySchemaFailure,
)


def _brief(**overrides) -> CreativeBrief:
    data = dict(
        brief_id=CreativeBriefId("br_1"),
        title="Con thỏ và cánh diều",
        audience="5-8",
        language="vi",
        target_duration_seconds=240,
        prohibited_content=["bạo lực"],
    )
    data.update(overrides)
    return CreativeBrief(**data)


def _candidate(cid: str, title: str, **overrides) -> dict:
    base = dict(
        candidate_id=cid,
        title=title,
        summary="Tóm tắt " + title,
        premise="Tiền đề " + title,
        logline="Logline " + title,
        themes=["tình bạn"],
        age_fit=0.9,
        estimated_seconds=240,
        scene_count=5,
        character_count=2,
        location_count=2,
        safety_ok=True,
    )
    base.update(overrides)
    return base


def _response(*candidates) -> str:
    return json.dumps({"language": "vi", "candidates": list(candidates)}, ensure_ascii=False)


def _service(response: str, **port_kwargs) -> IdeaGenerationService:
    port = FixtureModelPort(responses={"ideation": response}, **port_kwargs)
    return IdeaGenerationService(StoryModelBoundary(port))


def _run(coro):
    import asyncio

    return asyncio.run(coro())


def test_generate_valid_set_normalizes_brief():
    service = _service(
        _response(
            _candidate("c1", "A"),
            _candidate("c2", "B"),
            _candidate("c3", "C"),
            _candidate("c4", "D"),
        )
    )

    async def go():
        return await service.generate(_brief())

    result = _run(go)
    assert result.candidate_set.candidate_count == 4
    assert result.candidate_set.distinct_ids
    assert result.candidate_set.evaluated is False
    assert (result.brief.audience_min_age, result.brief.audience_max_age) == (5, 8)
    assert "khủng bố" in result.brief.prohibited_content  # band default merged
    assert result.provenance.prompt_id == "story.ideation.generate"
    assert result.provenance.repair_count == 0
    assert result.provenance.provider == "fixture"


def test_generate_accepts_3_and_5_boundaries():
    for count in (3, 5):
        service = _service(_response(*[_candidate(f"c{i}", f"T{i}") for i in range(count)]))
        result = _run(lambda: service.generate(_brief()))
        assert result.candidate_set.candidate_count == count


def test_generate_rejects_too_few_candidates():
    service = _service(_response(_candidate("c1", "A"), _candidate("c2", "B")))
    with pytest.raises(StorySchemaFailure):
        _run(lambda: service.generate(_brief()))


def test_generate_rejects_duplicate_ids_as_typed_failure():
    service = _service(_response(_candidate("same", "A"), _candidate("same", "B"), _candidate("c3", "C")))
    with pytest.raises(IdeaValidationFailure) as exc:
        _run(lambda: service.generate(_brief()))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "IDEA_DUPLICATE" in codes


def test_generate_rejects_unsafe_candidate():
    service = _service(
        _response(
            _candidate("c1", "A", safety_ok=False),
            _candidate("c2", "B"),
            _candidate("c3", "C"),
        )
    )
    with pytest.raises(IdeaValidationFailure) as exc:
        _run(lambda: service.generate(_brief()))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "SAFETY_PROHIBITED" in codes


def test_generate_rejects_prohibited_term_in_output():
    service = _service(
        _response(
            _candidate("c1", "A", summary="một trận bạo lực trong rừng"),
            _candidate("c2", "B"),
            _candidate("c3", "C"),
        )
    )
    with pytest.raises(IdeaValidationFailure):
        _run(lambda: service.generate(_brief()))


def test_generate_rejects_blank_brief_title():
    service = _service(_response(_candidate("c1", "A"), _candidate("c2", "B"), _candidate("c3", "C")))
    with pytest.raises(IdeaValidationFailure):
        _run(lambda: service.generate(_brief(title="  ")))


def test_generate_idempotent_same_inputs():
    first = _run(lambda: _service(_response(_candidate("c1", "A"), _candidate("c2", "B"), _candidate("c3", "C"))).generate(_brief()))
    second = _run(lambda: _service(_response(_candidate("c1", "A"), _candidate("c2", "B"), _candidate("c3", "C"))).generate(_brief()))
    assert first.candidate_set == second.candidate_set
    assert first.candidate_set.content_hash() == second.candidate_set.content_hash()


def test_generate_fenced_json_repaired_once():
    fenced = "```json\n" + _response(_candidate("c1", "A"), _candidate("c2", "B"), _candidate("c3", "C")) + "\n```"
    result = _run(lambda: _service(fenced).generate(_brief()))
    assert result.candidate_set.candidate_count == 3
    assert result.provenance.repair_count == 1


def test_generate_propagates_boundary_safety_failure():
    service = _service("x" * 20_000)  # exceeds max_output_chars 12_000
    with pytest.raises(Exception) as exc:
        _run(lambda: service.generate(_brief()))
    assert exc.value.__class__.__name__ == "StorySafetyFailure"


def test_generate_refusing_fixture_fails_closed():
    service = _service("", reject=True)
    with pytest.raises(Exception) as exc:
        _run(lambda: service.generate(_brief()))
    assert exc.value.__class__.__name__ == "StoryProviderTransientError"


def test_target_count_out_of_bounds_rejected():
    service = _service(_response(_candidate("c1", "A"), _candidate("c2", "B"), _candidate("c3", "C")))
    with pytest.raises(IdeaValidationFailure):
        _run(lambda: service.generate(_brief(), target_count=6))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _set(**overrides) -> IdeaCandidateSet:
    data = dict(
        candidates=[
            IdeaCandidate(candidate_id="c1", title="T1", age_fit=0.9, safety_ok=True, content={"estimated_seconds": 240}),
            IdeaCandidate(candidate_id="c2", title="T2", age_fit=0.8, safety_ok=True, content={"estimated_seconds": 400}),
            IdeaCandidate(candidate_id="c3", title="T3", age_fit=0.7, safety_ok=True, content={"estimated_seconds": 100}),
        ]
    )
    data.update(overrides)
    return IdeaCandidateSet(**data)


def test_evaluate_scores_deterministically():
    result = IdeaEvaluationService().evaluate(_brief(), _set())
    assert result.candidate_set.evaluated is True
    assert result.candidate_set.scoring_rubric_version == SCORE_RUBRIC_VERSION
    assert result.recommendation == result.candidate_set.recommended_candidate_id
    for candidate in result.candidate_set.candidates:
        assert candidate.score is not None and 0.0 <= candidate.score <= 1.0
        assert "SAFETY" in candidate.score_dimensions


def test_evaluate_auto_policy_allows_selection():
    result = IdeaEvaluationService(selection_policy=SELECTION_POLICY_AUTO).evaluate(_brief(), _set())
    assert result.auto_selection_allowed is True
    assert result.recommendation is not None


def test_evaluate_human_required_never_auto_selects():
    result = IdeaEvaluationService(selection_policy=SELECTION_POLICY_HUMAN_REQUIRED).evaluate(_brief(), _set())
    assert result.recommendation is not None  # recommendation still produced
    assert result.auto_selection_allowed is False


def test_evaluate_unknown_policy_rejected_at_construction():
    with pytest.raises(ValueError):
        IdeaEvaluationService(selection_policy="SILENT_SELECT")


def test_evaluate_rejects_invalid_set():
    from windagent_intelligence.story.ideation.service import IdeaValidationFailure

    unsafe = _set()
    unsafe = unsafe.model_copy(
        update={
            "candidates": [
                c.model_copy(update={"safety_ok": False}) if c.candidate_id == "c2" else c
                for c in unsafe.candidates
            ]
        }
    )
    with pytest.raises(IdeaValidationFailure):
        IdeaEvaluationService().evaluate(_brief(), unsafe)


def test_evaluate_model_assisted_values_change_score():
    brief = _brief()
    base = IdeaEvaluationService().evaluate(brief, _set())
    assisted = IdeaEvaluationService().evaluate(
        brief,
        _set(),
        model_values={"c1": {"EMOTIONAL_ARC": 0.1, "ORIGINALITY": 0.1}},
    )
    c1_base = next(c for c in base.candidate_set.candidates if c.candidate_id == "c1")
    c1_assisted = next(c for c in assisted.candidate_set.candidates if c.candidate_id == "c1")
    assert c1_assisted.score_dimensions["EMOTIONAL_ARC"] != c1_base.score_dimensions["EMOTIONAL_ARC"]
    assert c1_assisted.score != c1_base.score


def test_evaluate_does_not_mutate_input():
    candidate_set = _set()
    before = candidate_set.content_hash()
    IdeaEvaluationService().evaluate(_brief(), candidate_set)
    assert candidate_set.content_hash() == before
    assert candidate_set.evaluated is False
