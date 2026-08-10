"""B3 domain: brief normalization, selection policy, policy vocab."""

from __future__ import annotations

from windagent_core.domain.story.ideation import (
    AGE_BAND_DEFAULT_PROHIBITED,
    DEFAULT_LANGUAGE,
    SELECTION_POLICIES,
    SELECTION_POLICY_AUTO,
    SELECTION_POLICY_HUMAN_REQUIRED,
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
    SelectedIdea,
    normalize_creative_brief,
    parse_audience_band,
    selection_allowed,
    validate_selected_idea,
)
from windagent_core.domain.story.ids import CreativeBriefId, SelectedIdeaId
from windagent_core.domain.story.validation import ValidationSeverity


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


def test_parse_audience_band():
    assert parse_audience_band("5-8") == (5, 8)
    assert parse_audience_band(" 5 - 8 ") == (5, 8)
    assert parse_audience_band("0-99") == (0, 99)
    assert parse_audience_band("") is None
    assert parse_audience_band("thiếu nhi") is None
    assert parse_audience_band("8-5") is None  # inverted band rejected


def test_normalize_parses_audience_band_and_merges_prohibited():
    brief = _brief()
    normalized = normalize_creative_brief(brief)
    assert (normalized.audience_min_age, normalized.audience_max_age) == (5, 8)
    # age-band defaults (0-8) UNION explicit list, deduped, order-preserving
    assert normalized.prohibited_content == ["bạo lực", "khủng bố", "sợ hãi"]
    assert normalized.language == "vi"
    assert normalized is not brief  # immutable normalization
    assert brief.audience_min_age == 0  # input never mutated


def test_normalize_explicit_args_win():
    brief = _brief(audience="9-13")
    normalized = normalize_creative_brief(
        brief,
        language="en",
        theme="dũng cảm",
        audience_band="5-8",
        prohibited_content=["kỳ thị"],
        constraints=["bối cảnh làng quê"],
    )
    assert normalized.language == "en"
    assert normalized.theme == "dũng cảm"
    assert (normalized.audience_min_age, normalized.audience_max_age) == (5, 8)
    assert "kỳ thị" in normalized.prohibited_content
    assert "khủng bố" in normalized.prohibited_content  # band default merged
    assert normalized.constraints == ["bối cảnh làng quê"]


def test_normalize_keeps_existing_ages_when_band_unparseable():
    brief = _brief(audience="mọi lứa tuổi", audience_min_age=3, audience_max_age=10)
    normalized = normalize_creative_brief(brief)
    assert (normalized.audience_min_age, normalized.audience_max_age) == (3, 10)
    assert normalized.audience == "mọi lứa tuổi"
    # straddling band (3-10) resolves to the strictest containing band (9-13)
    assert "khủng bố" in normalized.prohibited_content
    assert "bạo lực tả thực" in normalized.prohibited_content


def test_normalize_metadata_report_recorded():
    normalized = normalize_creative_brief(_brief())
    report = normalized.production_constraints["normalization_report"]
    assert report["normalization_version"] == "brief_normalization/v1"
    assert report["audience_band_parsed"] == "5-8"
    assert report["prohibited_from_age_band"] == AGE_BAND_DEFAULT_PROHIBITED["0-8"]


def test_default_language_constant():
    assert DEFAULT_LANGUAGE == "vi"


def _set(**set_overrides) -> IdeaCandidateSet:
    data = dict(
        candidates=[
            IdeaCandidate(candidate_id="c1", title="T1", safety_ok=True, age_fit=0.9),
            IdeaCandidate(candidate_id="c2", title="T2", safety_ok=True, age_fit=0.8),
            IdeaCandidate(candidate_id="c3", title="T3", safety_ok=True, age_fit=0.7),
        ]
    )
    data.update(set_overrides)
    return IdeaCandidateSet(**data)


def test_auto_policy_allows_only_evaluated_safe_set():
    assert selection_allowed(SELECTION_POLICY_AUTO, _set(evaluated=True, recommended_candidate_id="c1")) is True
    # unevaluated -> fail closed
    assert selection_allowed(SELECTION_POLICY_AUTO, _set()) is False
    # no recommendation -> fail closed
    assert selection_allowed(SELECTION_POLICY_AUTO, _set(evaluated=True)) is False
    # unsafe candidate -> fail closed
    unsafe = _set(evaluated=True, recommended_candidate_id="c1")
    unsafe = unsafe.model_copy(update={"candidates": [c.model_copy(update={"safety_ok": False}) if c.candidate_id == "c2" else c for c in unsafe.candidates]})
    assert selection_allowed(SELECTION_POLICY_AUTO, unsafe) is False


def test_human_required_never_auto_selects():
    scored = _set(evaluated=True, recommended_candidate_id="c1")
    assert selection_allowed(SELECTION_POLICY_HUMAN_REQUIRED, scored) is False


def test_unknown_policy_fails_closed():
    scored = _set(evaluated=True, recommended_candidate_id="c1")
    assert selection_allowed("UNKNOWN_POLICY", scored) is False


def test_selection_policy_vocabulary_frozen():
    assert SELECTION_POLICIES == (SELECTION_POLICY_AUTO, SELECTION_POLICY_HUMAN_REQUIRED)
    assert SELECTION_POLICY_AUTO == "AUTO_WHEN_POLICY_ALLOWS"
    assert SELECTION_POLICY_HUMAN_REQUIRED == "HUMAN_REQUIRED"


def test_selected_idea_rejects_unknown_policy():
    selected = SelectedIdea(
        selected_idea_id=SelectedIdeaId.generate("sel"),
        source_set_id="set_1",
        candidate_id="c1",
        title="T1",
        selection_policy="SILENT_SELECT",
    )
    report = validate_selected_idea(selected, _set())
    assert not report.is_pass()
    blocking = [i for i in report.issues if i.severity == ValidationSeverity.BLOCKING]
    assert any(i.code == "POLICY_UNKNOWN" for i in blocking)


def test_selected_idea_accepts_frozen_policies():
    for policy in SELECTION_POLICIES:
        selected = SelectedIdea(
            selected_idea_id=SelectedIdeaId.generate("sel"),
            source_set_id="set_1",
            candidate_id="c1",
            title="T1",
            selection_policy=policy,
            rationale="rubric",
        )
        assert validate_selected_idea(selected, _set()).is_pass()
