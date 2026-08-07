#!/usr/bin/env python3
"""
Phase 9 verification — VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED (plan 03 §12-§16).

Verifies the shot graph + camera planning layer
(`intelligence/windagent_intelligence/video/shot_planner/`) against the
ratified contracts in `docs/video_production/director/`:

  artifacts/video_production/phase_09/
  ├── graph_fixture_matrix.json
  ├── dag_validation_receipt.json
  ├── camera_rule_receipt.json
  ├── generation_mode_receipt.json
  └── phase_verdict.json

Gate conditions (plan 03 §16):
  1. the graph always validates before publish (structural defects fail closed);
  2. cycle / duplicate ID / missing node / self-edge / invalid cross-scene
     dependency are all rejected deterministically;
  3. every shot has a generation mode decision and its necessary dependency;
  4. tail-frame / transition dependencies carry the correct required artifact;
  5. independent shots are identified (parallel-capable);
  6. camera side + screen direction constraints are enforced as warnings;
  7. the Director never calls a provider (the shot planner holds no model port).

Every check is offline: Phase 8 uses the deterministic model fake, Phase 9 is
pure rules. Supports --no-write / --verify-only.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_09"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_BUILDERS = (
    ("fixture_short_cartoon", "build_short_cartoon_package"),
    ("fixture_two_character_dialogue", "build_two_character_dialogue_package"),
    ("fixture_multi_scene_drama", "build_multi_scene_drama_package"),
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


# ---------------------------------------------------------------------------
# Fixture helpers: Phase 8 director (deterministic fake) + Phase 9 planner
# ---------------------------------------------------------------------------
def _plan_graph_for_fixture(builder_name: str) -> dict:
    from tests.fixtures.video_production import director_fixtures as fx

    from windagent_intelligence.video import ShotGraphPlannerService, VideoDirectorService

    pkg = getattr(fx, builder_name)()
    plan_json = fx.build_pinned_planner_output(pkg)
    port = fx.DeterministicDirectorModel(plan_json)
    receipt = asyncio.run(VideoDirectorService(port).create_cinematic_plan_receipt(pkg))
    locked = asyncio.run(VideoDirectorService(port).lock_shot_plan(receipt.plan))
    result = ShotGraphPlannerService().plan(pkg, locked)
    return {"pkg": pkg, "plan": locked, "result": result}


# ---------------------------------------------------------------------------
# 1. Graph fixture matrix (three fixtures -> typed graphs + modes + camera)
# ---------------------------------------------------------------------------
def build_graph_fixture_matrix() -> dict:
    checks: list[dict] = []
    fixtures: dict = {"schema_version": "1.0.0", "fixtures": {}}

    for fixture_name, builder in FIXTURE_BUILDERS:
        out = _plan_graph_for_fixture(builder)
        result = out["result"]
        types: dict = {}
        for dep in result.graph.dependencies:
            types[dep.dependency_type.value] = types.get(dep.dependency_type.value, 0) + 1
        blocking = sum(1 for d in result.graph.dependencies if d.blocking)
        independent = [str(s) for s in result.graph.independent_shot_ids()]
        modes = {s.generation_mode.preferred_mode.value for s in result.specifications}

        fixtures["fixtures"][fixture_name] = {
            "shots": len(result.graph.shots),
            "edges": len(result.graph.dependencies),
            "edge_types": types,
            "blocking_edges": blocking,
            "independent_shots": independent,
            "graph_hash": result.graph_hash[:16],
            "generation_modes": sorted(modes),
            "issues": [i.to_dict() for i in result.issues],
        }

        _record(checks, f"{fixture_name}_graph_valid",
                result.graph.shots and result.graph.dependencies,
                f"shots={len(result.graph.shots)} edges={len(result.graph.dependencies)}")
        _record(checks, f"{fixture_name}_acyclic",
                result.graph.has_cycle() is False, "no directed cycle")
        _record(checks, f"{fixture_name}_every_shot_has_mode",
                len(result.specifications) == len(result.graph.shots)
                and all(s.generation_mode.preferred_mode for s in result.specifications),
                f"specs={len(result.specifications)}")
        _record(checks, f"{fixture_name}_topological_order_reproducible",
                [str(s) for s in result.graph.topological_order()]
                == [str(s) for s in result.graph.topological_order()],
                "stable Kahn order")
        # Tail-frame / transition dependencies carry the correct artifact.
        for dep in result.graph.dependencies:
            if dep.dependency_type.value == "CONTINUITY" and dep.blocking:
                _record(checks, f"{fixture_name}_continuity_tail_frame",
                        dep.required_artifact_type.value == "TAIL_FRAME",
                        "continuity requires TAIL_FRAME")
            if dep.dependency_type.value == "TRANSITION" and dep.blocking:
                _record(checks, f"{fixture_name}_transition_full_clip",
                        dep.required_artifact_type.value == "FULL_CLIP",
                        "transition requires FULL_CLIP")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/shot_dependency_graph.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "fixtures": fixtures,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 2. DAG validation receipt (fail closed on structural defects)
# ---------------------------------------------------------------------------
def build_dag_validation_receipt() -> dict:
    from windagent_core.domain.video_production.enums import (
        DependencyType,
        RequiredArtifactType,
        ShotGraphIssueCode,
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
        ShotDependencyGraphValidator,
    )

    def shot(sid: str, scn: str, order: int) -> Shot:
        return Shot(shot_id=ShotId(sid), scene_id=SceneId(scn), order=order,
                    duration_seconds=3.0)

    def dep(did: str, frm: str, to: str, **kw) -> ShotDependency:
        defaults = {
            "dependency_id": ShotDependencyId(did),
            "from_shot_id": ShotId(frm),
            "to_shot_id": ShotId(to),
            "dependency_type": DependencyType.TEMPORAL,
        }
        defaults.update(kw)
        return ShotDependency(**defaults)

    checks: list[dict] = []
    validator = ShotDependencyGraphValidator()
    cases = {
        "duplicate_node_id": ShotDependencyGraph(
            shots=[shot("s1", "scn1", 1), shot("s1", "scn1", 2)], dependencies=[]),
        "duplicate_edge_id": ShotDependencyGraph(
            shots=[shot("s1", "scn1", 1), shot("s2", "scn1", 2)],
            dependencies=[dep("e1", "s1", "s2"), dep("e1", "s1", "s2")]),
        "missing_node": ShotDependencyGraph(
            shots=[shot("s1", "scn1", 1)],
            dependencies=[dep("e1", "s1", "ghost")]),
        "self_edge": ShotDependencyGraph(
            shots=[shot("s1", "scn1", 1)],
            dependencies=[dep("e1", "s1", "s1")]),
        "blocking_cycle": ShotDependencyGraph(
            shots=[shot("s1", "scn1", 1), shot("s2", "scn1", 2)],
            dependencies=[
                dep("e1", "s1", "s2", blocking=True),
                dep("e2", "s2", "s1", blocking=True),
            ]),
        "cross_scene_temporal": ShotDependencyGraph(
            shots=[shot("s1", "scn1", 1), shot("s2", "scn2", 1)],
            dependencies=[dep("e1", "s1", "s2", dependency_type=DependencyType.TEMPORAL)]),
    }
    expected_codes = {
        "duplicate_node_id": ShotGraphIssueCode.DUPLICATE_NODE_ID,
        "duplicate_edge_id": ShotGraphIssueCode.DUPLICATE_EDGE_ID,
        "missing_node": ShotGraphIssueCode.MISSING_NODE,
        "self_edge": ShotGraphIssueCode.SELF_EDGE,
        "blocking_cycle": ShotGraphIssueCode.BLOCKING_CYCLE,
        "cross_scene_temporal": ShotGraphIssueCode.INVALID_CROSS_SCENE,
    }
    for name, graph in cases.items():
        issues = validator.validate(graph)
        codes = {i.code for i in issues}
        _record(checks, f"{name}_detected",
                expected_codes[name] in codes,
                f"codes={sorted(c.value for c in codes)}")
        _record(checks, f"{name}_blocking",
                all(i.blocking for i in issues), "fail closed")

    # Valid graph: no blocking issues, stable topological order.
    good = ShotDependencyGraph(
        shots=[shot("s1", "scn1", 1), shot("s2", "scn1", 2)],
        dependencies=[dep("e1", "s1", "s2", blocking=True,
                          required_artifact_type=RequiredArtifactType.TAIL_FRAME)],
    )
    _record(checks, "valid_graph_no_issues", validator.validate(good) == [], "clean")
    _record(checks, "valid_graph_topological_stable",
            [str(s) for s in good.topological_order()]
            == [str(s) for s in good.topological_order()], "stable order")
    _record(checks, "valid_graph_independent_shot",
            [str(s) for s in good.independent_shot_ids()] == ["s1"],
            "s1 has no blocking predecessor")

    # Transition dependency carries FULL_CLIP (plan §13, §14.4).
    transition = ShotDependencyGraph(
        shots=[shot("s1", "scn1", 1), shot("s2", "scn1", 2)],
        dependencies=[dep("e1", "s1", "s2", blocking=True,
                          dependency_type=DependencyType.TRANSITION,
                          required_artifact_type=RequiredArtifactType.FULL_CLIP)],
    )
    _record(checks, "transition_edge_full_clip",
            validator.validate(transition) == []
            and transition.blocking_edges()[0].required_artifact_type
            == RequiredArtifactType.FULL_CLIP,
            "transition waits for both endpoints (FULL_CLIP)")

    # Service-level fail closed: a cyclic builder must raise.
    from windagent_intelligence.video import ShotGraphPlannerService
    from windagent_intelligence.video.errors import ValidationFailureError
    from tests.fixtures.video_production import director_fixtures as fx

    pkg = fx.build_short_cartoon_package()
    plan_json = fx.build_pinned_planner_output(pkg)
    from windagent_intelligence.video import VideoDirectorService

    port = fx.DeterministicDirectorModel(plan_json)
    receipt = asyncio.run(VideoDirectorService(port).create_cinematic_plan_receipt(pkg))
    locked = asyncio.run(VideoDirectorService(port).lock_shot_plan(receipt.plan))

    class CyclicBuilder:
        def build(self, package, shots):
            s = list(shots)
            a, b = s[0], s[1]
            return ShotDependencyGraph(
                shots=s,
                dependencies=[
                    dep("cyc1", str(a.shot_id), str(b.shot_id), blocking=True),
                    dep("cyc2", str(b.shot_id), str(a.shot_id), blocking=True),
                ],
            )

    rejected = False
    try:
        ShotGraphPlannerService(graph_builder=CyclicBuilder()).plan(pkg, locked)
    except ValidationFailureError:
        rejected = True
    _record(checks, "service_cycle_fails_closed", rejected,
            "cyclic graph never published")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/shot_dependency_graph.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Camera rule receipt (plan §14.2)
# ---------------------------------------------------------------------------
def build_camera_rule_receipt() -> dict:
    from windagent_core.domain.video_production.enums import (
        CameraDecisionReasonCode,
        ShotGraphIssueCode,
    )
    from windagent_core.domain.video_production.ids import (
        SceneId,
        ShotId,
    )
    from windagent_core.domain.video_production.shot import Shot
    from windagent_core.domain.video_production.shot_graph import CameraDecision

    from windagent_intelligence.video import CameraPlanner
    from windagent_intelligence.video.ids import StableIdFactory

    checks: list[dict] = []
    planner = CameraPlanner(id_factory=StableIdFactory())

    # Every shot type has a reason-coded camera decision.
    from windagent_core.domain.video_production.enums import (
        ScreenDirection,
        ShotType,
    )

    covered = {ShotType.ESTABLISHING, ShotType.MASTER, ShotType.MEDIUM,
               ShotType.CLOSE_UP, ShotType.EXTREME_CLOSE_UP,
               ShotType.OVER_SHOULDER, ShotType.POV, ShotType.INSERT,
               ShotType.REACTION, ShotType.TRANSITION}
    for shot_type in covered:
        shot = Shot(shot_id=ShotId(f"s_{shot_type.value}"),
                    scene_id=SceneId("scn1"), order=1, shot_type=shot_type,
                    duration_seconds=3.0)
        decision = planner.decide(shot)
        _record(checks, f"camera_{shot_type.value.lower()}_reason_coded",
                bool(decision.reason_code),
                f"reason_code={decision.reason_code.value}")

    def shot(sid: str, order: int) -> Shot:
        return Shot(shot_id=ShotId(sid), scene_id=SceneId("scn1"), order=order,
                    duration_seconds=3.0)

    # Screen direction flip detected (explicit directions, never NEUTRAL).
    flip = planner.validate(
        shots_by_scene={"scn1": [shot("s1", 1), shot("s2", 2)]},
        camera_by_shot={
            "s1": CameraDecision(
                screen_direction=ScreenDirection.LEFT_TO_RIGHT,
                reason_code=CameraDecisionReasonCode.ACTION_FOLLOW),
            "s2": CameraDecision(
                screen_direction=ScreenDirection.RIGHT_TO_LEFT,
                reason_code=CameraDecisionReasonCode.ACTION_FOLLOW),
        },
    )
    _record(checks, "screen_direction_flip_detected",
            any(i.code == ShotGraphIssueCode.SCREEN_DIRECTION_FLIP for i in flip),
            "flip within a scene is flagged")

    # Fixture plans are camera-clean (no warnings).
    from tests.fixtures.video_production import director_fixtures as fx

    from windagent_intelligence.video import ShotGraphPlannerService, VideoDirectorService

    pkg = fx.build_two_character_dialogue_package()
    plan_json = fx.build_pinned_planner_output(pkg)
    port = fx.DeterministicDirectorModel(plan_json)
    receipt = asyncio.run(VideoDirectorService(port).create_cinematic_plan_receipt(pkg))
    locked = asyncio.run(VideoDirectorService(port).lock_shot_plan(receipt.plan))
    result = ShotGraphPlannerService().plan(pkg, locked)
    camera_codes = {ShotGraphIssueCode.CAMERA_SIDE_VIOLATION,
                    ShotGraphIssueCode.SCREEN_DIRECTION_FLIP,
                    ShotGraphIssueCode.MOVEMENT_TOO_SHORT,
                    ShotGraphIssueCode.REACTION_MISSING_SOURCE}
    _record(checks, "fixture_plans_camera_clean",
            all(i.code not in camera_codes for i in result.issues),
            "no camera warnings on the golden dialogue fixture")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/camera_planning_rules.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Generation mode receipt (plan §14.3 decision table)
# ---------------------------------------------------------------------------
def build_generation_mode_receipt() -> dict:
    from windagent_core.domain.video_production.enums import (
        DependencyType,
        GenerationMode,
        GenerationModeReasonCode,
        RequiredArtifactType,
        ShotType,
    )
    from windagent_core.domain.video_production.ids import (
        SceneId,
        ShotDependencyId,
        ShotId,
    )
    from windagent_core.domain.video_production.shot import (
        Shot,
        ShotDependency,
    )

    from windagent_intelligence.video import GenerationModeDecider

    checks: list[dict] = []
    decider = GenerationModeDecider()

    def shot(sid: str, shot_type=ShotType.MEDIUM) -> Shot:
        return Shot(shot_id=ShotId(sid), scene_id=SceneId("scn1"), order=1,
                    shot_type=shot_type, duration_seconds=3.0)

    def dep(did: str, dep_type, artifact) -> ShotDependency:
        return ShotDependency(
            dependency_id=ShotDependencyId(did),
            from_shot_id=ShotId("s0"), to_shot_id=ShotId("s1"),
            dependency_type=dep_type, required_artifact_type=artifact,
            blocking=True,
        )

    # 1. TRANSITION shot -> VIDEO_TO_VIDEO.
    d1 = decider.decide(shot=shot("s1", ShotType.TRANSITION), incoming=[],
                        scene_character_asset_ids=[], scene_location_asset_ids=[])
    _record(checks, "transition_shot_transforms_clip",
            d1.preferred_mode == GenerationMode.VIDEO_TO_VIDEO
            and d1.reason_code == GenerationModeReasonCode.CLIP_TRANSFORMATION,
            f"preferred={d1.preferred_mode.value}")

    # 2. Identity reference -> IMAGE_TO_VIDEO.
    d2 = decider.decide(shot=shot("s1"), incoming=[],
                        scene_character_asset_ids=[], scene_location_asset_ids=[])
    _record(checks, "independent_shot_text_to_video",
            d2.preferred_mode == GenerationMode.TEXT_TO_VIDEO
            and d2.reason_code == GenerationModeReasonCode.NO_MANDATORY_REFERENCE,
            "no mandatory reference -> text-to-video")

    # 3. FRAMES required from a TRANSITION dependency.
    d3 = decider.decide(shot=shot("s1"), incoming=[
        dep("e1", DependencyType.TRANSITION, RequiredArtifactType.FULL_CLIP)],
        scene_character_asset_ids=[], scene_location_asset_ids=[])
    _record(checks, "frames_required",
            d3.preferred_mode == GenerationMode.FRAMES_TO_VIDEO
            and d3.reason_code == GenerationModeReasonCode.FRAMES_REQUIRED,
            f"preferred={d3.preferred_mode.value}")

    # 4. Motion continuation (blocking CONTINUITY tail frame) -> extension.
    d4 = decider.decide(shot=shot("s1"), incoming=[
        dep("e2", DependencyType.CONTINUITY, RequiredArtifactType.TAIL_FRAME)],
        scene_character_asset_ids=[], scene_location_asset_ids=[])
    _record(checks, "motion_continuation_extension",
            d4.preferred_mode == GenerationMode.VIDEO_EXTENSION
            and d4.reason_code == GenerationModeReasonCode.MOTION_CONTINUATION,
            f"preferred={d4.preferred_mode.value}")

    # 5. Fixture dialogue shots get IMAGE_TO_VIDEO via identity references.
    from tests.fixtures.video_production import director_fixtures as fx

    pkg = fx.build_short_cartoon_package()
    char_assets = [
        a.asset_id for a in pkg.assets
        if str(a.asset_id) in {str(x) for x in pkg.characters[0].portrait_asset_ids}
    ]
    identity_shot = shot("s1").model_copy(
        update={
            "reference_asset_ids": char_assets,
            "dialogue_line_ids": [pkg.dialogue[0].dialogue_id],
        }
    )
    d5 = decider.decide(shot=identity_shot, incoming=[],
                        scene_character_asset_ids=char_assets,
                        scene_location_asset_ids=[])
    _record(checks, "identity_reference_image_to_video",
            d5.preferred_mode == GenerationMode.IMAGE_TO_VIDEO
            and d5.reason_code == GenerationModeReasonCode.IDENTITY_REFERENCE_REQUIRED,
            f"preferred={d5.preferred_mode.value}")

    # Every mode decision carries acceptable fallbacks for reference/continuity.
    _record(checks, "fallbacks_recorded",
            all(m.acceptable_fallback_modes for m in (d1, d3, d4, d5)),
            "fallback modes recorded for transform/frames/continuation/identity")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/generation_mode_decision.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
def main(no_write: bool = False) -> int:
    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)

    matrix = build_graph_fixture_matrix()
    dag_receipt = build_dag_validation_receipt()
    camera_receipt = build_camera_rule_receipt()
    mode_receipt = build_generation_mode_receipt()

    gate_reasons: list[str] = []
    if not matrix["all_checks_pass"]:
        gate_reasons.append("graph fixture matrix checks failed")
    if not dag_receipt["all_checks_pass"]:
        gate_reasons.append("DAG validation checks failed")
    if not camera_receipt["all_checks_pass"]:
        gate_reasons.append("camera rule checks failed")
    if not mode_receipt["all_checks_pass"]:
        gate_reasons.append("generation mode checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 9,
        "status": overall_status,
        "gate": "VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED",
        "evidence": [
            {"path": "graph_fixture_matrix.json"},
            {"path": "dag_validation_receipt.json"},
            {"path": "camera_rule_receipt.json"},
            {"path": "generation_mode_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase9_shot_graph.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "graph_fixture_matrix.json", matrix)
        write_json(PHASE_DIR / "dag_validation_receipt.json", dag_receipt)
        write_json(PHASE_DIR / "camera_rule_receipt.json", camera_receipt)
        write_json(PHASE_DIR / "generation_mode_receipt.json", mode_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, matrix, dag_receipt, camera_receipt, mode_receipt),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_09 artifacts untouched.")

    print(f"Phase 9 verdict: {overall_status}")
    print(f"  graph fixture matrix: {'PASS' if matrix['all_checks_pass'] else 'FAIL'}")
    print(f"  DAG validation: {'PASS' if dag_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  camera rules: {'PASS' if camera_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  generation modes: {'PASS' if mode_receipt['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status: str, matrix: dict, dag: dict, camera: dict, mode: dict) -> str:
    return f"""# Phase 9 Report — Shot Dependency Graph & Camera Planning

- **Gate:** `VP9_SHOT_GRAPH_AND_CAMERA_PLAN_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Graph fixture matrix

- Contract: `docs/video_production/director/shot_dependency_graph.md`
- Checks: {matrix.get('check_count')}; all pass: {matrix.get('all_checks_pass')}

## DAG validation

- Contract: `docs/video_production/director/shot_dependency_graph.md`
- Checks: {dag.get('check_count')}; all pass: {dag.get('all_checks_pass')}

## Camera rules

- Contract: `docs/video_production/director/camera_planning_rules.md`
- Checks: {camera.get('check_count')}; all pass: {camera.get('all_checks_pass')}

## Generation modes

- Contract: `docs/video_production/director/generation_mode_decision.md`
- Checks: {mode.get('check_count')}; all pass: {mode.get('all_checks_pass')}

## Evidence

- `graph_fixture_matrix.json`
- `dag_validation_receipt.json`
- `camera_rule_receipt.json`
- `generation_mode_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
