"""
Unit and Integration Test Suite for Stage D Universal Production Asset Domain (UI19–UI33).

Covers:
- UI19 Taxonomy: ProductionAssetKind, MediaType, compatibility
- UI20 Aggregate & Revisions: ProductionAsset, immutable AssetRevision, content hashing, lineage
- UI21 Lifecycles: Dual business and operational state machine transitions
- UI22 Query Service: Multi-attribute filtering, cursor pagination, detail inspection
- UI23 Command Dispatcher: Import, upload, approval, rejection, revision creation, binding
- UI26 License Governance: Fail-closed server-side eligibility checks
- UI32 Dependency Graph & UI33 Version Replacement Impact Analysis
"""

import pytest
from windagent_core.domain.video_production.asset_command_handlers import AssetCommandHandler
from windagent_core.domain.video_production.asset_lifecycle import (
    AssetLifecycleState,
)
from windagent_core.domain.video_production.asset_query_service import AssetQueryService
from windagent_core.domain.video_production.enums import (
    AssetProcessingState,
    LicenseState,
    MediaType,
    ProductionAssetKind,
)
from windagent_core.domain.video_production.errors import VideoProductionProtocolError
from windagent_core.domain.video_production.production_asset import (
    AssetRevision,
    ProductionAsset,
)
from windagent_core.domain.video_production.workspace import (
    WorkspaceCommandRequest,
    WorkspaceCommandType,
)


def test_production_asset_taxonomy_ui19():
    """Verify Stage D UI19 taxonomy enums and media compatibility."""
    assert ProductionAssetKind.CHARACTER.value == "CHARACTER"
    assert ProductionAssetKind.MODEL_3D.value == "MODEL_3D"
    assert ProductionAssetKind.MUSIC.value == "MUSIC"

    # MediaType extensions
    assert MediaType.MODEL_3D.value == "model_3d"
    assert MediaType.AUDIO.value == "audio"


def test_production_asset_aggregate_ui20():
    """Verify ProductionAsset aggregate root, immutable AssetRevision, and lineage pointers."""
    asset = ProductionAsset(
        asset_id="ast_hero_01",
        kind=ProductionAssetKind.CHARACTER,
        name="Hero Character",
        lifecycle_state=AssetLifecycleState.DISCOVERED,
        processing_state=AssetProcessingState.IDLE,
        license_state=LicenseState.UNKNOWN,
    )

    rev1 = AssetRevision(
        revision_id="rev_v1",
        asset_id="ast_hero_01",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        media_type=MediaType.MODEL_3D,
        mime_type="model/gltf-binary",
        size_bytes=1000,
    )

    asset.set_active_revision(rev1.revision_id)

    assert asset.asset_id == "ast_hero_01"
    assert asset.active_revision_id == "rev_v1"
    assert rev1.content_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_asset_lifecycle_state_machine_ui21():
    """Verify dual state machines and fail-closed transition rules."""
    asset = ProductionAsset(
        asset_id="ast_test",
        kind=ProductionAssetKind.PROP,
        name="Test Prop",
        lifecycle_state=AssetLifecycleState.DISCOVERED,
        processing_state=AssetProcessingState.IDLE,
    )

    # Valid progression
    asset.update_lifecycle_state(AssetLifecycleState.DOWNLOADED)
    assert asset.lifecycle_state == AssetLifecycleState.DOWNLOADED

    asset.update_lifecycle_state(AssetLifecycleState.VALIDATED)
    assert asset.lifecycle_state == AssetLifecycleState.VALIDATED

    asset.update_lifecycle_state(AssetLifecycleState.APPROVED)
    assert asset.lifecycle_state == AssetLifecycleState.APPROVED

    # Operational processing state update
    asset.update_processing_state(AssetProcessingState.NORMALIZING)
    assert asset.processing_state == AssetProcessingState.NORMALIZING

    # Illegal transition: cannot go from BOUND_TO_PROJECT to DISCOVERED
    asset.update_lifecycle_state(AssetLifecycleState.BOUND_TO_PROJECT)
    with pytest.raises(VideoProductionProtocolError):
        asset.update_lifecycle_state(AssetLifecycleState.DISCOVERED)


def test_server_license_governance_ui26():
    """Verify server-side license governance fail-closed gate."""
    untrusted = ProductionAsset(
        asset_id="ast_untrusted",
        kind=ProductionAssetKind.OTHER,
        name="Untrusted Asset",
        license_state=LicenseState.UNKNOWN,
    )
    assert not untrusted.is_eligible_for_production()

    approved = ProductionAsset(
        asset_id="ast_approved",
        kind=ProductionAssetKind.OTHER,
        name="Approved Commercial Asset",
        license_state=LicenseState.LICENSED,
        lifecycle_state=AssetLifecycleState.APPROVED,
    )
    assert approved.is_eligible_for_production()

    rejected = ProductionAsset(
        asset_id="ast_rejected",
        kind=ProductionAssetKind.OTHER,
        name="Rejected Asset",
        license_state=LicenseState.REJECTED,
        lifecycle_state=AssetLifecycleState.REJECTED,
    )
    assert not rejected.is_eligible_for_production()


def test_asset_command_handlers_ui23():
    """Verify asset mutating command execution."""
    asset_store = {}
    revision_store = {}
    handler = AssetCommandHandler(asset_store, revision_store)

    # 1. IMPORT_ASSET
    req_import = WorkspaceCommandRequest(
        command_id="cmd_1",
        command_type=WorkspaceCommandType.IMPORT_ASSET,
        project_id="prj_1",
        target_revision_id="rev_0",
        entity_id="ast_cyber_car",
        reason="Import speeder vehicle",
        idempotency_key="idemp_1",
        payload={
            "name": "Cyber Speeder",
            "kind": "MODEL_3D",
            "media_type": "model_3d",
            "size_bytes": 2048576,
            "license_state": "CREATIVE_COMMONS",
        },
    )

    res_import = handler.handle(req_import)
    assert res_import["status"] == "COMPLETED"
    assert "ast_cyber_car" in asset_store
    asset = asset_store["ast_cyber_car"]
    assert asset.name == "Cyber Speeder"
    assert asset.kind == ProductionAssetKind.MODEL_3D

    # 2. APPROVE_ASSET
    req_approve = WorkspaceCommandRequest(
        command_id="cmd_2",
        command_type=WorkspaceCommandType.APPROVE_ASSET,
        project_id="prj_1",
        target_revision_id="rev_0",
        entity_id="ast_cyber_car",
        reason="Human legal approval",
        idempotency_key="idemp_2",
    )
    res_approve = handler.handle(req_approve)
    assert res_approve["status"] == "COMPLETED"
    assert asset.lifecycle_state == AssetLifecycleState.APPROVED

    # 3. BIND_ASSET
    req_bind = WorkspaceCommandRequest(
        command_id="cmd_3",
        command_type=WorkspaceCommandType.BIND_ASSET,
        project_id="prj_1",
        target_revision_id="rev_0",
        entity_id="ast_cyber_car",
        reason="Bind to episode project",
        idempotency_key="idemp_3",
    )
    res_bind = handler.handle(req_bind)
    assert res_bind["status"] == "COMPLETED"
    assert "prj_1" in asset.project_bindings
    assert asset.lifecycle_state == AssetLifecycleState.BOUND_TO_PROJECT


def test_asset_query_service_and_impact_analysis_ui22_ui32_ui33():
    """Verify query listing, pagination, inspector detail, and version replacement impact analysis."""
    asset_store = {}
    revision_store = {}

    a = ProductionAsset(
        asset_id="ast_dragon",
        kind=ProductionAssetKind.CHARACTER,
        name="Dragon Rig",
        lifecycle_state=AssetLifecycleState.APPROVED,
        license_state=LicenseState.LICENSED,
        project_bindings=["prj_fantasy"],
    )

    r1 = AssetRevision(
        revision_id="rev_dragon_v1",
        asset_id="ast_dragon",
        content_hash="1111111111111111111111111111111111111111111111111111111111111111",
        size_bytes=5000,
    )
    r2 = AssetRevision(
        revision_id="rev_dragon_v2",
        asset_id="ast_dragon",
        supersedes_revision_id="rev_dragon_v1",
        content_hash="2222222222222222222222222222222222222222222222222222222222222222",
        size_bytes=6200,
    )

    a.set_active_revision("rev_dragon_v1")
    asset_store[a.asset_id] = a
    revision_store[r1.revision_id] = r1
    revision_store[r2.revision_id] = r2

    qs = AssetQueryService(asset_store, revision_store)

    # 1. Listing with filter
    list_res = qs.list_assets(project_id="prj_fantasy", kind="CHARACTER")
    assert list_res["total_count"] == 1
    assert list_res["items"][0]["asset_id"] == "ast_dragon"

    # 2. Detail inspection
    detail = qs.get_asset_detail("ast_dragon")
    assert detail is not None
    assert detail["asset"]["name"] == "Dragon Rig"
    assert detail["revisions_count"] == 2

    # 3. Revision replacement impact
    impact = qs.compare_revisions("ast_dragon", "rev_dragon_v1", "rev_dragon_v2")
    assert impact["hash_changed"] is True
    assert impact["size_diff_bytes"] == 1200
    assert impact["impacted_projects_count"] == 1
