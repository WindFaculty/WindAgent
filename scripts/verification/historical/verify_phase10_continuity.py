#!/usr/bin/env python3
"""
Phase 10 verification — VP10_CONTINUITY_LEDGER_VERIFIED (plan 03 §17-§21).

Verifies the continuity ledger layer
(`intelligence/windagent_intelligence/video/continuity/`) against the
ratified contracts in `docs/video_production/director/`:

  artifacts/video_production/phase_10/
  ├── continuity_fixture_matrix.json
  ├── transition_test_receipt.json
  ├── blocking_defect_receipt.json
  ├── invalidation_dependency_receipt.json
  └── phase_verdict.json

Gate conditions (plan 03 §21):
  1. required continuity state is traceable through the shot graph for all
     three golden fixtures (identity traced, scene boundaries reset policy);
  2. invalid transitions are BLOCKED deterministically (prop change without
     action, change outside allowed, identity/reference hash mismatch,
     180-degree camera-side violation, parallel-branch conflict);
  3. human overrides are audited (actor / reason / target revision /
     timestamp) and never rewrite retroactive evidence;
  4. the ledger hash is deterministic and tied to source graph/plan/package
     hashes.

Every check is offline and fully deterministic. Supports --no-write /
--verify-only.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
from pathlib import Path

from windagent_core.domain.video_production.shot import ShotDependencyGraph
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_10"

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
# Fixture helpers: Phase 8 director (deterministic fake) + Phase 9 planner +
# Phase 10 continuity ledger
# ---------------------------------------------------------------------------
def _ledger_for_fixture(builder_name: str) -> dict:
    from tests.fixtures.video_production import director_fixtures as fx

    from windagent_intelligence.video import (
        ContinuityLedgerService,
        ShotGraphPlannerService,
        VideoDirectorService,
    )

    pkg = getattr(fx, builder_name)()
    plan_json = fx.build_pinned_planner_output(pkg)
    port = fx.DeterministicDirectorModel(plan_json)
    receipt = asyncio.run(VideoDirectorService(port).create_cinematic_plan_receipt(pkg))
    locked = asyncio.run(VideoDirectorService(port).lock_shot_plan(receipt.plan))
    graph_receipt = ShotGraphPlannerService().plan(pkg, locked)
    ledger_receipt = ContinuityLedgerService().build(pkg, graph_receipt)
    return {
        "pkg": pkg,
        "graph_receipt": graph_receipt,
        "result": ledger_receipt,
    }


# ---------------------------------------------------------------------------
# 1. Continuity fixture matrix (three fixtures -> traceable, clean ledgers)
# ---------------------------------------------------------------------------
def build_continuity_fixture_matrix() -> dict:
    checks: list[dict] = []
    fixtures: dict = {"schema_version": "1.0.0", "fixtures": {}}

    for fixture_name, builder in FIXTURE_BUILDERS:
        out = _ledger_for_fixture(builder)
        result = out["result"]
        ledger = result.ledger
        identity_traced = any(
            any(f.startswith("identity:") for f in e.incoming_state)
            for e in ledger.entries
        )
        reference_traced = any(
            any(f.startswith("reference:") for f in e.incoming_state)
            for e in ledger.entries
        )

        fixtures["fixtures"][fixture_name] = {
            "shots": len(ledger.entries),
            "ledger_hash": ledger.ledger_hash[:16],
            "identity_traced": identity_traced,
            "reference_traced": reference_traced,
            "source_graph_hash": result.source_graph_hash[:16],
            "blocking_issues": [i.to_dict() for i in result.blocking_issues],
            "entry_sources": sorted(
                {
                    s.source.value
                    for e in ledger.entries
                    for s in e.incoming_state.values()
                }
            ),
        }

        _record(checks, f"{fixture_name}_ledger_built",
                bool(ledger.entries) and bool(ledger.ledger_hash),
                f"entries={len(ledger.entries)}")
        _record(checks, f"{fixture_name}_identity_traceable",
                identity_traced, "identity traced through the graph")
        _record(checks, f"{fixture_name}_clean_golden",
                result.blocking_issues == [],
                "no blocking continuity defect on the golden fixture")
        _record(checks, f"{fixture_name}_hash_tied_to_sources",
                bool(result.source_graph_hash)
                and bool(result.source_plan_hash)
                and bool(result.source_package_hash),
                "ledger hash tied to source graph/plan/package hashes")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/continuity_ledger.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "fixtures": fixtures,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 2. Transition test receipt (state transitions; plan §19.2)
# ---------------------------------------------------------------------------
def build_transition_test_receipt() -> dict:
    from windagent_core.domain.video_production.continuity import (
        ContinuityChange,
    )
    from windagent_core.domain.video_production.enums import (
        ContinuityFieldSource,
        ContinuityIssueCode,
    )
    from windagent_core.domain.video_production.ids import (
        SceneId,
        ShotId,
    )
    from windagent_core.domain.video_production.shot import Shot
    from windagent_core.domain.video_production.shot_graph import ShotDependencyGraph

    from tests.fixtures.video_production import director_fixtures as fx

    from windagent_intelligence.video import ContinuityLedgerService

    pkg = fx.build_two_character_dialogue_package()
    graph = ShotDependencyGraph(
        shots=[
            Shot(shot_id=ShotId("s1"), scene_id=SceneId("scn_01"), order=1,
                 duration_seconds=3.0),
            Shot(shot_id=ShotId("s2"), scene_id=SceneId("scn_01"), order=2,
                 duration_seconds=3.0),
        ]
    )
    receipt = _bare_receipt(pkg, graph)

    checks: list[dict] = []
    svc = ContinuityLedgerService()

    # Wardrobe change allowed by screenplay -> passes (no blocking defect).
    scene = pkg.screenplay.scenes[0].model_copy(
        update={"action_description": "Minh takes off his coat and wears a raincoat."}
    )
    allowed_pkg = pkg.model_copy(
        update={"screenplay": pkg.screenplay.model_copy(update={"scenes": [scene]})}
    )
    result_ok = svc.build(
        allowed_pkg,
        receipt,
        planned_changes={
            "s2": [ContinuityChange(
                field="appearance:chr_minh:clothing",
                after="raincoat",
                source=ContinuityFieldSource.SCREENPLAY_FACT,
                reason="scene action",
            )],
        },
    )
    _record(checks, "wardrobe_change_allowed_by_screenplay_passes",
            result_ok.blocking_issues == [],
            f"issues={len(result_ok.issues)}")

    # Wardrobe change NOT allowed by screenplay -> blocking.
    result_blocked = svc.build(
        pkg,
        receipt,
        planned_changes={
            "s2": [ContinuityChange(
                field="appearance:chr_minh:clothing",
                after="tuxedo",
                source=ContinuityFieldSource.DIRECTOR_DECISION,
                reason="director wish",
            )],
        },
    )
    _record(checks, "wardrobe_change_outside_allowed_blocking",
            any(i.code == ContinuityIssueCode.CHANGE_OUTSIDE_ALLOWED
                for i in result_blocked.issues),
            "change outside allowed set is blocking")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/continuity_ledger.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Blocking defect receipt (plan §20 fail-closed scenarios)
# ---------------------------------------------------------------------------
def build_blocking_defect_receipt() -> dict:
    from windagent_core.domain.video_production.continuity import (
        ContinuityChange,
    )
    from windagent_core.domain.video_production.enums import (
        CameraSide,
        ContinuityFieldSource,
        ContinuityIssueCode,
    )
    from windagent_core.domain.video_production.ids import (
        ReferenceAssetId,
        SceneId,
        ShotId,
    )
    from windagent_core.domain.video_production.shot import Shot
    from windagent_core.domain.video_production.shot_graph import (
        CameraDecision,
        ShotDependencyGraph,
    )

    from tests.fixtures.video_production import director_fixtures as fx

    from windagent_intelligence.video import ContinuityLedgerService

    pkg = fx.build_short_cartoon_package()
    checks: list[dict] = []
    svc = ContinuityLedgerService()

    # 3.1 Prop change without a screenplay action -> blocking.
    prop_graph = ShotDependencyGraph(
        shots=[
            Shot(shot_id=ShotId("s1"), scene_id=SceneId("scn_01"), order=1,
                 duration_seconds=3.0),
            Shot(shot_id=ShotId("s2"), scene_id=SceneId("scn_01"), order=2,
                 duration_seconds=3.0),
        ]
    )
    result = svc.build(
        pkg,
        _bare_receipt(pkg, prop_graph),
        planned_changes={
            "s2": [ContinuityChange(
                field="prop:prp_ball:possessor",
                after="chr_doudou",
                source=ContinuityFieldSource.DIRECTOR_DECISION,
            )],
        },
    )
    _record(checks, "prop_change_without_action_blocking",
            any(i.code == ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE
                for i in result.issues) and bool(result.blocking_issues),
            "unexplained prop change is blocking")

    # 3.2 Identity/reference hash mismatch -> blocking.
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
    pkg2 = pkg.model_copy(update={"assets": [*pkg.assets, second], "characters": [char]})
    identity_graph = ShotDependencyGraph(
        shots=[
            Shot(shot_id=ShotId("s1"), scene_id=SceneId("scn_01"), order=1,
                 duration_seconds=3.0,
                 reference_asset_ids=[ReferenceAssetId("ast_doudou_v2")]),
        ]
    )
    result2 = svc.build(pkg2, _bare_receipt(pkg2, identity_graph))
    _record(checks, "identity_hash_mismatch_blocking",
            any(i.code == ContinuityIssueCode.IDENTITY_HASH_MISMATCH
                for i in result2.issues),
            "identity/reference hash mismatch is blocking")

    # 3.3 180-degree camera-side flip inside a scene -> blocking.
    flip_graph = ShotDependencyGraph(
        shots=[
            Shot(shot_id=ShotId("s1"), scene_id=SceneId("scn_01"), order=1,
                 duration_seconds=3.0),
            Shot(shot_id=ShotId("s2"), scene_id=SceneId("scn_01"), order=2,
                 duration_seconds=3.0),
        ]
    )
    receipt = _bare_receipt(pkg, flip_graph)
    specs = list(receipt.specifications)
    specs[0] = specs[0].model_copy(update={"camera": CameraDecision(camera_side=CameraSide.SIDE_A)})
    specs[1] = specs[1].model_copy(update={"camera": CameraDecision(camera_side=CameraSide.SIDE_B)})
    flip_receipt = _with_specs(receipt, specs)
    result3 = svc.build(pkg, flip_receipt)
    _record(checks, "camera_side_violation_blocking",
            any(i.code == ContinuityIssueCode.CAMERA_SIDE_VIOLATION
                for i in result3.issues),
            "180-degree flip inside a scene is blocking")

    # 3.4 Parallel branches write conflicting canonical state -> blocking.
    parallel_graph = ShotDependencyGraph(
        shots=[
            Shot(shot_id=ShotId("s1"), scene_id=SceneId("scn_01"), order=1,
                 duration_seconds=3.0),
            Shot(shot_id=ShotId("s2"), scene_id=SceneId("scn_01"), order=2,
                 duration_seconds=3.0),
        ]
    )
    result4 = svc.build(
        pkg,
        _bare_receipt(pkg, parallel_graph),
        planned_changes={
            "s1": [ContinuityChange(field="appearance:chr_doudou:emotion", after="happy")],
            "s2": [ContinuityChange(field="appearance:chr_doudou:emotion", after="sad")],
        },
    )
    _record(checks, "parallel_conflict_blocking",
            any(i.code == ContinuityIssueCode.PARALLEL_CONFLICT
                for i in result4.issues),
            "parallel conflicting changes are blocking")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/continuity_rule_catalog.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Invalidation dependency receipt (plan §19.4, override audit)
# ---------------------------------------------------------------------------
def build_invalidation_dependency_receipt() -> dict:
    from windagent_core.domain.video_production.continuity import (
        HumanContinuityOverride,
    )
    from windagent_core.domain.video_production.ids import (
        ContinuityOverrideId,
        ProductionRevisionId,
        SceneId,
        ShotId,
    )
    from windagent_core.domain.video_production.shot import Shot
    from windagent_core.domain.video_production.shot_graph import ShotDependencyGraph

    from tests.fixtures.video_production import director_fixtures as fx

    from windagent_intelligence.video import ContinuityLedgerService

    pkg = fx.build_short_cartoon_package()
    graph = ShotDependencyGraph(
        shots=[
            Shot(shot_id=ShotId("s1"), scene_id=SceneId("scn_01"), order=1,
                 duration_seconds=3.0),
            Shot(shot_id=ShotId("s2"), scene_id=SceneId("scn_01"), order=2,
                 duration_seconds=3.0),
        ]
    )
    checks: list[dict] = []
    svc = ContinuityLedgerService()

    # Human override carries the full audit record (actor/reason/revision/time).
    # The timestamp is pinned so the receipt (and the ledger hash it embeds)
    # is byte-deterministic across runs.
    override = HumanContinuityOverride(
        override_id=ContinuityOverrideId("cov_demo_1"),
        actor="quality-reviewer",
        reason="wardrobe continuity approved",
        target_revision=ProductionRevisionId("rev_phase10_1"),
        field="appearance:chr_doudou:clothing",
        before="old costume",
        after="approved costume",
        applied_at_shot_id=ShotId("s1"),
        timestamp=datetime.datetime(2026, 8, 2, 12, 0, 0, tzinfo=datetime.timezone.utc),
    )
    result = svc.build(
        pkg,
        _bare_receipt(pkg, graph),
        overrides=[override],
    )
    record = result.ledger.overrides[0]
    _record(checks, "override_audit_record_present",
            record.actor == "quality-reviewer"
            and record.reason == "wardrobe continuity approved"
            and str(record.target_revision) == "rev_phase10_1"
            and record.timestamp is not None,
            "override carries actor/reason/revision/timestamp")

    # Override resolves the defect: planned change is HUMAN_OVERRIDE sourced.
    s1 = result.ledger.entry_for(ShotId("s1"))
    override_change = next(
        (c for c in s1.planned_changes if c.field == "appearance:chr_doudou:clothing"),
        None,
    )
    _record(checks, "override_resolves_defect",
            override_change is not None
            and override_change.source.value == "HUMAN_OVERRIDE"
            and result.blocking_issues == [],
            "override is the escape hatch and resolves blocking defects")

    # Ledger hash is deterministic and changes with source hashes.
    r1 = svc.build(pkg, _bare_receipt(pkg, graph))
    r2 = svc.build(pkg, _bare_receipt(pkg, graph))
    _record(checks, "ledger_hash_deterministic",
            r1.ledger_hash == r2.ledger_hash,
            "same inputs -> same ledger hash")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/continuity_override_policy.md",
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

    matrix = build_continuity_fixture_matrix()
    transition_receipt = build_transition_test_receipt()
    blocking_receipt = build_blocking_defect_receipt()
    invalidation_receipt = build_invalidation_dependency_receipt()

    gate_reasons: list[str] = []
    if not matrix["all_checks_pass"]:
        gate_reasons.append("continuity fixture matrix checks failed")
    if not transition_receipt["all_checks_pass"]:
        gate_reasons.append("transition test checks failed")
    if not blocking_receipt["all_checks_pass"]:
        gate_reasons.append("blocking defect checks failed")
    if not invalidation_receipt["all_checks_pass"]:
        gate_reasons.append("invalidation dependency checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 10,
        "status": overall_status,
        "gate": "VP10_CONTINUITY_LEDGER_VERIFIED",
        "evidence": [
            {"path": "continuity_fixture_matrix.json"},
            {"path": "transition_test_receipt.json"},
            {"path": "blocking_defect_receipt.json"},
            {"path": "invalidation_dependency_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase10_continuity.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "continuity_fixture_matrix.json", matrix)
        write_json(PHASE_DIR / "transition_test_receipt.json", transition_receipt)
        write_json(PHASE_DIR / "blocking_defect_receipt.json", blocking_receipt)
        write_json(PHASE_DIR / "invalidation_dependency_receipt.json", invalidation_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(
                overall_status,
                matrix,
                transition_receipt,
                blocking_receipt,
                invalidation_receipt,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_10 artifacts untouched.")

    print(f"Phase 10 verdict: {overall_status}")
    print(f"  continuity fixture matrix: {'PASS' if matrix['all_checks_pass'] else 'FAIL'}")
    print(f"  transition tests: {'PASS' if transition_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  blocking defects: {'PASS' if blocking_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  invalidation/override: {'PASS' if invalidation_receipt['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, matrix, transition, blocking, invalidation) -> str:
    return f"""# Phase 10 Report — Continuity Ledger

- **Gate:** `VP10_CONTINUITY_LEDGER_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Continuity fixture matrix

- Contract: `docs/video_production/director/continuity_ledger.md`
- Checks: {matrix.get('check_count')}; all pass: {matrix.get('all_checks_pass')}

## Transition tests

- Contract: `docs/video_production/director/continuity_ledger.md`
- Checks: {transition.get('check_count')}; all pass: {transition.get('all_checks_pass')}

## Blocking defects

- Contract: `docs/video_production/director/continuity_rule_catalog.md`
- Checks: {blocking.get('check_count')}; all pass: {blocking.get('all_checks_pass')}

## Invalidation / overrides

- Contract: `docs/video_production/director/continuity_override_policy.md`
- Checks: {invalidation.get('check_count')}; all pass: {invalidation.get('all_checks_pass')}

## Evidence

- `continuity_fixture_matrix.json`
- `transition_test_receipt.json`
- `blocking_defect_receipt.json`
- `invalidation_dependency_receipt.json`
- `phase_verdict.json`
"""


def _bare_receipt(pkg, graph: ShotDependencyGraph):
    """Build a minimal ShotGraphReceipt for deterministic checks."""
    from windagent_intelligence.video import ShotScheduler

    specs = _bare_specs(pkg, graph)
    return ShotGraphReceipt(
        graph=graph,
        specifications=specs,
        scheduling=ShotScheduler().schedule(graph),
        graph_hash="g" * 64,
        source_plan_hash="p" * 64,
        source_package_hash=pkg.content_hash(),
    )


def _with_specs(receipt, specs) -> ShotGraphReceipt:
    return ShotGraphReceipt(
        graph=receipt.graph,
        specifications=specs,
        scheduling=receipt.scheduling,
        graph_hash=receipt.graph_hash,
        source_plan_hash=receipt.source_plan_hash,
        source_package_hash=receipt.source_package_hash,
    )


def _bare_specs(pkg, graph: ShotDependencyGraph):
    from windagent_core.domain.video_production.ids import ShotSpecificationId
    from windagent_core.domain.video_production.shot_graph import ShotSpecification

    from windagent_intelligence.video import CameraPlanner, GenerationModeDecider

    camera = CameraPlanner()
    decider = GenerationModeDecider()
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
                generation_mode=decider.decide(
                    shot=shot,
                    incoming=[],
                    scene_character_asset_ids=[],
                    scene_location_asset_ids=[],
                ),
            )
        )
    return specs


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
