"""A2 domain tests: VideoProject <-> SeriesProject compatibility conversion.

The conversion is lossless and preserves the underlying opaque identifier
value so migration never creates a second project row.
"""

from windagent_core.contracts.studio.ids import SeriesProjectId
from windagent_core.domain.studio.compat import (
    series_id_from_video,
    to_series_project,
    to_video_project,
    video_id_from_series,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.domain.video_production.ids import VideoProjectId
from windagent_core.domain.video_production.project import VideoProject


def test_series_id_preserves_video_project_id_value():
    vid = VideoProjectId.generate("proj")
    sid = series_id_from_video(vid)
    assert isinstance(sid, SeriesProjectId)
    assert sid.value == vid.value  # no second project row
    assert video_id_from_series(sid) == vid


def test_to_series_project_is_lossless_and_marks_legacy():
    vid = VideoProjectId.generate("proj")
    vp = VideoProject(
        project_id=vid,
        title="Legacy Pilot",
        metadata={"genre": "drama"},
    )
    sp = to_series_project(vp, description="ported")
    assert isinstance(sp, SeriesProject)
    assert sp.series_id.value == vid.value
    assert sp.title == "Legacy Pilot"
    assert sp.metadata["legacy_project_status"] == vp.status.value
    assert sp.metadata["genre"] == "drama"
    assert sp.description == "ported"


def test_to_video_project_projection_round_trip():
    vid = VideoProjectId.generate("proj")
    vp = VideoProject(project_id=vid, title="Pilot", metadata={"k": "v"})
    sp = to_series_project(vp)
    back = to_video_project(sp)
    assert back.project_id == vid
    assert back.title == "Pilot"
    # unknown studio-only metadata is preserved, not invented into revisions
    assert back.metadata["k"] == "v"
    assert back.metadata["legacy_project_status"] == vp.status.value


def test_series_project_round_trip_keeps_identity():
    sp = SeriesProject(
        series_id=SeriesProjectId.generate("ser"),
        title="Canonical Series",
    )
    vp = to_video_project(sp)
    restored = to_series_project(vp)
    assert restored.series_id == sp.series_id
    assert restored.title == sp.title
