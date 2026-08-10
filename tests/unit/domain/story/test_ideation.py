"""B1 ideation: scoring math, ties, age/safety, adapters, selection binding."""

from __future__ import annotations

from windagent_core.domain.story.ideation import (
    SCORE_DIMENSION_WEIGHTS,
    SCORE_RUBRIC_VERSION,
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
    SelectedIdea,
    from_video_brief,
    score_candidate_set,
    tie_break_candidates,
    validate_creative_brief,
    validate_idea_candidate_set,
    validate_selected_idea,
)
from windagent_core.domain.story.ids import CreativeBriefId, SelectedIdeaId
from windagent_core.domain.story.validation import ValidationSeverity
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief as VideoCreativeBrief,
)
from windagent_core.domain.video_production.ids import CreativeBriefId as VideoBriefId


def _brief() -> CreativeBrief:
    return CreativeBrief(
        brief_id=CreativeBriefId("br_1"),
        title="Con thỏ và cánh diều",
        audience="5-8",
        audience_min_age=5,
        audience_max_age=8,
        language="vi",
        target_duration_seconds=240,
        prohibited_content=["bạo lực", "khủng bố"],
    )


def _set() -> IdeaCandidateSet:
    return IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="c1", title="Chú thỏ và cánh diều giấy", logline="A" * 100),
        IdeaCandidate(candidate_id="c2", title="Cánh diều bay qua sông", logline="B" * 100),
        IdeaCandidate(candidate_id="c3", title="Thỏ con học thả diều", logline="C" * 100),
    ])


def test_scoring_is_deterministic_and_weighted():
    brief = _brief()
    candidate_set = _set()
    first = score_candidate_set(brief, candidate_set)
    second = score_candidate_set(brief, candidate_set)
    assert first == second
    assert first.evaluated is True
    assert first.scoring_rubric_version == SCORE_RUBRIC_VERSION
    for candidate in first.candidates:
        assert candidate.score is not None and 0.0 <= candidate.score <= 1.0
        assert set(candidate.score_dimensions) == set(SCORE_DIMENSION_WEIGHTS)


def test_scoring_weights_sum_to_one():
    assert abs(sum(SCORE_DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_tie_break_deterministic():
    candidates = [
        IdeaCandidate(candidate_id="b", title="B", score=0.8, score_dimensions={"AGE_FIT": 0.5}),
        IdeaCandidate(candidate_id="a", title="A", score=0.8, score_dimensions={"AGE_FIT": 0.5}),
    ]
    # Same total + same AGE_FIT -> lexicographic candidate_id wins.
    assert tie_break_candidates(candidates).candidate_id == "a"


def test_safety_failure_zeroes_score():
    brief = _brief()
    candidate_set = IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="c1", title="T1", safety_ok=False),
        IdeaCandidate(candidate_id="c2", title="T2"),
        IdeaCandidate(candidate_id="c3", title="T3"),
    ])
    scored = score_candidate_set(brief, candidate_set)
    unsafe = next(c for c in scored.candidates if c.candidate_id == "c1")
    assert unsafe.score_dimensions["SAFETY"] == 0.0
    assert unsafe.safety_ok is False


def test_candidate_count_boundaries():
    from windagent_core.contracts.studio.errors import StudioValidationError

    for count in (2, 6):
        try:
            IdeaCandidateSet(candidates=[IdeaCandidate(candidate_id=f"c{i}", title=f"T{i}") for i in range(count)])
            raise AssertionError(f"{count} candidates should be rejected")
        except StudioValidationError:
            pass
    ok = IdeaCandidateSet(candidates=[IdeaCandidate(candidate_id=f"c{i}", title=f"T{i}") for i in range(4)])
    assert len(ok.candidates) == 4


def test_duplicate_candidates_blocked():
    brief = _brief()
    candidate_set = IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="same", title="T1"),
        IdeaCandidate(candidate_id="same", title="T2"),
        IdeaCandidate(candidate_id="c3", title="T3"),
    ])
    report = validate_idea_candidate_set(candidate_set, brief)
    assert not report.is_pass()
    assert any(i.code == "IDEA_DUPLICATE" for i in report.issues)


def test_prohibited_content_blocks_candidate():
    brief = _brief()
    candidate_set = IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="c1", title="T1", summary="một trận bạo lực trong rừng"),
        IdeaCandidate(candidate_id="c2", title="T2"),
        IdeaCandidate(candidate_id="c3", title="T3"),
    ])
    report = validate_idea_candidate_set(candidate_set, brief)
    blocking = [i for i in report.issues if i.severity == ValidationSeverity.BLOCKING]
    assert any(i.code == "SAFETY_PROHIBITED" for i in blocking)


def test_age_unsuitable_blocks():
    brief = _brief()
    candidate_set = IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="c1", title="T1", age_fit=0.2),
        IdeaCandidate(candidate_id="c2", title="T2"),
        IdeaCandidate(candidate_id="c3", title="T3"),
    ])
    report = validate_idea_candidate_set(candidate_set, brief)
    assert any(i.code == "SAFETY_AGE_UNSUITABLE" and i.severity == ValidationSeverity.BLOCKING for i in report.issues)


def test_brief_validation_blocks_empty_title():
    report = validate_creative_brief(CreativeBrief(brief_id=CreativeBriefId("br_x"), title="  "))
    assert not report.is_pass()
    assert any(i.code == "FIELD_EMPTY" for i in report.issues)


def test_from_video_brief_preserves_pinned_fields():
    video = VideoCreativeBrief(
        brief_id=VideoBriefId("vb_1"),
        title="Con thỏ và cánh diều",
        genre="thiếu nhi",
        logline="Một chú thỏ học cách thả diều.",
        tone="ấm áp",
        audience="5-8",
        target_duration_seconds=240,
        aspect_ratio="16:9",
        production_constraints={"style": "hoạt hình"},
    )
    canonical = from_video_brief(video)
    assert canonical.title == video.title
    assert canonical.genre == video.genre
    assert canonical.target_duration_seconds == 240
    assert canonical.production_constraints == {"style": "hoạt hình"}
    assert canonical.brief_id == video.brief_id
    # Normalized additions default deterministically.
    assert canonical.language == "vi"
    assert canonical.audience_band() == "0-99"


def test_selection_requires_candidate_from_current_set():
    selected = SelectedIdea(
        selected_idea_id=SelectedIdeaId.generate("sel"),
        source_set_id="set_1",
        candidate_id="ghost",
        title="Không tồn tại",
    )
    report = validate_selected_idea(selected, _set())
    assert not report.is_pass()
    assert any(i.code == "REF_MISSING" for i in report.issues)
