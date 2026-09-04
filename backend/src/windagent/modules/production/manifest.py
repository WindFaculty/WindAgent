"""Module manifest for Production (Phase 16)."""

from __future__ import annotations

from windagent.platform.modules import (
    CommandRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)

from .api.routes import MODULE_ID, MODULE_VERSION, create_production_router
from .application.commands import (
    CreateAssetRevision,
    CreateAudioTrack,
    CreateCodeVideoProject,
    CreateEdl,
    CreateMixPlan,
    CreateProductionAsset,
    CreateProductionProject,
    CreateProductionRevision,
    CreateRenderJob,
    DeriveProductionRevision,
    LockProductionRevision,
    TransitionCodeVideoProject,
    TransitionProductionAsset,
    TransitionRenderJob,
    UpdateEdl,
    UpdateProductionProject,
)
from .application.handlers import (
    CreateAssetRevisionHandler,
    CreateAudioTrackHandler,
    CreateCodeVideoProjectHandler,
    CreateEdlHandler,
    CreateMixPlanHandler,
    CreateProductionAssetHandler,
    CreateProductionProjectHandler,
    CreateProductionRevisionHandler,
    CreateRenderJobHandler,
    DeriveProductionRevisionHandler,
    GetAssetRevisionHandler,
    GetAudioTrackHandler,
    GetCodeVideoProjectHandler,
    GetEdlHandler,
    GetMixPlanHandler,
    GetProductionAssetHandler,
    GetProductionProjectHandler,
    GetProductionRevisionHandler,
    GetRenderJobHandler,
    ListAssetRevisionsHandler,
    ListAudioTracksHandler,
    ListCodeVideoProjectsHandler,
    ListEdlsHandler,
    ListMixPlansHandler,
    ListProductionAssetsHandler,
    ListProductionProjectsHandler,
    ListProductionRevisionsHandler,
    ListRenderJobsHandler,
    LockProductionRevisionHandler,
    TransitionCodeVideoProjectHandler,
    TransitionProductionAssetHandler,
    TransitionRenderJobHandler,
    UpdateEdlHandler,
    UpdateProductionProjectHandler,
)
from .application.queries import (
    GetAssetRevision,
    GetAudioTrack,
    GetCodeVideoProject,
    GetEdl,
    GetMixPlan,
    GetProductionAsset,
    GetProductionProject,
    GetProductionRevision,
    GetRenderJob,
    ListAssetRevisions,
    ListAudioTracks,
    ListCodeVideoProjects,
    ListEdls,
    ListMixPlans,
    ListProductionAssets,
    ListProductionProjects,
    ListProductionRevisions,
    ListRenderJobs,
)
from .application.runtime import ProductionServices
from .jobs.handlers import (
    ProductionAssetNormalizeJobHandler,
    ProductionCodeVideoVerifyJobHandler,
    ProductionPostprocessJobHandler,
    ProductionRenderJobHandler,
)

PRODUCTION_JOB_TYPES = (
    "production.render.execute",
    "production.postprocess.assemble",
    "production.asset.normalize",
    "production.code_video.verify",
)


def build_production_manifest(services: ProductionServices | None = None) -> ModuleManifest:
    return ModuleManifest(
        id=MODULE_ID,
        version=MODULE_VERSION,
        commands=(
            CommandRegistration(CreateProductionProject, CreateProductionProjectHandler(services)),
            CommandRegistration(UpdateProductionProject, UpdateProductionProjectHandler(services)),
            CommandRegistration(CreateProductionRevision, CreateProductionRevisionHandler(services)),
            CommandRegistration(DeriveProductionRevision, DeriveProductionRevisionHandler(services)),
            CommandRegistration(LockProductionRevision, LockProductionRevisionHandler(services)),
            CommandRegistration(CreateProductionAsset, CreateProductionAssetHandler(services)),
            CommandRegistration(TransitionProductionAsset, TransitionProductionAssetHandler(services)),
            CommandRegistration(CreateAssetRevision, CreateAssetRevisionHandler(services)),
            CommandRegistration(CreateAudioTrack, CreateAudioTrackHandler(services)),
            CommandRegistration(CreateMixPlan, CreateMixPlanHandler(services)),
            CommandRegistration(CreateCodeVideoProject, CreateCodeVideoProjectHandler(services)),
            CommandRegistration(TransitionCodeVideoProject, TransitionCodeVideoProjectHandler(services)),
            CommandRegistration(CreateRenderJob, CreateRenderJobHandler(services)),
            CommandRegistration(TransitionRenderJob, TransitionRenderJobHandler(services)),
            CommandRegistration(CreateEdl, CreateEdlHandler(services)),
            CommandRegistration(UpdateEdl, UpdateEdlHandler(services)),
        ),
        queries=(
            QueryRegistration(GetProductionProject, GetProductionProjectHandler(services)),
            QueryRegistration(ListProductionProjects, ListProductionProjectsHandler(services)),
            QueryRegistration(GetProductionRevision, GetProductionRevisionHandler(services)),
            QueryRegistration(ListProductionRevisions, ListProductionRevisionsHandler(services)),
            QueryRegistration(GetProductionAsset, GetProductionAssetHandler(services)),
            QueryRegistration(ListProductionAssets, ListProductionAssetsHandler(services)),
            QueryRegistration(GetAssetRevision, GetAssetRevisionHandler(services)),
            QueryRegistration(ListAssetRevisions, ListAssetRevisionsHandler(services)),
            QueryRegistration(GetAudioTrack, GetAudioTrackHandler(services)),
            QueryRegistration(ListAudioTracks, ListAudioTracksHandler(services)),
            QueryRegistration(GetMixPlan, GetMixPlanHandler(services)),
            QueryRegistration(ListMixPlans, ListMixPlansHandler(services)),
            QueryRegistration(GetCodeVideoProject, GetCodeVideoProjectHandler(services)),
            QueryRegistration(ListCodeVideoProjects, ListCodeVideoProjectsHandler(services)),
            QueryRegistration(GetRenderJob, GetRenderJobHandler(services)),
            QueryRegistration(ListRenderJobs, ListRenderJobsHandler(services)),
            QueryRegistration(GetEdl, GetEdlHandler(services)),
            QueryRegistration(ListEdls, ListEdlsHandler(services)),
        ),
        jobs=(
            JobRegistration("production.render.execute", ProductionRenderJobHandler(services)),
            JobRegistration("production.postprocess.assemble", ProductionPostprocessJobHandler(services)),
            JobRegistration("production.asset.normalize", ProductionAssetNormalizeJobHandler(services)),
            JobRegistration("production.code_video.verify", ProductionCodeVideoVerifyJobHandler(services)),
        ),
        routers=(create_production_router(),),
        capabilities=("production", "video", "assets", "audio", "code_video", "rendering", "postproduction"),
    )


manifest = build_production_manifest()
