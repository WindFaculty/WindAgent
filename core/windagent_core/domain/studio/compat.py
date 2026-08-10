"""
VideoProject <-> SeriesProject compatibility conversion (studio.contract/v0.1).

``VideoProject`` remains a V2 compatibility facade/read path during deprecation;
it is not a competing aggregate. Canonical hierarchy is exactly
``SeriesProject -> Episode -> ProductionRevision``.

The conversion is explicit and lossless and, critically, preserves the underlying
opaque identifier VALUE so no second project row is ever created during
migration: ``SeriesProjectId(video_project_id.value)[:.value] == video_project_id.value``.
"""

from __future__ import annotations

from typing import Any, Dict

from windagent_core.contracts.studio.ids import SeriesProjectId
from windagent_core.domain.video_production.ids import VideoProjectId
from windagent_core.domain.video_production.project import VideoProject
from windagent_core.domain.studio.series import SeriesProject

VIDEO_TO_SERIES_COMPAT_PREFIX = "ser_"


def series_id_from_video(video_project_id: VideoProjectId) -> SeriesProjectId:
    """Lossless identity-compatible SeriesProjectId from a VideoProjectId.

    Preserves the underlying value so a migrated project reads as the same
    logical project without a second row.
    """
    return SeriesProjectId(video_project_id.value)


def video_id_from_series(series_id: SeriesProjectId) -> VideoProjectId:
    """Reconstruct the V2 VideoProjectId for a canonical SeriesProjectId."""
    return VideoProjectId(series_id.value)


def to_series_project(
    video_project: VideoProject,
    *,
    description: str = "",
    metadata: Dict[str, Any] | None = None,
) -> SeriesProject:
    """Convert a V2 VideoProject into the canonical SeriesProject aggregate."""
    merged_metadata: Dict[str, Any] = {
        "legacy_project_status": video_project.status.value,
        "legacy_current_revision_id": (
            str(video_project.current_revision_id) if video_project.current_revision_id else None
        ),
        **dict(video_project.metadata),
        **(metadata or {}),
    }
    return SeriesProject(
        series_id=series_id_from_video(video_project.project_id),
        title=video_project.title,
        description=description,
        created_at=video_project.created_at,
        updated_at=video_project.updated_at,
        metadata=merged_metadata,
    )


def to_video_project(series_project: SeriesProject) -> VideoProject:
    """Project the canonical SeriesProject back to the V2 read facade.

    The legacy aggregate only carries a status and a current revision link;
    unknown Studio-only metadata is preserved in ``metadata`` but never invents
    revision content.
    """
    return VideoProject(
        project_id=video_id_from_series(series_project.series_id),
        title=series_project.title,
        created_at=series_project.created_at,
        updated_at=series_project.updated_at,
        metadata=dict(series_project.metadata),
    )


__all__ = [
    "VIDEO_TO_SERIES_COMPAT_PREFIX",
    "series_id_from_video",
    "video_id_from_series",
    "to_series_project",
    "to_video_project",
]
