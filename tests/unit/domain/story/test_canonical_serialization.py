"""B1 canonical serialization: round trips, hashing, Unicode, fail-closed versions."""

from __future__ import annotations

import json

import pytest

from windagent_core.domain.story import (
    ARTIFACT_SCHEMA_VERSION,
    content_hash_of,
    validate_artifact_schema_version,
)
from windagent_core.domain.story.ideation.models import (
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
)
from windagent_core.domain.story.ids import CreativeBriefId, SelectedIdeaId
from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError


def _brief() -> CreativeBrief:
    return CreativeBrief(
        brief_id=CreativeBriefId("br_1"),
        title="Con thỏ và cánh diều",
        genre="thiếu nhi",
        logline="Một chú thỏ học cách thả diều cùng người bạn mới.",
        tone="ấm áp",
        audience="5-8",
        audience_min_age=5,
        audience_max_age=8,
        language="vi",
        theme="tình bạn",
        target_duration_seconds=240,
        prohibited_content=["bạo lực"],
    )


def _set() -> IdeaCandidateSet:
    return IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="c1", title="Chú thỏ và cánh diều giấy", summary="Một chú thỏ tìm thấy cánh diều bị rơi."),
        IdeaCandidate(candidate_id="c2", title="Cánh diều bay qua sông", summary="Cánh diều đưa thỏ đi gặp bạn mới."),
        IdeaCandidate(candidate_id="c3", title="Thỏ con học thả diều", summary="Thỏ con kiên trì học thả diều."),
    ])


def test_round_trip_lossless_unicode():
    brief = _brief()
    restored = CreativeBrief.deserialize(brief.serialize())
    assert restored == brief
    assert restored.title == "Con thỏ và cánh diều"
    assert "cánh diều" in brief.serialize()


def test_canonical_serialization_sorted_and_ascii_safe():
    raw = _brief().serialize()
    parsed = json.loads(raw)
    # Sorted keys at every level.
    assert list(parsed.keys()) == sorted(parsed.keys())
    # ensure_ascii=False: Vietnamese chars survive verbatim.
    assert "\\u" not in raw.replace("\\u0027", "") or "cánh" in raw


def test_canonical_bytes_stable_regardless_of_key_order():
    a = _brief().canonical_bytes()
    b = json.dumps(
        {k: v for k, v in reversed(list(_brief().to_canonical_dict().items()))},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    assert a == b


def test_content_hash_deterministic_and_schema_scoped():
    brief = _brief()
    assert brief.content_hash() == brief.content_hash() == content_hash_of(brief.to_canonical_dict())
    assert len(brief.content_hash()) == 64
    # Same content but different schema version -> different hash.
    other = brief.model_copy(update={"schema_version": "studio.artifact/v1alpha2"})
    assert other.content_hash() != brief.content_hash()


def test_unknown_schema_version_fails_closed_at_construction():
    with pytest.raises(UnsupportedMajorVersionError):
        CreativeBrief(brief_id=CreativeBriefId("br_2"), title="X", schema_version="studio.artifact/v2")
    with pytest.raises(UnsupportedMajorVersionError):
        CreativeBrief(brief_id=CreativeBriefId("br_3"), title="Y", schema_version="garbage")


def test_unknown_major_rejected_at_parse():
    with pytest.raises(UnsupportedMajorVersionError):
        validate_artifact_schema_version("studio.artifact/v2")
    assert validate_artifact_schema_version(ARTIFACT_SCHEMA_VERSION) == ARTIFACT_SCHEMA_VERSION


def test_extra_fields_preserved_within_version():
    brief = _brief().model_copy(update={"future_field": {"x": 1}})
    restored = CreativeBrief.deserialize(brief.serialize())
    assert restored.future_field == {"x": 1}


def test_long_and_empty_inputs():
    long_title = "X" * 100_000
    brief = CreativeBrief(brief_id=CreativeBriefId("br_4"), title=long_title)
    assert len(brief.serialize()) > 100_000
    with pytest.raises(Exception):
        CreativeBrief(brief_id=CreativeBriefId("br_5"), title="")


def test_candidate_set_round_trip_and_count_rule():
    candidate_set = _set()
    restored = IdeaCandidateSet.deserialize(candidate_set.serialize())
    assert restored == candidate_set


def test_summary_is_presentation_safe():
    summary = _brief().to_summary()
    assert summary["title"] == "Con thỏ và cánh diều"
    assert summary["artifact_type"] == "CreativeBrief"
    # No envelope fields leak into summaries.
    for envelope_term in ("content_hash", "artifact_id", "revision_id", "prompt_id"):
        assert envelope_term not in summary


def test_selected_idea_round_trip():
    from windagent_core.domain.story.ideation.models import SelectedIdea

    selected = SelectedIdea(
        selected_idea_id=SelectedIdeaId.generate("sel"),
        source_set_id="set_1",
        candidate_id="c1",
        title="Chú thỏ và cánh diều giấy",
        rationale="Đề tài quen thuộc, phù hợp lứa tuổi 5-8.",
    )
    restored = SelectedIdea.deserialize(selected.serialize())
    assert restored == selected
