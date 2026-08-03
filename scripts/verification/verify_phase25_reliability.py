#!/usr/bin/env python3
"""
Phase 25 verification — VP25_RECOVERY_AND_CHAOS_VERIFIED (plan 07 §11).

Evidence-mode verifier (R0 contract):
  python verify_phase25_reliability.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase25_reliability.py --write-fixture <tempdir>

Gate VP25 passes ONLY when (plan §11):
  1. all 15 mandatory chaos scenarios ran at mock/integration level with real
     observed outcomes (receipts + chaos_scenario_manifest);
  2. browser/session scenarios have controlled-environment receipts;
  3. duplicate side-effect audit shows zero duplicate submit/debit/publish;
  4. recovery timing report records observed baselines (no fabricated RTO);
  5. soak/repeat report is clean (no duplicate events, no leaks, no flaky);
  6. no release-blocking reliability finding remains;
  7. every receipt is schema-valid and content-addressed by the manifest.

Read-only by default; --write-fixture only writes to a temp dir.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_25"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import chaos_phase25  # noqa: E402
from scripts.verification.evidence_lib import (  # noqa: E402
    derive_verdict,
    diff_snapshots,
    load_json,
    parse_verifier_args,
    snapshot_dir,
    validate_evidence_manifest,
    validate_production_receipt,
    write_json,
)

GATE = "VP25_RECOVERY_AND_CHAOS_VERIFIED"
# Aggregate evidence files (NOT §3 receipts — schema is checked per artifact).
REQUIRED_FILES = (
    "chaos_scenario_manifest.json",
    "duplicate_side_effect_audit.json",
    "recovery_timing_report.json",
    "soak_test_report.json",
    "open_reliability_findings.json",
    "phase_verdict.json",
)
# Files that must carry candidate_sha when the sha is supplied.
SHA_BOUND_FILES = ("chaos_scenario_manifest.json", "duplicate_side_effect_audit.json", "phase_verdict.json")


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_fixtures(out_dir: Path) -> Path:
    """Deterministic contract-check fixtures for the verifier CLI contract."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "chaos_scenario_manifest.json", {
        "schema_version": "1.0.0",
        "gate": GATE,
        "tier": "CONTRACT_TESTED",
        "generated_at": utc_now_iso(),
        "note": "Fixture data only — not production evidence.",
        "scenario_count": len(chaos_phase25.REQUIRED_SCENARIO_IDS),
        "scenarios": [
            {"scenario_id": sid, "status": "PASSED", "observed_expectations": {"fixture": True}}
            for sid in chaos_phase25.REQUIRED_SCENARIO_IDS
        ],
    })
    write_json(out_dir / "contract_verdict.json", {
        "gate": GATE,
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": utc_now_iso(),
    })
    return out_dir


def _validate_scenario_manifest(evidence_dir: Path, reasons: list[str]) -> tuple[bool, list[str]]:
    manifest = load_json(evidence_dir / "chaos_scenario_manifest.json")
    if manifest is None:
        reasons.append("chaos_scenario_manifest.json missing/unreadable")
        return False, []
    errors: list[str] = []
    if manifest.get("schema_version") != "1.0.0":
        errors.append("manifest schema_version must be 1.0.0")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append("manifest scenarios must be a list")
        return False, errors
    ids = [s.get("scenario_id") for s in scenarios]
    missing = [sid for sid in chaos_phase25.REQUIRED_SCENARIO_IDS if sid not in ids]
    if missing:
        errors.append(f"missing mandatory scenarios: {missing}")
    for spec in chaos_phase25.MANDATORY_SCENARIOS:
        entry = next((s for s in scenarios if s.get("scenario_id") == spec["scenario_id"]), None)
        if entry is None:
            continue
        if entry.get("status") != "PASSED":
            errors.append(f"{spec['scenario_id']}: manifest status must be PASSED")
        observed = entry.get("observed_expectations")
        if not isinstance(observed, dict) or not all(observed.values()):
            errors.append(f"{spec['scenario_id']}: observed expectations not all true")
        if not entry.get("receipt"):
            errors.append(f"{spec['scenario_id']}: missing receipt path")
    return not errors, errors


def _validate_receipts(evidence_dir: Path, candidate_sha: str | None, reasons: list[str]) -> tuple[bool, int]:
    rec_dir = evidence_dir / "failure_injection_receipts"
    if not rec_dir.is_dir():
        reasons.append("missing failure_injection_receipts/ directory")
        return False, 0
    receipts = sorted(rec_dir.glob("*.json"))
    if not receipts:
        reasons.append("failure_injection_receipts/ contains no receipts")
        return False, 0
    ok = True
    seen: set[str] = set()
    for path in receipts:
        rec = load_json(path) or {}
        errors = validate_production_receipt(rec, candidate_sha=candidate_sha)
        if errors:
            reasons.append(f"{path.name}: {errors[0]}")
            ok = False
        observed = rec.get("observed")
        if not isinstance(observed, dict) or not all(observed.values()):
            reasons.append(f"{path.name}: observed expectations not all true")
            ok = False
        scenario_id = rec.get("scenario_id")
        if scenario_id not in chaos_phase25.REQUIRED_SCENARIO_IDS:
            reasons.append(f"{path.name}: unknown scenario_id {scenario_id!r}")
            ok = False
        if scenario_id in seen:
            reasons.append(f"{path.name}: duplicate scenario receipt for {scenario_id}")
            ok = False
        seen.add(scenario_id)
        if rec.get("tier") not in ("MOCK_LEVEL", "INTEGRATION_LEVEL"):
            reasons.append(f"{path.name}: tier must be MOCK_LEVEL/INTEGRATION_LEVEL")
            ok = False
        for key in ("detection_time_ms", "recovery_time_ms"):
            if not isinstance(rec.get(key), (int, float)):
                reasons.append(f"{path.name}: {key} must be numeric")
                ok = False
    missing = set(chaos_phase25.REQUIRED_SCENARIO_IDS) - seen
    if missing:
        reasons.append(f"missing scenario receipts: {sorted(missing)}")
        ok = False
    return ok, len(receipts)


def _validate_controlled_env(evidence_dir: Path, reasons: list[str]) -> bool:
    """Browser/session scenarios must carry a controlled-environment receipt."""
    ok = True
    for sid in chaos_phase25.BROWSER_SESSION_SCENARIOS:
        rec = load_json(evidence_dir / "failure_injection_receipts" / f"{sid}.json")
        if rec is None:
            reasons.append(f"{sid}: missing receipt for controlled-environment check")
            ok = False
            continue
        if not isinstance(rec.get("controlled_environment"), dict):
            reasons.append(f"{sid}: controlled-environment receipt required (plan §11.2)")
            ok = False
    return ok


def _validate_duplicate_audit(evidence_dir: Path, reasons: list[str]) -> bool:
    audit = load_json(evidence_dir / "duplicate_side_effect_audit.json")
    if audit is None:
        reasons.append("duplicate_side_effect_audit.json missing")
        return False
    ok = True
    for key in ("total_duplicate_submits", "total_duplicate_debits", "total_duplicate_publishes"):
        if audit.get(key) != 0:
            reasons.append(f"duplicate_side_effect_audit: {key} must be 0, got {audit.get(key)}")
            ok = False
    return ok


def _validate_timing_report(evidence_dir: Path, reasons: list[str]) -> bool:
    report = load_json(evidence_dir / "recovery_timing_report.json")
    if report is None:
        reasons.append("recovery_timing_report.json missing")
        return False
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        reasons.append("recovery_timing_report: rows must be non-empty")
        return False
    ok = True
    for row in rows:
        if row.get("observed_baseline") is not True:
            reasons.append("recovery_timing_report: observed_baseline must be true (no fabricated RTO)")
            ok = False
        if not isinstance(row.get("detection_time_ms"), (int, float)):
            reasons.append(f"recovery_timing_report: {row.get('scenario_id')} detection_time_ms missing")
            ok = False
    return ok


def _validate_soak(evidence_dir: Path, reasons: list[str]) -> bool:
    report = load_json(evidence_dir / "soak_test_report.json")
    if report is None:
        reasons.append("soak_test_report.json missing")
        return False
    ok = True
    if report.get("iterations", 0) < chaos_phase25.MIN_SOAK_ITERATIONS:
        reasons.append(f"soak_test_report: iterations {report.get('iterations')} < {chaos_phase25.MIN_SOAK_ITERATIONS}")
        ok = False
    if report.get("duplicate_events_total") != 0:
        reasons.append(f"soak_test_report: duplicate events {report.get('duplicate_events_total')} != 0")
        ok = False
    if report.get("all_runs_terminal") is not True:
        reasons.append("soak_test_report: not all runs reached a terminal state")
        ok = False
    if report.get("leaks_total", 0) > 0:
        reasons.append(f"soak_test_report: leaks {report.get('leaks_total')} != 0")
        ok = False
    if report.get("flaky_races", 0) > 0:
        reasons.append("soak_test_report: flaky races detected")
        ok = False
    return ok


def _validate_findings(evidence_dir: Path, reasons: list[str]) -> bool:
    findings = load_json(evidence_dir / "open_reliability_findings.json")
    if findings is None:
        reasons.append("open_reliability_findings.json missing")
        return False
    ok = True
    if findings.get("release_blocking_count") != 0:
        reasons.append("open_reliability_findings: release_blocking_count must be 0")
        ok = False
    for finding in findings.get("findings", []):
        if not finding.get("finding_id") or not finding.get("impact") or not finding.get("owner"):
            reasons.append(f"open_reliability_findings: finding {finding.get('finding_id')} incomplete")
            ok = False
        if not finding.get("release_decision"):
            reasons.append(f"open_reliability_findings: finding {finding.get('finding_id')} missing release decision")
            ok = False
    return ok


def _validate_phase_verdict(evidence_dir: Path, candidate_sha: str | None, reasons: list[str]) -> bool:
    verdict = load_json(evidence_dir / "phase_verdict.json")
    if verdict is None:
        reasons.append("phase_verdict.json missing")
        return False
    ok = True
    if verdict.get("gate") != GATE:
        reasons.append(f"phase_verdict: gate must be {GATE}")
        ok = False
    if verdict.get("status") != "PASSED":
        reasons.append(f"phase_verdict: status must be PASSED, got {verdict.get('status')!r}")
        ok = False
    if candidate_sha and verdict.get("candidate_sha") != candidate_sha:
        reasons.append(f"phase_verdict: candidate_sha {verdict.get('candidate_sha')!r} != expected {candidate_sha!r}")
        ok = False
    if not verdict.get("derived_by"):
        reasons.append("phase_verdict: missing derived_by")
        ok = False
    return ok


def verify_production_evidence(
    evidence_dir: Path,
    candidate_sha: str | None,
    *,
    require_phase_verdict: bool = True,
) -> tuple[str, dict[str, bool], list[str]]:
    workstreams: dict[str, bool] = {}
    reasons: list[str] = []

    if not evidence_dir.exists():
        return "BLOCKED", workstreams, ["evidence dir missing; no production evidence"]

    manifest = load_json(evidence_dir / "evidence_manifest.json")
    if manifest is None:
        reasons.append("missing evidence_manifest.json (content-addressed manifest required)")
        workstreams["evidence_manifest"] = False
    else:
        manifest_errors = validate_evidence_manifest(manifest, evidence_dir, candidate_sha=candidate_sha)
        workstreams["evidence_manifest"] = not manifest_errors
        reasons.extend(f"manifest: {e}" for e in manifest_errors)

    for name in REQUIRED_FILES:
        if name == "phase_verdict.json" and not require_phase_verdict:
            workstreams[name] = True  # bootstrap: written after derivation
            continue
        path = evidence_dir / name
        if not path.is_file():
            reasons.append(f"missing evidence file: {name}")
            workstreams[name] = False
            continue
        receipt = load_json(path)
        # Aggregate files are not §3 receipts; only candidate_sha consistency
        # is cross-checked here (schema of each artifact is validated below).
        errors: list[str] = []
        if name in SHA_BOUND_FILES and candidate_sha:
            if receipt.get("candidate_sha") != candidate_sha:
                errors.append(f"candidate_sha mismatch: {receipt.get('candidate_sha')!r} != {candidate_sha!r}")
        if name == "chaos_scenario_manifest.json" and receipt.get("schema_version") != "1.0.0":
            errors.append("schema_version must be 1.0.0")
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    # -- chaos scenario manifest: all 15 mandatory scenarios -------------------
    ws, errs = _validate_scenario_manifest(evidence_dir, reasons)
    workstreams["chaos_scenarios_complete"] = ws
    reasons.extend(errs)

    # -- failure injection receipts --------------------------------------------
    ws, count = _validate_receipts(evidence_dir, candidate_sha, reasons)
    workstreams["failure_injection_receipts"] = ws
    if count != len(chaos_phase25.REQUIRED_SCENARIO_IDS):
        reasons.append(f"failure_injection_receipts: expected {len(chaos_phase25.REQUIRED_SCENARIO_IDS)} receipts, got {count}")

    # -- controlled environment receipts for browser/session scenarios ---------
    workstreams["controlled_environment"] = _validate_controlled_env(evidence_dir, reasons)

    # -- no duplicate side effects ----------------------------------------------
    workstreams["duplicate_side_effect_audit"] = _validate_duplicate_audit(evidence_dir, reasons)

    # -- recovery timing (observed baselines only) ------------------------------
    workstreams["recovery_timing_report"] = _validate_timing_report(evidence_dir, reasons)

    # -- soak / repeat -----------------------------------------------------------
    workstreams["soak_test_report"] = _validate_soak(evidence_dir, reasons)

    # -- open reliability findings: no release blocker ---------------------------
    workstreams["open_reliability_findings"] = _validate_findings(evidence_dir, reasons)

    # -- phase verdict consistent ------------------------------------------------
    if require_phase_verdict:
        workstreams["phase_verdict"] = _validate_phase_verdict(evidence_dir, candidate_sha, reasons)
    else:
        # Producer bootstrap: verdict is derived first, then phase_verdict.json
        # is written with the derived status and re-verified.
        workstreams["phase_verdict"] = True

    verdict = derive_verdict(workstreams=workstreams, blocking_reasons=reasons)
    return verdict, workstreams, reasons


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=DEFAULT_EVIDENCE_DIR,
        description="Phase 25 evidence-mode verifier (VP25_RECOVERY_AND_CHAOS_VERIFIED)",
    )

    if not args.read_only:
        out = write_fixtures(args.write_fixture)
        print(f"CONTRACT_TESTED fixtures written to {out}")
        return 0

    before = snapshot_dir(args.evidence_dir)
    verdict, workstreams, reasons = verify_production_evidence(
        args.evidence_dir, args.candidate_sha
    )
    after = snapshot_dir(args.evidence_dir)
    mutations = diff_snapshots(before, after)
    if mutations:
        verdict = "FAILED"
        reasons = [f"READ-ONLY VIOLATION: {m}" for m in mutations] + reasons
        print("READ-ONLY VIOLATION: verifier mutated evidence files!")

    print(f"Phase 25 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
