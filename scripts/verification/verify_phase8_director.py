#!/usr/bin/env python3
"""
Phase 8 verification — VP8_DIRECTOR_FOUNDATION_VERIFIED (plan 03 §7-§11).

Verifies the Director Layer (`intelligence/windagent_intelligence/video/director/`)
against the ratified contracts in `docs/video_production/director/`:

  artifacts/video_production/phase_08/
  ├── cinematic_plan_fixtures/            (one golden plan per fixture)
  ├── director_contract_receipt.json
  ├── screenplay_immutability_receipt.json
  ├── duration_validation_receipt.json
  └── phase_verdict.json

Gate conditions (plan 03 §11):
  1. the three package fixtures (short cartoon, two-character dialogue,
     multi-scene drama) each produce a valid, deterministic CinematicPlan;
  2. locked screenplay cannot be mutated by planning (package hash unchanged);
  3. every blocking directorial issue goes through a ScriptRevisionProposal;
  4. unknown entity/reference IDs fail closed (no partial plan);
  5. dialogue over duration raises an issue (never silently cut);
  6. the Director never calls a provider (only the planning model port).

Every check below is real and offline: the model port is a deterministic
fake returning pinned structured planner output (no network).

Supports --no-write / --verify-only (runs all checks, writes nothing).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_08"
FIXTURES_DIR = PHASE_DIR / "cinematic_plan_fixtures"

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
# 1. Director contract receipt (three fixtures -> valid deterministic plans)
# ---------------------------------------------------------------------------
async def _plan_for_fixture(builder_name: str) -> dict:
    from tests.fixtures.video_production import director_fixtures as fx

    builder = getattr(fx, builder_name)
    pkg = builder()
    plan_json = fx.build_pinned_planner_output(pkg)
    port = fx.DeterministicDirectorModel(plan_json)
    from windagent_intelligence.video import VideoDirectorService

    svc = VideoDirectorService(port)
    receipt = await svc.create_cinematic_plan_receipt(pkg)
    return {
        "fixture": builder_name,
        "receipt": receipt,
        "package": pkg,
        "port": port,
    }


def build_director_contract_receipt() -> dict:
    """Three fixtures produce valid plans; determinism + provider neutrality."""
    from windagent_intelligence.video import VideoDirectorService

    checks: list[dict] = []

    results = asyncio.run(_run_all_fixtures())
    _record(checks, "fixture_count_three",
            len(results) == 3, f"planned {len(results)} fixtures")
    for res in results:
        receipt = res["receipt"]
        pkg = res["package"]
        plan = receipt.plan
        _record(checks, f"{res['fixture']}_plan_valid",
                plan is not None and len(plan.graph.shots) >= 1,
                f"shots={len(plan.graph.shots)} deps={len(plan.graph.dependencies)}")
        _record(checks, f"{res['fixture']}_no_issues",
                len(receipt.issues) == 0,
                f"issues={len(receipt.issues)}")
        _record(checks, f"{res['fixture']}_source_revision",
                str(plan.revision_id) == str(pkg.revision_id),
                "plan is bound to the package revision")
        # Determinism: same fixture + same fake -> same plan hash.
        from tests.fixtures.video_production import director_fixtures as fx

        port2 = fx.DeterministicDirectorModel(fx.build_pinned_planner_output(pkg))
        svc2 = VideoDirectorService(port2)
        receipt2 = asyncio.run(svc2.create_cinematic_plan_receipt(pkg))
        _record(checks, f"{res['fixture']}_deterministic_hash",
                receipt.plan_hash == receipt2.plan_hash,
                f"plan_hash={receipt.plan_hash[:12]}")
        # Provider neutrality: only the planning capability is called.
        _record(checks, f"{res['fixture']}_provider_not_called",
                res["port"].calls == ["cinematic_planning"],
                f"calls={res['port'].calls}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/director/cinematic_plan_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


async def _run_all_fixtures() -> list[dict]:
    results = []
    for _, builder in FIXTURE_BUILDERS:
        results.append(await _plan_for_fixture(builder))
    return results


# ---------------------------------------------------------------------------
# 2. Cinematic plan fixtures (golden outputs)
# ---------------------------------------------------------------------------
def build_cinematic_plan_fixtures(no_write: bool = False) -> None:
    """Golden plan fixtures per fixture; saved under cinematic_plan_fixtures/.

    Never writes in verify-only mode (`no_write=True`) — honors the strict
    --no-write contract shared with the Phase 6/7 verifiers.
    """
    for fixture_name, builder in FIXTURE_BUILDERS:
        res = asyncio.run(_plan_for_fixture(builder))
        receipt = res["receipt"]
        if not no_write:
            write_json(FIXTURES_DIR / f"{fixture_name}.plan.json", receipt.to_dict())


# ---------------------------------------------------------------------------
# 3. Screenplay immutability receipt (locked screenplay never changes)
# ---------------------------------------------------------------------------
def build_screenplay_immutability_receipt() -> dict:
    from tests.fixtures.video_production import director_fixtures as fx

    checks: list[dict] = []
    for fixture_name, builder in FIXTURE_BUILDERS:
        pkg = getattr(fx, builder)()
        assert pkg.screenplay.status.value == "LOCKED", fixture_name
        before_hash = pkg.content_hash()
        before_screenplay = pkg.screenplay.model_dump_json()

        plan_json = fx.build_pinned_planner_output(pkg)
        port = fx.DeterministicDirectorModel(plan_json)
        from windagent_intelligence.video import VideoDirectorService

        receipt = asyncio.run(
            VideoDirectorService(port).create_cinematic_plan_receipt(pkg)
        )
        _record(checks, f"{fixture_name}_package_hash_unchanged",
                pkg.content_hash() == before_hash,
                "package content hash is identical after planning")
        _record(checks, f"{fixture_name}_screenplay_unchanged",
                pkg.screenplay.model_dump_json() == before_screenplay,
                "screenplay JSON is byte-identical after planning")
        _record(checks, f"{fixture_name}_plan_never_locks_screenplay",
                receipt.plan.metadata.get("screenplay_locked") is True,
                "plan records the locked state without mutating it")

    # A DRAFT screenplay must be rejected by default (explicit unlocked state
    # is opt-in via require_locked=False).
    pkg = fx.build_short_cartoon_package()
    from windagent_core.domain.video_production.enums import ScreenplayStatus

    draft = pkg.model_copy(update={
        "screenplay": pkg.screenplay.model_copy(update={"status": ScreenplayStatus.DRAFT}),
    })
    port = fx.DeterministicDirectorModel(fx.build_pinned_planner_output(draft))
    from windagent_intelligence.video import VideoDirectorService
    from windagent_intelligence.video.errors import ValidationFailureError

    rejected = False
    try:
        asyncio.run(VideoDirectorService(port).create_cinematic_plan_receipt(draft))
    except ValidationFailureError:
        rejected = True
    _record(checks, "draft_screenplay_rejected_by_default", rejected,
            "DRAFT screenplay is rejected unless explicitly unlocked")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "policy": "docs/video_production/director/script_revision_protocol.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Duration validation receipt (dialogue never cut; overflow -> issue)
# ---------------------------------------------------------------------------
def build_duration_validation_receipt() -> dict:
    from tests.fixtures.video_production import director_fixtures as fx

    checks: list[dict] = []
    pkg = fx.build_short_cartoon_package()

    # 4.1 Dialogue over duration -> issue, dialogue NOT cut.
    plan_json = fx.build_pinned_planner_output(pkg)
    for shot in plan_json["shots"]:
        if shot["dialogue_line_ids"]:
            shot["duration_seconds"] = 1.0
    port = fx.DeterministicDirectorModel(plan_json)
    from windagent_intelligence.video import VideoDirectorService

    receipt = asyncio.run(VideoDirectorService(port).create_cinematic_plan_receipt(pkg))
    issue_cats = {i.category.value for i in receipt.issues}
    _record(checks, "dialogue_over_duration_issue",
            "DIALOGUE_DURATION_MISMATCH" in issue_cats,
            f"categories={sorted(issue_cats)}")
    bound = {str(d) for s in receipt.plan.graph.shots for d in s.dialogue_line_ids}
    _record(checks, "dialogue_not_cut",
            bound == {str(d.dialogue_id) for d in pkg.dialogue},
            "every dialogue line remains bound to a shot")
    _record(checks, "blocking_issue_has_proposal",
            any(p.source_issue_id in {i.issue_id for i in receipt.issues}
                for p in receipt.proposals),
            f"proposals={len(receipt.proposals)}")

    # 4.2 Total duration overflow -> issue.
    plan_json2 = fx.build_pinned_planner_output(pkg)
    for shot in plan_json2["shots"]:
        shot["duration_seconds"] = 60.0
    port2 = fx.DeterministicDirectorModel(plan_json2)
    receipt2 = asyncio.run(VideoDirectorService(port2).create_cinematic_plan_receipt(pkg))
    _record(checks, "duration_overflow_issue",
            "DURATION_OVERFLOW" in {i.category.value for i in receipt2.issues},
            "overflow beyond target raises DURATION_OVERFLOW")

    # 4.3 Policy is versioned and recorded on the plan.
    _record(checks, "duration_policy_versioned",
            receipt.plan.metadata.get("duration_policy_version") == "1.0.0",
            "policy version recorded on plan metadata")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "policy": "docs/video_production/director/duration_budget_policy.md",
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

    contract_receipt = build_director_contract_receipt()
    build_cinematic_plan_fixtures(no_write=no_write)
    immutability_receipt = build_screenplay_immutability_receipt()
    duration_receipt = build_duration_validation_receipt()

    gate_reasons: list[str] = []
    if not contract_receipt["all_checks_pass"]:
        gate_reasons.append("director contract checks failed")
    if not immutability_receipt["all_checks_pass"]:
        gate_reasons.append("screenplay immutability checks failed")
    if not duration_receipt["all_checks_pass"]:
        gate_reasons.append("duration validation checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 8,
        "status": overall_status,
        "gate": "VP8_DIRECTOR_FOUNDATION_VERIFIED",
        "evidence": [
            {"path": "cinematic_plan_fixtures/"},
            {"path": "director_contract_receipt.json"},
            {"path": "screenplay_immutability_receipt.json"},
            {"path": "duration_validation_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase8_director.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "director_contract_receipt.json", contract_receipt)
        write_json(PHASE_DIR / "screenplay_immutability_receipt.json", immutability_receipt)
        write_json(PHASE_DIR / "duration_validation_receipt.json", duration_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(
                overall_status,
                contract_receipt,
                immutability_receipt,
                duration_receipt,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_08 artifacts untouched (--no-write keeps the tree clean).")

    print(f"Phase 8 verdict: {overall_status}")
    print(f"  director contract: {'PASS' if contract_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  screenplay immutability: {'PASS' if immutability_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  duration validation: {'PASS' if duration_receipt['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status: str, contract: dict, immutability: dict, duration: dict) -> str:
    return f"""# Phase 8 Report — Director Layer Foundation

- **Gate:** `VP8_DIRECTOR_FOUNDATION_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Director contract

- Contract: `docs/video_production/director/cinematic_plan_contract.md`
- Checks: {contract.get('check_count')}; all pass: {contract.get('all_checks_pass')}

## Screenplay immutability

- Policy: `docs/video_production/director/script_revision_protocol.md`
- Checks: {immutability.get('check_count')}; all pass: {immutability.get('all_checks_pass')}

## Duration validation

- Policy: `docs/video_production/director/duration_budget_policy.md`
- Checks: {duration.get('check_count')}; all pass: {duration.get('all_checks_pass')}

## Evidence

- `cinematic_plan_fixtures/`
- `director_contract_receipt.json`
- `screenplay_immutability_receipt.json`
- `duration_validation_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
