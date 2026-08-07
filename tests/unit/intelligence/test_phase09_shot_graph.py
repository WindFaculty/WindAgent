"""
Phase 9 — Shot dependency graph & camera planning unit tests (plan 03 §15).

Covers:
- cycle / missing node / duplicate ID / self-edge / invalid cross-scene dep;
- stable topological order;
- tail-frame / transition dependencies create the correct required artifact;
- independent shots are identified (parallel-capable);
- camera side and screen direction constraints (plan §14.2);
- serialize/round-trip the graph.

Generation-mode decision logic was retired in VP3D Stage A (see
legacy_v1/SUNSET.md) — the engine adapter decides execution from the IR.
"""

import pytest

from windagent_core.domain.video_production.enums import (
    CameraDecisionReasonCode,
    DependencyType,
    RequiredArtifactType,
    ScreenDirection,
    ShotGraphIssueCode,
    ShotType,
)
from windagent_core.domain.video_production.errors import (
    ShotDependencyGraphCycleError,
)
from windagent_core.domain.video_production.ids import (
    SceneId,
    ShotDependencyId,
    ShotId,
)
from windagent_core.domain.video_production.shot import (
    Shot,
    ShotDependency,
    ShotDependencyGraph,
)
from windagent_core.domain.video_production.shot_graph import (
    CameraDecision,
    ShotDependencyGraphValidator,
)
from windagent_intelligence.video import (
    CameraPlanner,
    ShotGraphPlannerService,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory

from tests.fixtures.video_production.director_fixtures import (
    DeterministicDirectorModel,
    build_multi_scene_drama_package,
    build_pinned_planner_output,
    build_short_cartoon_package,
    build_two_character_dialogue_package,
)
from windagent_intelligence.video import VideoDirectorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _planned_graph(builder, *, max_parallel: int = 2) -> dict:
    """Run Phase 8 director + Phase 9 shot graph planner for a fixture."""
    pkg = builder()
    plan_json = build_pinned_planner_output(pkg)
    director = VideoDirectorService(DeterministicDirectorModel(plan_json))
    receipt = await director.create_cinematic_plan_receipt(pkg)
    locked = await director.lock_shot_plan(receipt.plan)
    svc = ShotGraphPlannerService()
    graph_receipt = svc.plan(
        pkg,
        locked,
        production_max_parallel=max_parallel,
    )
    return {"pkg": pkg, "director": director, "plan": locked, "result": graph_receipt}


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


# ---------------------------------------------------------------------------
# Graph validation (plan §13)
# ---------------------------------------------------------------------------
class TestGraphValidation:
    def test_duplicate_node_id_detected(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s1", "scn1", 2)],
            dependencies=[],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        codes = {i.code for i in issues}
        assert ShotGraphIssueCode.DUPLICATE_NODE_ID in codes
        assert all(i.blocking for i in issues)

    def test_duplicate_edge_id_detected(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s2", "scn1", 2)],
            dependencies=[
                _dep("e1", "s1", "s2"),
                _dep("e1", "s1", "s2"),
            ],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        assert ShotGraphIssueCode.DUPLICATE_EDGE_ID in {i.code for i in issues}

    def test_missing_node_detected(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1)],
            dependencies=[_dep("e1", "s1", "ghost")],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        assert ShotGraphIssueCode.MISSING_NODE in {i.code for i in issues}

    def test_self_edge_detected(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1)],
            dependencies=[_dep("e1", "s1", "s1")],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        assert ShotGraphIssueCode.SELF_EDGE in {i.code for i in issues}

    def test_blocking_cycle_fails_closed(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s2", "scn1", 2)],
            dependencies=[
                _dep("e1", "s1", "s2", blocking=True),
                _dep("e2", "s2", "s1", blocking=True),
            ],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        assert ShotGraphIssueCode.BLOCKING_CYCLE in {i.code for i in issues}
        # Fail closed: a cycle in the blocking subgraph is never published.
        with pytest.raises(ShotDependencyGraphCycleError):
            graph.topological_order()
        assert graph.has_cycle() is True

    def test_invalid_cross_scene_temporal_rejected(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s2", "scn2", 1)],
            dependencies=[
                _dep("e1", "s1", "s2", dependency_type=DependencyType.TEMPORAL),
            ],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        assert ShotGraphIssueCode.INVALID_CROSS_SCENE in {i.code for i in issues}

    def test_valid_graph_has_no_blocking_issues(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s2", "scn1", 2)],
            dependencies=[
                _dep("e1", "s1", "s2", blocking=True),
            ],
        )
        issues = ShotDependencyGraphValidator().validate(graph)
        assert issues == []

    def test_topological_order_stable(self):
        graph = ShotDependencyGraph(
            shots=[
                _shot("s1", "scn1", 1),
                _shot("s2", "scn1", 2),
                _shot("s3", "scn2", 1),
            ],
            dependencies=[
                _dep("e1", "s1", "s2", blocking=True),
                _dep("e2", "s1", "s3", blocking=True),
            ],
        )
        order1 = [str(s) for s in graph.topological_order()]
        order2 = [str(s) for s in graph.topological_order()]
        assert order1 == order2
        assert order1.index("s1") < order1.index("s2")
        assert order1.index("s1") < order1.index("s3")

    def test_independent_shots_identified(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s2", "scn1", 2), _shot("s3", "scn1", 3)],
            dependencies=[
                _dep("e1", "s1", "s3", blocking=True),
            ],
        )
        independent = {str(s) for s in graph.independent_shot_ids()}
        assert independent == {"s1", "s2"}

    def test_serialize_round_trip(self):
        graph = ShotDependencyGraph(
            shots=[_shot("s1", "scn1", 1), _shot("s2", "scn1", 2)],
            dependencies=[
                _dep(
                    "e1",
                    "s1",
                    "s2",
                    blocking=True,
                    required_artifact_type=RequiredArtifactType.TAIL_FRAME,
                ),
            ],
        )
        data = graph.model_dump(mode="json")
        restored = ShotDependencyGraph.model_validate(data)
        assert restored.model_dump(mode="json") == data
        assert restored.dependencies[0].required_artifact_type == RequiredArtifactType.TAIL_FRAME


# ---------------------------------------------------------------------------
# Service-level behavior on the three fixtures
# ---------------------------------------------------------------------------
class TestServiceHappyPaths:
    async def test_short_cartoon_typed_graph(self):
        out = await _planned_graph(build_short_cartoon_package)
        result = out["result"]
        assert result.graph.shots
        assert result.graph.dependencies
        types = {d.dependency_type for d in result.graph.dependencies}
        assert DependencyType.TEMPORAL in types
        assert result.graph.has_cycle() is False
        assert result.issues == [] or all(not i.blocking for i in result.issues)
        # Every shot has a specification with camera + scheduling metadata
        # (generation-mode decisions were retired in VP3D Stage A).
        assert len(result.specifications) == len(result.graph.shots)
        for spec in result.specifications:
            assert spec.camera.reason_code

    async def test_dialogue_fixture_dialogue_and_continuity(self):
        out = await _planned_graph(build_two_character_dialogue_package)
        result = out["result"]
        types = {d.dependency_type for d in result.graph.dependencies}
        # Dialogue flow edges exist (multiple dialogue shots).
        assert DependencyType.DIALOGUE in types
        # Every specification carries a camera decision (no generation mode).
        assert all(s.camera.reason_code for s in result.specifications)
        # Continuity edges carry TAIL_FRAME (tail-frame dependency).
        continuity = [
            d for d in result.graph.dependencies
            if d.dependency_type == DependencyType.CONTINUITY and d.blocking
        ]
        assert all(d.required_artifact_type == RequiredArtifactType.TAIL_FRAME for d in continuity)

    async def test_multi_scene_no_cross_scene_temporal(self):
        out = await _planned_graph(build_multi_scene_drama_package)
        result = out["result"]
        for dep in result.graph.dependencies:
            from_scene = next(s.scene_id for s in result.graph.shots if s.shot_id == dep.from_shot_id)
            to_scene = next(s.scene_id for s in result.graph.shots if s.shot_id == dep.to_shot_id)
            if dep.dependency_type == DependencyType.TEMPORAL:
                assert from_scene == to_scene

    async def test_graph_hash_deterministic(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = await director.create_cinematic_plan_receipt(pkg)
        locked = await director.lock_shot_plan(receipt.plan)
        r1 = ShotGraphPlannerService().plan(pkg, locked)
        r2 = ShotGraphPlannerService().plan(pkg, locked)
        assert r1.graph_hash == r2.graph_hash
        assert r1.graph.model_dump_json() == r2.graph.model_dump_json()

    async def test_graph_hash_changes_with_plan(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = await director.create_cinematic_plan_receipt(pkg)
        r1 = ShotGraphPlannerService().plan(pkg, receipt.plan, require_locked=False)
        # Adding an approved location reference changes the graph payload.
        plan_json["shots"][1]["reference_asset_ids"].append("ast_forest")
        director2 = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt2 = await director2.create_cinematic_plan_receipt(pkg)
        r2 = ShotGraphPlannerService().plan(pkg, receipt2.plan, require_locked=False)
        assert r1.graph_hash != r2.graph_hash

    async def test_unlocked_plan_rejected_by_default(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = await director.create_cinematic_plan_receipt(pkg)
        assert receipt.plan.locked is False
        svc = ShotGraphPlannerService()
        with pytest.raises(ValidationFailureError):
            svc.plan(pkg, receipt.plan)  # require_locked defaults True

    async def test_structural_cycle_fails_closed_in_service(self):
        """A builder that emits a blocking cycle must fail closed in the service."""
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = await director.create_cinematic_plan_receipt(pkg)
        locked = await director.lock_shot_plan(receipt.plan)

        class CyclicBuilder:
            def build(self, package, shots):
                s = list(shots)
                a, b = s[0], s[1]
                return ShotDependencyGraph(
                    shots=s,
                    dependencies=[
                        _dep("cyc1", str(a.shot_id), str(b.shot_id), blocking=True),
                        _dep("cyc2", str(b.shot_id), str(a.shot_id), blocking=True),
                    ],
                )

        svc = ShotGraphPlannerService(graph_builder=CyclicBuilder())
        with pytest.raises(ValidationFailureError):
            svc.plan(pkg, locked)


# ---------------------------------------------------------------------------
# Camera rules (plan §14.2)
# ---------------------------------------------------------------------------
class TestCameraRules:
    def test_camera_reason_code_present(self):
        planner = CameraPlanner()
        shot = _shot("s1", "scn1", 1, shot_type=ShotType.ESTABLISHING)
        decision = planner.decide(shot)
        assert decision.reason_code == CameraDecisionReasonCode.ESTABLISH_GEOGRAPHY
        assert decision.camera_side.value == "NEUTRAL"

    def test_establishing_before_coverage_reason(self):
        planner = CameraPlanner()
        coverage = _shot("s2", "scn1", 2, shot_type=ShotType.CLOSE_UP)
        decision = planner.decide(coverage)
        assert decision.reason_code in (
            CameraDecisionReasonCode.DIALOGUE_ALIGNMENT,
            CameraDecisionReasonCode.EMOTIONAL_BEAT,
        )
        assert decision.camera_side.value == "SIDE_A"

    def test_screen_direction_flip_detected(self):
        planner = CameraPlanner(id_factory=StableIdFactory())
        shots = [
            _shot("s1", "scn1", 1, shot_type=ShotType.MEDIUM),
            _shot("s2", "scn1", 2, shot_type=ShotType.MEDIUM),
        ]
        camera_by_shot = {
            "s1": CameraDecision(screen_direction=ScreenDirection.LEFT_TO_RIGHT, reason_code=CameraDecisionReasonCode.ACTION_FOLLOW),
            "s2": CameraDecision(screen_direction=ScreenDirection.RIGHT_TO_LEFT, reason_code=CameraDecisionReasonCode.ACTION_FOLLOW),
        }
        issues = planner.validate(
            shots_by_scene={"scn1": shots},
            camera_by_shot=camera_by_shot,
        )
        assert ShotGraphIssueCode.SCREEN_DIRECTION_FLIP in {i.code for i in issues}

    def test_movement_too_short_detected(self):
        planner = CameraPlanner(id_factory=StableIdFactory())
        from windagent_core.domain.video_production.enums import CameraMovement

        shots = [
            _shot("s1", "scn1", 1, shot_type=ShotType.MEDIUM,
                  camera_movement=CameraMovement.TRACK, duration_seconds=0.5),
        ]
        camera_by_shot = {
            "s1": CameraDecision(
                camera_movement=CameraMovement.TRACK,
                reason_code=CameraDecisionReasonCode.ACTION_FOLLOW,
            ),
        }
        issues = planner.validate(
            shots_by_scene={"scn1": shots},
            camera_by_shot=camera_by_shot,
        )
        assert ShotGraphIssueCode.MOVEMENT_TOO_SHORT in {i.code for i in issues}

    def test_180_degree_side_flip_detected(self):
        planner = CameraPlanner(id_factory=StableIdFactory())
        from windagent_core.domain.video_production.enums import CameraSide

        shots = [
            _shot("s1", "scn1", 1, shot_type=ShotType.MEDIUM),
            _shot("s2", "scn1", 2, shot_type=ShotType.MEDIUM),
        ]
        camera_by_shot = {
            "s1": CameraDecision(camera_side=CameraSide.SIDE_A, reason_code=CameraDecisionReasonCode.ACTION_FOLLOW),
            "s2": CameraDecision(camera_side=CameraSide.SIDE_B, reason_code=CameraDecisionReasonCode.ACTION_FOLLOW),
        }
        issues = planner.validate(
            shots_by_scene={"scn1": shots},
            camera_by_shot=camera_by_shot,
        )
        assert ShotGraphIssueCode.CAMERA_SIDE_VIOLATION in {i.code for i in issues}

    def test_reaction_without_source_detected(self):
        planner = CameraPlanner(id_factory=StableIdFactory())
        shots = [
            _shot("s1", "scn1", 1, shot_type=ShotType.REACTION),
        ]
        camera_by_shot = {
            "s1": CameraDecision(reason_code=CameraDecisionReasonCode.REACTION_BEAT),
        }
        issues = planner.validate(
            shots_by_scene={"scn1": shots},
            camera_by_shot=camera_by_shot,
        )
        assert ShotGraphIssueCode.REACTION_MISSING_SOURCE in {i.code for i in issues}

    def test_fixture_plans_have_no_camera_warnings(self):
        # The pinned fixture plans are camera-clean (no flips / no short moves).
        import asyncio

        pkg = build_two_character_dialogue_package()
        plan_json = build_pinned_planner_output(pkg)
        director = VideoDirectorService(DeterministicDirectorModel(plan_json))
        receipt = asyncio.run(director.create_cinematic_plan_receipt(pkg))
        locked = asyncio.run(director.lock_shot_plan(receipt.plan))
        result = ShotGraphPlannerService().plan(pkg, locked)
        camera_issues = [i for i in result.issues
                         if i.code in (ShotGraphIssueCode.CAMERA_SIDE_VIOLATION,
                                       ShotGraphIssueCode.SCREEN_DIRECTION_FLIP,
                                       ShotGraphIssueCode.MOVEMENT_TOO_SHORT,
                                       ShotGraphIssueCode.REACTION_MISSING_SOURCE)]
        assert camera_issues == []
