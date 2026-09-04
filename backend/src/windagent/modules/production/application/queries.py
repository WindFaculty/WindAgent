"""Immutable Production queries."""

from __future__ import annotations

from dataclasses import dataclass

from windagent.platform.queries import Query

from .models import (
    AssetRevisionView,
    AudioTrackView,
    CodeVideoProjectView,
    EdlView,
    MixPlanView,
    ProductionAssetView,
    ProductionProjectView,
    ProductionRevisionView,
    RenderJobView,
)


@dataclass(frozen=True, slots=True)
class GetProductionProject(Query[ProductionProjectView]):
    project_id: str


@dataclass(frozen=True, slots=True)
class ListProductionProjects(Query[tuple[ProductionProjectView, ...]]):
    pass


@dataclass(frozen=True, slots=True)
class GetProductionRevision(Query[ProductionRevisionView]):
    revision_id: str


@dataclass(frozen=True, slots=True)
class ListProductionRevisions(Query[tuple[ProductionRevisionView, ...]]):
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetProductionAsset(Query[ProductionAssetView]):
    asset_id: str


@dataclass(frozen=True, slots=True)
class ListProductionAssets(Query[tuple[ProductionAssetView, ...]]):
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetAssetRevision(Query[AssetRevisionView]):
    revision_id: str


@dataclass(frozen=True, slots=True)
class ListAssetRevisions(Query[tuple[AssetRevisionView, ...]]):
    asset_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetAudioTrack(Query[AudioTrackView]):
    track_id: str


@dataclass(frozen=True, slots=True)
class ListAudioTracks(Query[tuple[AudioTrackView, ...]]):
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetMixPlan(Query[MixPlanView]):
    mix_plan_id: str


@dataclass(frozen=True, slots=True)
class ListMixPlans(Query[tuple[MixPlanView, ...]]):
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetCodeVideoProject(Query[CodeVideoProjectView]):
    project_id: str


@dataclass(frozen=True, slots=True)
class ListCodeVideoProjects(Query[tuple[CodeVideoProjectView, ...]]):
    pass


@dataclass(frozen=True, slots=True)
class GetRenderJob(Query[RenderJobView]):
    job_id: str


@dataclass(frozen=True, slots=True)
class ListRenderJobs(Query[tuple[RenderJobView, ...]]):
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class GetEdl(Query[EdlView]):
    edl_id: str


@dataclass(frozen=True, slots=True)
class ListEdls(Query[tuple[EdlView, ...]]):
    project_id: str | None = None
