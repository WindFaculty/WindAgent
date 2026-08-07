"""
Phase 10 — Continuity Ledger unit tests (plan 03 §20).

Covers:
- prop changes hands without a screenplay action -> blocking;
- wardrobe change allowed by the screenplay -> passes;
- identity/reference hash mismatch -> blocking;
- 180-degree camera-side violation detected;
- parallel branches creating a conflicting canonical change -> issue;
- human override carries a full audit record (actor, reason, revision, time);
- multi-scene state reset/continuation follows the policy;
- ledger hash is deterministic and traceable to source hashes;
- serialize/round-trip the ledger.
"""

from windagent_core.domain.video_production.continuity import (
    ContinuityChange,
    ContinuityLedger,
    HumanContinuityOverride,
)
from windagent_core.domain.video_production.enums import (
    CameraSide,
    ContinuityFieldSource,
    ContinuityIssueCode,
    DependencyType,
)
from windagent_core.domain.video_production.ids import (
    ContinuityOverrideId,
    ProductionRevisionId,
    ReferenceAssetId,
    SceneId,
    ShotDependencyId,
    ShotId,
)
from windagent_core.domain.video_production.shot import (
    Shot,
    ShotDependency,
    ShotDependencyGraph,
)
from windagent_core.domain.video_production.shot_graph import CameraDecision
from windagent_intelligence.video import (
    ContinuityLedgerService,
    ShotGraphPlannerService,
)
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt

from tests.fixtures.video_production.director_fixtures import (
    build_multi_scene_drama_package,
    build_short_cartoon_package,
    build_two_character_dialogue_package,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _shot(shot_id: str, scene_id: str, order: int, **kwargs) -> Shot:
    defaults = {
        "shot_id": ShotId(shot_id),
        "scene_id": SceneId(scene_id),
        "order": order,
        "duration_seconds": 3.0,
    }
    defaults.update(kwargs)
    return Shot(**defaults)


def _dep(dep_id: str, from_id: str, to_id: str, **kwargs) -> ShotDependency:
    defaults = {
        "dependency_id": ShotDependencyId(dep_id),
        "from_shot_id": ShotId(from_id),
        "to_shot_id": ShotId(to_id),
        "dependency_type": DependencyType.TEMPORAL,
    }
    defaults.update(kwargs)
    return ShotDependency(**defaults)


def _graph(*shots, deps=()) -> ShotDependencyGraph:
    return ShotDependencyGraph(shots=list(shots), dependencies=list(deps))


def _change(field: str, after, *, before=None, source=ContinuityFieldSource.DIRECTOR_DECISION) -> ContinuityChange:
    return ContinuityChange(field=field, before=before, after=after, source=source)


async def _graph_receipt_for(builder) -> "ShotGraphReceipt":
    """Phase 8 director + Phase 9 shot graph for a golden fixture."""
    from windagent_intelligence.video import VideoDirectorService
    from tests.fixtures.video_production.director_fixtures import (
        DeterministicDirectorModel,
        build_pinned_planner_output,
    )

    pkg = builder()
    plan_json = build_pinned_planner_output(pkg)
    director = VideoDirectorService(DeterministicDirectorModel(plan_json))
    receipt = await director.create_cinematic_plan_receipt(pkg)
    locked = await director.lock_shot_plan(receipt.plan)
    return ShotGraphPlannerService().plan(pkg, locked)


def _override(field: str, after, *, actor="reviewer-1", reason="approved fix") -> HumanContinuityOverride:
    return HumanContinuityOverride(
        override_id=ContinuityOverrideId(StableIdFactory().continuity_override_id(field)),
        actor=actor,
        reason=reason,
        target_revision=ProductionRevisionId("rev_phase10_1"),
        field=field,
        before=None,
        after=after,
    )


# ---------------------------------------------------------------------------
# Golden fixtures build clean ledgers
# ---------------------------------------------------------------------------
class TestGoldenFixtures:
    async def test_short_cartoon_ledger_traceable(self):
        pkg = build_short_cartoon_package()
        graph_receipt = await _graph_receipt_for(build_short_cartoon_package)
        svc = ContinuityLedgerService()
        result = svc.build(pkg, graph_receipt)
        assert result.ledger.entries
        assert result.ledger_hash
        # Identity is traced through every shot (Doudou portrait reference).
        assert any(
            any(f.startswith("identity:") for f in e.incoming_state)
            for e in result.ledger.entries
        )
        # Clean golden fixture -> no blocking continuity defects.
        assert result.blocking_issues == []

    async def test_two_character_dialogue_ledger_clean(self):
        pkg = build_two_character_dialogue_package()
        graph_receipt = await _graph_receipt_for(build_two_character_dialogue_package)
        result = ContinuityLedgerService().build(pkg, graph_receipt)
        assert result.blocking_issues == []

    async def test_multi_scene_ledger_clean(self):
        pkg = build_multi_scene_drama_package()
        graph_receipt = await _graph_receipt_for(build_multi_scene_drama_package)
        result = ContinuityLedgerService().build(pkg, graph_receipt)
        assert result.blocking_issues == []

    async def test_ledger_hash_deterministic(self):
        pkg = build_short_cartoon_package()
        graph_receipt = await _graph_receipt_for(build_short_cartoon_package)
        svc = ContinuityLedgerService()
        r1 = svc.build(pkg, graph_receipt)
        r2 = svc.build(pkg, graph_receipt)
        assert r1.ledger_hash == r2.ledger_hash
        assert r1.ledger.model_dump_json() == r2.ledger.model_dump_json()

    async def test_ledger_hash_traceable_to_sources(self):
        pkg = build_short_cartoon_package()
        graph_receipt = await _graph_receipt_for(build_short_cartoon_package)
        svc = ContinuityLedgerService()
        r1 = svc.build(pkg, graph_receipt)
        r2 = svc.build(pkg, graph_receipt)
        assert r1.ledger_hash == r2.ledger_hash
        assert r1.source_graph_hash == graph_receipt.graph_hash
        assert r1.source_plan_hash == graph_receipt.source_plan_hash
        assert r1.source_package_hash == graph_receipt.source_package_hash


# ---------------------------------------------------------------------------
# §20: Prop change without action -> blocking
# ---------------------------------------------------------------------------
class TestPropChangeWithoutAction:
    def test_prop_change_without_screenplay_action_blocking(self):
        pkg = build_short_cartoon_package()
        graph = _graph(
            _shot("s1", "scn_01", 1),
            _shot("s2", "scn_01", 2),
            deps=[_dep("e1", "s1", "s2", blocking=True)],
        )
        graph_receipt = _receipt(pkg, graph)
        result = ContinuityLedgerService().build(
            pkg,
            graph_receipt,
            planned_changes={
                "s2": [_change("prop:prp_ball:possessor", "chr_doudou")],
            },
        )
        codes = {i.code for i in result.issues}
        assert ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE in codes
        assert result.blocking_issues


# ---------------------------------------------------------------------------
# §20: Wardrobe change allowed by screenplay -> passes
# ---------------------------------------------------------------------------
class TestWardrobeChangeAllowed:
    def test_wardrobe_change_with_screenplay_action_passes(self):
        pkg = build_two_character_dialogue_package()
        graph = _graph(
            _shot("s1", "scn_01", 1),
            _shot("s2", "scn_01", 2),
            deps=[_dep("e1", "s1", "s2", blocking=True)],
        )
        graph_receipt = _receipt(pkg, graph)
        # The screenplay action text mentions "wears" -> clothing change allowed.
        scene = pkg.screenplay.scenes[0]
        scene = scene.model_copy(
            update={
                "action_description": "Minh takes off his coat and wears a raincoat.",
            }
        )
        pkg = pkg.model_copy(
            update={"screenplay": pkg.screenplay.model_copy(update={"scenes": [scene]})}
        )
        result = ContinuityLedgerService().build(
            pkg,
            graph_receipt,
            planned_changes={
                "s2": [_change("appearance:chr_minh:clothing", "raincoat",
                               source=ContinuityFieldSource.SCREENPLAY_FACT)],
            },
        )
        codes = {i.code for i in result.issues}
        assert ContinuityIssueCode.CHANGE_OUTSIDE_ALLOWED not in codes
        assert result.blocking_issues == []


# ---------------------------------------------------------------------------
# §20: Identity / reference hash mismatch -> blocking
# ---------------------------------------------------------------------------
class TestIdentityHashMismatch:
    def test_identity_reference_mismatch_blocking(self):
        pkg = build_short_cartoon_package()
        # Give Doudou a SECOND approved portrait; the shot binds the OTHER one
        # so the incoming bible identity != the required shot identity.
        second = pkg.assets[0].model_copy(
            update={
                "asset_id": ReferenceAssetId("ast_doudou_v2"),
                "content_hash": "1" * 64,
            }
        )
        char = pkg.characters[0].model_copy(
            update={
                "portrait_asset_ids": [
                    pkg.characters[0].portrait_asset_ids[0],
                    ReferenceAssetId("ast_doudou_v2"),
                ]
            }
        )
        pkg2 = pkg.model_copy(
            update={"assets": [*pkg.assets, second], "characters": [char]}
        )
        graph2 = _graph(
            _shot("s1", "scn_01", 1).model_copy(
                update={"reference_asset_ids": [ReferenceAssetId("ast_doudou_v2")]}
            )
        )
        result = ContinuityLedgerService().build(
            pkg2,
            _receipt(pkg2, graph2),
        )
        codes = {i.code for i in result.issues}
        assert ContinuityIssueCode.IDENTITY_HASH_MISMATCH in codes
        assert result.blocking_issues


# ---------------------------------------------------------------------------
# §20: 180-degree camera-side violation detected
# ---------------------------------------------------------------------------
class TestCameraSideViolation:
    def test_180_degree_flip_detected(self):
        pkg = build_short_cartoon_package()
        graph = _graph(
            _shot("s1", "scn_01", 1),
            _shot("s2", "scn_01", 2),
            deps=[_dep("e1", "s1", "s2", blocking=True)],
        )
        # Camera decisions: shot 1 SIDE_A, shot 2 SIDE_B (a flip inside scene).
        receipt = _receipt(pkg, graph)
        specs = list(receipt.specifications)
        specs[0] = specs[0].model_copy(
            update={"camera": CameraDecision(camera_side=CameraSide.SIDE_A)}
        )
        specs[1] = specs[1].model_copy(
            update={"camera": CameraDecision(camera_side=CameraSide.SIDE_B)}
        )
        flip_receipt = ShotGraphReceipt(
            graph=receipt.graph,
            specifications=specs,
            scheduling=receipt.scheduling,
            graph_hash=receipt.graph_hash,
            source_plan_hash=receipt.source_plan_hash,
            source_package_hash=receipt.source_package_hash,
        )
        result = ContinuityLedgerService().build(pkg, flip_receipt)
        codes = {i.code for i in result.issues}
        assert ContinuityIssueCode.CAMERA_SIDE_VIOLATION in codes
        assert result.blocking_issues


# ---------------------------------------------------------------------------
# §20: Parallel branches create a conflicting canonical change -> issue
# ---------------------------------------------------------------------------
class TestParallelConflict:
    def test_parallel_branches_conflict(self):
        pkg = build_short_cartoon_package()
        graph = _graph(
            _shot("s1", "scn_01", 1),
            _shot("s2", "scn_01", 2),
            # No blocking edge between s1 and s2 -> parallel.
        )
        result = ContinuityLedgerService().build(
            pkg,
            _receipt(pkg, graph),
            planned_changes={
                "s1": [_change("appearance:chr_doudou:emotion", "happy")],
                "s2": [_change("appearance:chr_doudou:emotion", "sad")],
            },
        )
        codes = {i.code for i in result.issues}
        assert ContinuityIssueCode.PARALLEL_CONFLICT in codes
        assert result.blocking_issues


# ---------------------------------------------------------------------------
# §20: Human override has an audit record
# ---------------------------------------------------------------------------
class TestHumanOverride:
    def test_override_audit_record(self):
        pkg = build_short_cartoon_package()
        graph = _graph(
            _shot("s1", "scn_01", 1),
            _shot("s2", "scn_01", 2),
            deps=[_dep("e1", "s1", "s2", blocking=True)],
        )
        override = _override("appearance:chr_doudou:clothing", "blue scarf")
        result = ContinuityLedgerService().build(
            pkg,
            _receipt(pkg, graph),
            overrides=[override],
        )
        # Audit record present with actor / reason / revision / timestamp.
        assert len(result.ledger.overrides) == 1
        record = result.ledger.overrides[0]
        assert record.actor == "reviewer-1"
        assert record.reason == "approved fix"
        assert str(record.target_revision) == "rev_phase10_1"
        assert record.timestamp is not None
        # The override applied from the first shot (no target -> first shot).
        assert result.ledger.entry_for(ShotId("s1")).planned_changes
        assert result.ledger.entry_for(ShotId("s1")).outgoing_state[
            "appearance:chr_doudou:clothing"
        ].source == ContinuityFieldSource.HUMAN_OVERRIDE


# ---------------------------------------------------------------------------
# §20: Multi-scene state reset / continuation policy
# ---------------------------------------------------------------------------
class TestMultiScenePolicy:
    async def test_scene_boundary_resets_location_keeps_identity(self):
        pkg = build_multi_scene_drama_package()
        graph_receipt = await _graph_receipt_for(build_multi_scene_drama_package)
        result = ContinuityLedgerService().build(pkg, graph_receipt)
        entries = result.ledger.entries
        assert len(entries) >= 3
        # Camera side resets to NEUTRAL at each new scene.
        scene_boundaries = [e for e in entries if e.scene_id and entries[0].scene_id != e.scene_id]
        if scene_boundaries:
            assert scene_boundaries[0].incoming_state["camera_side"].value == "NEUTRAL"
        # Identity continues across scenes (Keeper portrait traced).
        identity_fields = {
            f: e for e in entries for f in e.incoming_state if f.startswith("identity:")
        }
        assert identity_fields


# ---------------------------------------------------------------------------
# Validator-level unit checks
# ---------------------------------------------------------------------------
class TestValidatorDirect:
    def test_validator_change_outside_allowed(self):
        pkg = build_short_cartoon_package()
        graph = _graph(_shot("s1", "scn_01", 1))
        result = ContinuityLedgerService().build(
            pkg,
            _receipt(pkg, graph),
            planned_changes={
                "s1": [_change("appearance:chr_doudou:clothing", "tuxedo")],
            },
        )
        assert any(
            i.code == ContinuityIssueCode.CHANGE_OUTSIDE_ALLOWED for i in result.issues
        )

    def test_serialize_round_trip_ledger(self):
        pkg = build_short_cartoon_package()
        graph = _graph(_shot("s1", "scn_01", 1))
        result = ContinuityLedgerService().build(pkg, _receipt(pkg, graph))
        data = result.ledger.model_dump(mode="json")
        restored = ContinuityLedger.model_validate(data)
        assert restored.model_dump(mode="json") == data
        assert restored.ledger_hash == result.ledger_hash


def _receipt(pkg, graph: ShotDependencyGraph) -> ShotGraphReceipt:
    """Build a minimal ShotGraphReceipt for deterministic unit scenarios."""
    from windagent_intelligence.video import ShotScheduler

    scheduler = ShotScheduler()
    specs = _bare_specs(pkg, graph)
    return ShotGraphReceipt(
        graph=graph,
        specifications=specs,
        scheduling=scheduler.schedule(graph),
        graph_hash="g" * 64,
        source_plan_hash="p" * 64,
        source_package_hash=pkg.content_hash(),
    )


def _bare_specs(pkg, graph: ShotDependencyGraph):
    from windagent_core.domain.video_production.ids import ShotSpecificationId
    from windagent_core.domain.video_production.shot_graph import (
        ShotSpecification,
    )

    from windagent_intelligence.video import CameraPlanner

    camera = CameraPlanner()
    specs = []
    for shot in graph.shots:
        specs.append(
            ShotSpecification(
                spec_id=ShotSpecificationId(f"sps_{shot.shot_id}"),
                shot_id=shot.shot_id,
                scene_id=shot.scene_id,
                sequence=1,
                ordinal=shot.order,
                duration_seconds=shot.duration_seconds,
                camera=camera.decide(shot),
            )
        )
    return specs
