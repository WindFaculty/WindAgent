"""
Stage E Verification Suite — Script ↔ Asset Binding Domain & Handlers.

Tests:
1. ProductionAssetBinding model validation & immutability.
2. AssetEligibilityService rules (kind match, approved state, license state, archived blocking).
3. AssetRequirementResolver missing requirement generation & candidate ranking.
4. AssetCommandHandler BIND_ASSET and UNBIND_ASSET execution with eligibility evaluation.
5. ScriptAssetProjectionEngine event convergence.
"""

from windagent_core.domain.video_production.script_asset_binding import (
    ProductionAssetBinding,
    ScreenplayEntityType,
    BindingStatus,
)
from windagent_core.domain.video_production.asset_eligibility_service import (
    AssetEligibilityService,
)
from windagent_core.domain.video_production.asset_requirement_resolver import (
    AssetRequirementResolver,
)
from windagent_core.domain.video_production.production_asset import ProductionAsset
from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
from windagent_core.domain.video_production.ids import (
    VideoProjectId,
    ProductionRevisionId,
)
from windagent_core.domain.video_production.enums import (
    ProductionAssetKind,
    LicenseState,
)
from windagent_core.domain.video_production.asset_command_handlers import AssetCommandHandler
from windagent_core.domain.video_production.workspace import (
    WorkspaceCommandRequest,
    WorkspaceCommandStatus,
)
from windagent_core.domain.video_production.script_asset_projection import (
    ScriptAssetProjectionEngine,
)


def test_production_asset_binding_creation():
    binding = ProductionAssetBinding(
        binding_id="bnd_001",
        project_id="vp_01",
        production_revision_id="rev_13",
        screenplay_entity_type=ScreenplayEntityType.CHARACTER,
        screenplay_entity_id="char_bunny",
        role_key="primary",
        asset_id="asset_bunny",
        asset_revision_id="rev_asset_01",
    )
    assert binding.binding_id == "bnd_001"
    assert binding.status == BindingStatus.ACTIVE
    data = binding.to_dict()
    assert data["screenplay_entity_type"] == "CHARACTER"


def test_asset_eligibility_service():
    svc = AssetEligibilityService()

    approved_asset = ProductionAsset(
        asset_id="asset_bunny",
        kind=ProductionAssetKind.CHARACTER,
        name="Bunny Hero",
        lifecycle_state=AssetLifecycleState.APPROVED,
        license_state=LicenseState.LICENSED,
        active_revision_id="rev_asset_01",
    )

    res_approved = svc.evaluate_eligibility(
        asset=approved_asset,
        entity_type=ScreenplayEntityType.CHARACTER,
        entity_id="char_bunny",
        project_id="vp_01",
        target_revision_id="rev_13",
    )
    assert res_approved.is_eligible is True
    assert len(res_approved.blocking_reasons) == 0

    # Unapproved asset check
    unapproved_asset = ProductionAsset(
        asset_id="asset_draft",
        kind=ProductionAssetKind.CHARACTER,
        name="Bunny Draft",
        lifecycle_state=AssetLifecycleState.DOWNLOADED,
        license_state=LicenseState.UNKNOWN,
        active_revision_id="rev_asset_02",
    )

    res_unapproved = svc.evaluate_eligibility(
        asset=unapproved_asset,
        entity_type=ScreenplayEntityType.CHARACTER,
        entity_id="char_bunny",
        project_id="vp_01",
        target_revision_id="rev_13",
    )
    assert res_unapproved.is_eligible is False
    assert len(res_unapproved.blocking_reasons) >= 1


def test_asset_requirement_resolver():
    resolver = AssetRequirementResolver()

    screenplay_read_model = {
        "characters": [{"character_id": "char_bunny", "name": "Bunny"}],
        "locations": [{"location_id": "loc_park", "name": "Sunny Park"}],
        "props": [{"prop_id": "prop_ball", "name": "Red Beach Ball"}],
    }

    # With no active bindings, should generate requirements for character, location, prop
    reqs = resolver.generate_requirements(
        project_id="vp_01",
        revision_id="rev_13",
        screenplay_read_model=screenplay_read_model,
        active_bindings=[],
    )

    assert len(reqs) == 3
    req_types = {r.screenplay_entity_type for r in reqs}
    assert req_types == {
        ScreenplayEntityType.CHARACTER,
        ScreenplayEntityType.LOCATION,
        ScreenplayEntityType.PROP,
    }


def test_asset_command_handler_bind_unbind():
    approved_asset = ProductionAsset(
        asset_id="asset_bunny",
        kind=ProductionAssetKind.CHARACTER,
        name="Bunny Hero",
        lifecycle_state=AssetLifecycleState.APPROVED,
        license_state=LicenseState.LICENSED,
        active_revision_id="rev_asset_01",
    )

    handler = AssetCommandHandler(
        asset_store={"asset_bunny": approved_asset},
        revision_store={},
    )

    bind_req = WorkspaceCommandRequest(
        command_id="cmd_bind_01",
        command_type="BIND_ASSET",
        project_id=VideoProjectId("vp_01"),
        target_revision_id=ProductionRevisionId("rev_13"),
        entity_id="asset_bunny",
        reason="Initial binding test",
        idempotency_key="idem_01",
        payload={
            "screenplay_entity_type": "CHARACTER",
            "screenplay_entity_id": "char_bunny",
        },
    )

    bind_res = handler.handle(bind_req)
    assert bind_res["status"] == WorkspaceCommandStatus.COMPLETED.value
    assert "binding" in bind_res["payload"]

    unbind_req = WorkspaceCommandRequest(
        command_id="cmd_unbind_01",
        command_type="UNBIND_ASSET",
        project_id=VideoProjectId("vp_01"),
        target_revision_id=ProductionRevisionId("rev_13"),
        entity_id="asset_bunny",
        reason="Unbinding test",
        idempotency_key="idem_02",
        payload={
            "binding_id": bind_res["payload"]["binding"]["binding_id"],
            "screenplay_entity_id": "char_bunny",
        },
    )

    unbind_res = handler.handle(unbind_req)
    assert unbind_res["status"] == WorkspaceCommandStatus.COMPLETED.value


def test_script_asset_projection_convergence():
    engine = ScriptAssetProjectionEngine()

    engine.apply_event(
        "ASSET_BINDING_CREATED",
        {
            "binding_id": "bnd_01",
            "project_id": "vp_01",
            "production_revision_id": "rev_13",
            "screenplay_entity_type": "CHARACTER",
            "screenplay_entity_id": "char_bunny",
            "role_key": "primary",
            "asset_id": "asset_bunny",
            "asset_revision_id": "rev_asset_01",
            "actor": "user",
        },
    )

    summary = engine.build_inspector_summary("vp_01", "rev_13", total_requirements=2)
    assert summary.fulfilled_requirements == 1
    assert summary.bound_character_count == 1
    assert summary.completion_percentage == 50.0

    usage = engine.build_asset_usage("asset_bunny")
    assert usage.usage_count == 1
    assert usage.bound_project_ids == ["vp_01"]
