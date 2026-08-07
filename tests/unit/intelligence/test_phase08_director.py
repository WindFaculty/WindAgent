"""
Phase 8 — Director layer unit tests (plan 03 §10).

Covers:
- one-scene and multi-scene happy path;
- dialogue over duration creates an issue (not cut);
- locked screenplay is not mutated;
- unknown character/reference rejected (fail closed);
- total duration and shot order deterministic after validation;
- same fixture + deterministic model fake -> same plan hash;
- provider implementation is never called (only the planning model port).
"""

import pytest

from windagent_core.domain.video_production.director import (
    DirectorialIssueCategory,
)
from windagent_core.domain.video_production.enums import ScreenplayStatus
from windagent_core.domain.video_production.shot import CinematicPlan
from windagent_intelligence.video import VideoDirectorService
from windagent_intelligence.video.errors import (
    EmptyResponseError,
    ResponseParseError,
    ValidationFailureError,
)

from tests.fixtures.video_production.director_fixtures import (
    DeterministicDirectorModel,
    build_multi_scene_drama_package,
    build_pinned_planner_output,
    build_short_cartoon_package,
    build_two_character_dialogue_package,
)


def _service(plan_json: dict) -> VideoDirectorService:
    return VideoDirectorService(DeterministicDirectorModel(plan_json))


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------
class TestHappyPaths:
    async def test_port_contract_returns_cinematic_plan(self):
        pkg = build_short_cartoon_package()
        plan = await _service(build_pinned_planner_output(pkg)).create_cinematic_plan(pkg)

        assert isinstance(plan, CinematicPlan)
        assert plan.revision_id == pkg.revision_id

    async def test_one_scene_happy_path(self):
        pkg = build_short_cartoon_package()
        svc = _service(build_pinned_planner_output(pkg))
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        assert receipt.plan is not None
        assert len(receipt.plan.graph.shots) >= 1
        assert receipt.plan.project_id == pkg.project_id
        assert receipt.plan.revision_id == pkg.revision_id
        assert receipt.issues == []
        assert receipt.proposals == []
        # Every dialogue line bound, every scene covered.
        bound = {str(d) for s in receipt.plan.graph.shots for d in s.dialogue_line_ids}
        assert bound == {str(d.dialogue_id) for d in pkg.dialogue}
        scenes = {str(s.scene_id) for s in receipt.plan.graph.shots}
        assert scenes == {str(s) for s in pkg.screenplay.scene_ids}

    async def test_multi_scene_happy_path(self):
        pkg = build_multi_scene_drama_package()
        svc = _service(build_pinned_planner_output(pkg))
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        assert len(receipt.plan.graph.shots) >= 3
        assert receipt.issues == []
        assert len(receipt.plan.graph.dependencies) >= 2

    async def test_two_character_dialogue_happy_path(self):
        pkg = build_two_character_dialogue_package()
        svc = _service(build_pinned_planner_output(pkg))
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        assert len(receipt.plan.graph.shots) >= 4
        assert receipt.issues == []
        # VP3D Stage A: shots carry NO generation_mode; identity references are
        # bound by the reference selector instead (engine decides execution).


# ---------------------------------------------------------------------------
# Duration budget
# ---------------------------------------------------------------------------
class TestDurationBudget:
    async def test_dialogue_over_duration_creates_issue_not_cut(self):
        """Dialogue that exceeds its shot raises an issue; the line is bound anyway."""
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        # Shrink the first dialogue shot to 1 second so dialogue cannot fit.
        for shot in plan_json["shots"]:
            if shot["dialogue_line_ids"]:
                shot["duration_seconds"] = 1.0
        svc = _service(plan_json)
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        issue_cats = {i.category for i in receipt.issues}
        assert DirectorialIssueCategory.DIALOGUE_DURATION_MISMATCH in issue_cats
        # The dialogue is NOT cut: still bound to a shot.
        bound = {str(d) for s in receipt.plan.graph.shots for d in s.dialogue_line_ids}
        assert bound == {str(d.dialogue_id) for d in pkg.dialogue}
        # A proposal exists for the blocking issue (plan §9.3).
        assert any(p.source_issue_id in {i.issue_id for i in receipt.issues} for p in receipt.proposals)

    async def test_duration_overflow_raises_issue(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        for shot in plan_json["shots"]:
            shot["duration_seconds"] = 60.0  # way over the 20s target
        svc = _service(plan_json)
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        assert DirectorialIssueCategory.DURATION_OVERFLOW in {i.category for i in receipt.issues}


# ---------------------------------------------------------------------------
# Immutability / script revision protocol
# ---------------------------------------------------------------------------
class TestImmutability:
    async def test_locked_screenplay_not_mutated(self):
        pkg = build_short_cartoon_package()
        assert pkg.screenplay.status == ScreenplayStatus.LOCKED
        before_hash = pkg.content_hash()
        before_screenplay = pkg.screenplay.model_dump_json()

        svc = _service(build_pinned_planner_output(pkg))
        receipt = await svc.create_cinematic_plan_receipt(pkg)

        assert pkg.content_hash() == before_hash, "package must stay immutable"
        assert pkg.screenplay.model_dump_json() == before_screenplay, "screenplay must stay identical"
        assert receipt.plan.revision_id == pkg.revision_id
        assert receipt.plan.metadata["screenplay_locked"] is True

    async def test_draft_screenplay_rejected_by_default(self):
        pkg = build_short_cartoon_package()
        pkg = pkg.model_copy(
            update={"screenplay": pkg.screenplay.model_copy(update={"status": ScreenplayStatus.DRAFT})}
        )
        svc = _service(build_pinned_planner_output(pkg))
        with pytest.raises(ValidationFailureError):
            await svc.create_cinematic_plan_receipt(pkg)

    async def test_lock_shot_plan_returns_locked_copy(self):
        pkg = build_short_cartoon_package()
        svc = _service(build_pinned_planner_output(pkg))
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        assert receipt.plan.locked is False
        locked = await svc.lock_shot_plan(receipt.plan)
        assert locked.locked is True
        assert receipt.plan.locked is False  # input never mutated


# ---------------------------------------------------------------------------
# Fail closed on unknown references
# ---------------------------------------------------------------------------
class TestUnknownReferences:
    async def test_unknown_character_rejected(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        plan_json["scene_objectives"][0]["scene_id"] = "scn_does_not_exist"
        svc = _service(plan_json)
        with pytest.raises(ValidationFailureError) as exc:
            await svc.create_cinematic_plan_receipt(pkg)
        assert "unknown" in str(exc.value)

    async def test_unknown_dialogue_rejected(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        plan_json["shots"][1]["dialogue_line_ids"] = ["dlg_ghost_line"]
        svc = _service(plan_json)
        with pytest.raises(ValidationFailureError):
            await svc.create_cinematic_plan_receipt(pkg)

    async def test_missing_coverage_rejected(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        # Drop ALL shots so a scene has no coverage -> fail closed.
        plan_json["shots"] = []
        svc = _service(plan_json)
        with pytest.raises(ValidationFailureError) as exc:
            await svc.create_cinematic_plan_receipt(pkg)
        assert "no planned shot" in str(exc.value)

    async def test_unbound_dialogue_rejected(self):
        pkg = build_short_cartoon_package()
        plan_json = build_pinned_planner_output(pkg)
        for shot in plan_json["shots"]:
            shot["dialogue_line_ids"] = []
        svc = _service(plan_json)
        with pytest.raises(ValidationFailureError) as exc:
            await svc.create_cinematic_plan_receipt(pkg)
        assert "not bound" in str(exc.value)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
class TestDeterminism:
    async def test_shot_order_deterministic(self):
        pkg = build_multi_scene_drama_package()
        plan_json = build_pinned_planner_output(pkg)
        svc = _service(plan_json)
        receipt = await svc.create_cinematic_plan_receipt(pkg)
        # Shot order is deterministic within each scene (orders restart per scene).
        by_scene: dict[str, list[int]] = {}
        for shot in receipt.plan.graph.shots:
            by_scene.setdefault(str(shot.scene_id), []).append(shot.order)
        for scene_id, orders in by_scene.items():
            assert orders == sorted(orders), f"{scene_id}: {orders}"
            assert len(set(orders)) == len(orders), f"duplicate orders in {scene_id}"

    async def test_same_fixture_same_plan_hash(self):
        pkg = build_two_character_dialogue_package()
        plan_json = build_pinned_planner_output(pkg)
        r1 = await _service(plan_json).create_cinematic_plan_receipt(pkg)
        r2 = await _service(plan_json).create_cinematic_plan_receipt(pkg)
        assert r1.plan_hash == r2.plan_hash
        assert r1.plan.model_dump_json() == r2.plan.model_dump_json()

    async def test_changed_reference_changes_hash(self):
        pkg = build_two_character_dialogue_package()
        plan_json = build_pinned_planner_output(pkg)
        r1 = await _service(plan_json).create_cinematic_plan_receipt(pkg)
        # Bind an EXISTING approved asset to the establishing shot -> new hash.
        plan_json["shots"][0]["reference_asset_ids"].append("ast_minh")
        r2 = await _service(plan_json).create_cinematic_plan_receipt(pkg)
        assert r1.plan_hash != r2.plan_hash


# ---------------------------------------------------------------------------
# Provider neutrality / typed failures
# ---------------------------------------------------------------------------
class TestProviderNeutrality:
    async def test_provider_implementation_never_called(self):
        pkg = build_short_cartoon_package()
        port = DeterministicDirectorModel(build_pinned_planner_output(pkg))
        svc = VideoDirectorService(port)
        await svc.create_cinematic_plan_receipt(pkg)
        # The only capability the director may call is the planning model port.
        assert port.calls == ["cinematic_planning"]

    async def test_invalid_structured_output_typed_failure(self):
        pkg = build_short_cartoon_package()
        port = DeterministicDirectorModel({"not": "a planner output"})
        svc = VideoDirectorService(port)
        with pytest.raises(ResponseParseError):
            await svc.create_cinematic_plan_receipt(pkg)

    async def test_empty_response_typed_failure(self):
        from windagent_intelligence.video.ports import ModelCompletionResult

        class EmptyModel:
            async def complete(self, request):
                return ModelCompletionResult(capability=request.capability, content="", provider="fake")

        pkg = build_short_cartoon_package()
        svc = VideoDirectorService(EmptyModel())
        with pytest.raises(EmptyResponseError):
            await svc.create_cinematic_plan_receipt(pkg)
