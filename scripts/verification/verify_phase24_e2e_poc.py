#!/usr/bin/env python3
"""
Phase 24 verification — VP24_E2E_POC_PASSED (remediation plan 08, R4).

Evidence-mode verifier (R0 contract):
  python verify_phase24_e2e_poc.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase24_e2e_poc.py --write-fixture <tempdir>

Gate VP24 passes ONLY when simultaneously (plan §21):
  1. VP21–VP23 receipts on the same candidate lineage pass;
  2. every one of 5–7 shots has a real Flow job/candidate receipt with an
     external job ID (sanitized), no duplicate submit/debit;
  3. browser recovery/reconciliation has a real receipt;
  4. final MP4 is real, 30–45s, passes full FFprobe/decode/loudness;
  5. traceability graph has real hashes and full lineage;
  6. automation rate >= 80%, no hidden blocking identity defect;
  7. ledger observed/adjusted <= approved maximum and reconciled;
  8. final-cut approval references the final artifact hash.

Real Flow account/credit approval is a prerequisite (plan §17). Without live
run evidence this gate stays BLOCKED — no "partial success".
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_24"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification.evidence_lib import (  # noqa: E402
    derive_verdict,
    load_json,
    parse_verifier_args,
    snapshot_dir,
    diff_snapshots,
    validate_evidence_manifest,
    validate_production_receipt,
    write_json,
)

MIN_SHOTS = 5
MAX_SHOTS = 7
MIN_DURATION_SECONDS = 30.0
MAX_DURATION_SECONDS = 45.0
AUTOMATION_THRESHOLD = 0.80


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_fixtures(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "e2e_contract_fixture.json", {
        "gate": "VP24_E2E_POC_PASSED",
        "tier": "CONTRACT_TESTED",
        "generated_at": utc_now_iso(),
        "note": "Deterministic runbook/traceability contract checks (fixture only).",
        "checks": {
            "14_step_runbook_sequence": True,
            "traceability_dag_complete": True,
            "automation_rate_threshold": True,
        },
    })
    write_json(out_dir / "contract_verdict.json", {
        "gate": "VP24_E2E_POC_PASSED",
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": utc_now_iso(),
    })
    return out_dir


# ---------------------------------------------------------------------------
# Production evidence validation (gate VP24)
# ---------------------------------------------------------------------------

REQUIRED_FILES = (
    "poc_run_manifest.json",
    "input_revision_manifest.json",
    "workflow_event_receipt.json",
    "browser_recovery_receipt.json",
    "candidate_review_report.json",
    "audio_production_receipt.json",
    "postproduction_receipt.json",
    "final_media_manifest.json",
    "final_media_verification.json",
    "cost_report.json",
    "traceability_graph.json",
    "automation_rate.json",
    "final_cut_approval.json",
)


def _validate_flow_job_receipts(evidence_dir: Path, reasons: list[str]) -> tuple[bool, int]:
    job_dir = evidence_dir / "flow_job_receipts"
    if not job_dir.is_dir():
        reasons.append("missing flow_job_receipts/ directory (no live Flow jobs)")
        return False, 0
    receipts = sorted(job_dir.glob("*.json"))
    if not receipts:
        reasons.append("flow_job_receipts/ contains no job receipts")
        return False, 0
    ok = True
    seen_external_ids: set[str] = set()
    for path in receipts:
        rec = load_json(path) or {}
        ext_id = rec.get("external_job_id")
        if not isinstance(ext_id, str) or not ext_id:
            reasons.append(f"{path.name}: external_job_id (sanitized) required — R24-01")
            ok = False
        elif ext_id in seen_external_ids:
            reasons.append(f"{path.name}: duplicate external_job_id {ext_id!r}")
            ok = False
        else:
            seen_external_ids.add(ext_id)
        if not evidence_lib.is_sha256(rec.get("candidate_hash", "")):
            reasons.append(f"{path.name}: candidate_hash must be 64-hex")
            ok = False
        if not evidence_lib.is_sha256(rec.get("request_hash", "")):
            reasons.append(f"{path.name}: request_hash must be 64-hex")
            ok = False
        if rec.get("duplicate_submit") is True or rec.get("duplicate_debit") is True:
            reasons.append(f"{path.name}: duplicate submit/debit detected")
            ok = False
    return ok, len(receipts)


def verify_production_evidence(
    evidence_dir: Path,
    candidate_sha: str | None,
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
        path = evidence_dir / name
        if not path.is_file():
            reasons.append(f"missing production receipt: {name}")
            workstreams[name] = False
            continue
        receipt = load_json(path)
        errors = validate_production_receipt(receipt or {}, candidate_sha=candidate_sha)
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    # --- poc_run_manifest: real freeze scope (plan §18) ----------------------
    poc = load_json(evidence_dir / "poc_run_manifest.json")
    if poc:
        if not evidence_lib.is_candidate_sha(poc.get("candidate_sha", "")):
            reasons.append("poc_run_manifest: candidate_sha must be real 40/64-hex (R24-01)")
            workstreams.setdefault("poc_run_manifest", False)
        if poc.get("planned_shots") not in range(MIN_SHOTS, MAX_SHOTS + 1):
            reasons.append(f"poc_run_manifest: planned_shots must be {MIN_SHOTS}-{MAX_SHOTS}")
            workstreams.setdefault("poc_run_manifest", False)
        if not (MIN_DURATION_SECONDS <= float(poc.get("planned_duration_seconds", 0)) <= MAX_DURATION_SECONDS):
            reasons.append(f"poc_run_manifest: duration must be {MIN_DURATION_SECONDS}-{MAX_DURATION_SECONDS}s")
            workstreams.setdefault("poc_run_manifest", False)

    # --- flow job receipts: real external IDs + hashes -----------------------
    job_ok, shot_count = _validate_flow_job_receipts(evidence_dir, reasons)
    workstreams["flow_job_receipts"] = job_ok
    if not (MIN_SHOTS <= shot_count <= MAX_SHOTS):
        reasons.append(f"flow_job_receipts: {shot_count} jobs, expected {MIN_SHOTS}-{MAX_SHOTS}")

    # --- browser recovery: real reattach + zero duplicates --------------------
    recovery = load_json(evidence_dir / "browser_recovery_receipt.json")
    if recovery:
        if recovery.get("duplicate_submits_count") != 0:
            reasons.append("browser_recovery_receipt: duplicate_submits_count must be 0")
            workstreams.setdefault("browser_recovery_receipt", False)
        if recovery.get("reattach_verified") is not True or recovery.get("job_reconciled") is not True:
            reasons.append("browser_recovery_receipt: reattach/reconcile not verified")
            workstreams.setdefault("browser_recovery_receipt", False)
        if "browser_recovery_receipt" not in workstreams:
            workstreams["browser_recovery_receipt"] = True
    else:
        reasons.append("browser_recovery_receipt.json missing")
        workstreams["browser_recovery_receipt"] = False

    # --- final media: real 30-45s MP4 ----------------------------------------
    final = load_json(evidence_dir / "final_media_manifest.json")
    if final:
        locator = final.get("media_locator") or final.get("locator")
        media_path = evidence_dir / locator if locator else None
        errors: list[str] = []
        if not media_path or not media_path.is_file():
            errors.append("final media file missing")
        else:
            errors.extend(evidence_lib.validate_media_file(media_path, expected_container="mp4"))
            expected = final.get("final_media_sha256")
            if not evidence_lib.is_sha256(expected) or expected != evidence_lib.sha256_file(media_path):
                errors.append("final_media_sha256 mismatch with real file")
            duration = final.get("duration_seconds")
            if not isinstance(duration, (int, float)) or not (
                MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS
            ):
                errors.append(f"duration {duration} outside {MIN_DURATION_SECONDS}-{MAX_DURATION_SECONDS}s")
        workstreams["final_media_manifest"] = not errors
        reasons.extend(f"final_media_manifest: {e}" for e in errors)
    else:
        reasons.append("final_media_manifest.json missing")
        workstreams["final_media_manifest"] = False

    # --- automation rate >= 80% ----------------------------------------------
    auto = load_json(evidence_dir / "automation_rate.json")
    if auto:
        rate = auto.get("automation_rate")
        if not isinstance(rate, (int, float)) or rate < AUTOMATION_THRESHOLD:
            reasons.append(f"automation_rate {rate} < {AUTOMATION_THRESHOLD}")
            workstreams.setdefault("automation_rate", False)
        if "automation_rate" not in workstreams:
            workstreams["automation_rate"] = True
    else:
        reasons.append("automation_rate.json missing")
        workstreams["automation_rate"] = False

    # --- cost ledger reconciled within approved maximum ----------------------
    cost = load_json(evidence_dir / "cost_report.json")
    if cost:
        if not isinstance(cost.get("max_approved_credits"), (int, float)):
            reasons.append("cost_report: max_approved_credits required")
            workstreams.setdefault("cost_report", False)
        if not isinstance(cost.get("debited_credits"), (int, float)):
            reasons.append("cost_report: debited_credits required")
            workstreams.setdefault("cost_report", False)
        elif cost.get("debited_credits", 0) > cost.get("max_approved_credits", 0):
            reasons.append("cost_report: debited credits exceed approved maximum")
            workstreams.setdefault("cost_report", False)
        if cost.get("ledger_reconciled") is not True:
            reasons.append("cost_report: ledger not reconciled")
            workstreams.setdefault("cost_report", False)
        if "cost_report" not in workstreams:
            workstreams["cost_report"] = True
    else:
        reasons.append("cost_report.json missing")
        workstreams["cost_report"] = False

    # --- traceability graph with real lineage ---------------------------------
    trace = load_json(evidence_dir / "traceability_graph.json")
    if trace:
        nodes = trace.get("nodes")
        if not isinstance(nodes, list) or len(nodes) < 6:
            reasons.append("traceability_graph: incomplete DAG (fewer than 6 nodes)")
            workstreams.setdefault("traceability_graph", False)
        else:
            for node in nodes:
                if not evidence_lib.is_sha256(node.get("content_hash", "")):
                    reasons.append(f"traceability_graph: node {node.get('node_id')} hash not 64-hex")
                    workstreams.setdefault("traceability_graph", False)
                    break
            else:
                workstreams["traceability_graph"] = True
    else:
        reasons.append("traceability_graph.json missing")
        workstreams["traceability_graph"] = False

    # --- final-cut approval references the artifact hash ----------------------
    approval = load_json(evidence_dir / "final_cut_approval.json")
    if approval:
        if not evidence_lib.is_sha256(approval.get("final_artifact_sha256", "")):
            reasons.append("final_cut_approval: final_artifact_sha256 must be 64-hex")
            workstreams.setdefault("final_cut_approval", False)
        if approval.get("approved") is not True:
            reasons.append("final_cut_approval: not approved")
            workstreams.setdefault("final_cut_approval", False)
        if "final_cut_approval" not in workstreams:
            workstreams["final_cut_approval"] = True
    else:
        reasons.append("final_cut_approval.json missing")
        workstreams["final_cut_approval"] = False

    # --- prior gates on the same candidate lineage ----------------------------
    for gate_name in ("vp21_receipt.json", "vp22_receipt.json", "vp23_receipt.json"):
        path = evidence_dir / gate_name
        if not path.is_file():
            reasons.append(f"missing prior-gate receipt {gate_name} (same candidate lineage)")
            workstreams.setdefault(gate_name, False)
        else:
            rec = load_json(path)
            if not rec or rec.get("status") != "PASSED":
                reasons.append(f"{gate_name} not PASSED on this lineage")
                workstreams.setdefault(gate_name, False)
            else:
                workstreams[gate_name] = True

    if "flow_job_receipts" in workstreams and not workstreams["flow_job_receipts"]:
        reasons.append(
            "no live Flow E2E evidence — requires approved creative brief, credit cap and "
            "live run (plan 08 §17)"
        )

    verdict = derive_verdict(workstreams=workstreams, blocking_reasons=reasons)
    return verdict, workstreams, reasons


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=DEFAULT_EVIDENCE_DIR,
        description="Phase 24 evidence-mode verifier (VP24_E2E_POC_PASSED)",
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

    print(f"Phase 24 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
