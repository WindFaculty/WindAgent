#!/usr/bin/env python3
"""
Phase 27 verification — VIDEO_PRODUCTION_PLATFORM_VERIFIED + READY_FOR_CONTROLLED_RELEASE
(plan 07 §18-§28).

Evidence-mode verifier (R0 contract):
  python verify_phase27_release.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase27_release.py --write-fixture <tempdir>

Gates pass ONLY when (plan §24 blocker policy + §28):
  1. candidate attestation is consistent on the candidate SHA (HEAD, parent,
     branch, version consistency, lockfiles/migration/third-party frozen);
  2. every required CI lane passed on the candidate (offline mock matrix);
  3. migration rehearsal (SQLite upgrade + rollback + idempotent + data
     preservation) passed;
  4. controlled E2E (mock-level, zero real credits) passed with the
     real-credit E2E recorded as a release condition;
  5. evidence validation: phase gates 0-26 lineage present, phases 22/23/25/26
     PASSED on the candidate SHA, phase 21/24 verdict artifacts present, final
     bundle content-addressed and hash-consistent;
  6. no release-blocking finding remains (REL findings are documented
     conditions with owners/decisions, none release-blocking).

Read-only by default; --write-fixture only writes to a temp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_27"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import release_phase27 as rel  # noqa: E402
from scripts.verification.evidence_lib import (  # noqa: E402
    derive_verdict,
    diff_snapshots,
    load_json,
    parse_verifier_args,
    snapshot_dir,
    validate_evidence_manifest,
    write_json,
)

GATE = rel.GATE          # VIDEO_PRODUCTION_PLATFORM_VERIFIED
RELEASE_GATE = rel.RELEASE_GATE  # READY_FOR_CONTROLLED_RELEASE

# Phase-27 evidence files (not §3 receipts; schema checked per artifact).
REQUIRED_FILES = (
    "candidate_attestation.json",
    "ci_run_manifest.json",
    "build_hash_manifest.json",
    "migration_rehearsal_receipt.json",
    "release_e2e_receipt.json",
    "evidence_validation_receipt.json",
    "open_release_findings.json",
    "phase_verdict.json",
)
SHA_BOUND_FILES = (
    "candidate_attestation.json",
    "ci_run_manifest.json",
    "build_hash_manifest.json",
    "migration_rehearsal_receipt.json",
    "release_e2e_receipt.json",
    "evidence_validation_receipt.json",
    "open_release_findings.json",
    "phase_verdict.json",
)

# Final bundle files cross-checked by the evidence-validation lane.
FINAL_BUNDLE_FILES = (
    "implementation_manifest.json",
    "upstream_manifest.json",
    "test_matrix.json",
    "real_flow_e2e_receipt.json",
    "cost_report.json",
    "security_report.json",
    "architecture_report.json",
    "known_limitations.md",
    "final_verdict.md",
)


def write_fixtures(out_dir: Path) -> Path:
    """Deterministic contract-check fixtures for the verifier CLI contract."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "candidate_attestation.json", {
        "schema_version": "1.0.0",
        "gate": GATE,
        "tier": "CONTRACT_TESTED",
        "generated_at": rel.utc_now_iso(),
        "note": "Fixture data only — not production evidence.",
    })
    write_json(out_dir / "contract_verdict.json", {
        "gate": GATE,
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": rel.utc_now_iso(),
    })
    return out_dir


def _validate_attestation(evidence_dir: Path, candidate_sha: str | None, reasons: list[str]) -> bool:
    attest = load_json(evidence_dir / "candidate_attestation.json")
    if attest is None:
        reasons.append("candidate_attestation.json missing/unreadable")
        return False
    ok = True
    if attest.get("status") != "PASSED":
        reasons.append("candidate_attestation: status must be PASSED")
        ok = False
    details = attest.get("details") or {}
    if not details.get("branch"):
        reasons.append("candidate_attestation: branch must be recorded")
        ok = False
    if candidate_sha and attest.get("candidate_sha") != candidate_sha:
        reasons.append(
            f"candidate_attestation: candidate_sha {attest.get('candidate_sha')!r} != {candidate_sha!r}"
        )
        ok = False
    for key in ("product_version", "web_version", "desktop_version"):
        if not details.get(key):
            reasons.append(f"candidate_attestation: details.{key} missing")
            ok = False
    return ok


def _validate_ci_manifest(evidence_dir: Path, reasons: list[str]) -> bool:
    manifest = load_json(evidence_dir / "ci_run_manifest.json")
    if manifest is None:
        reasons.append("ci_run_manifest.json missing/unreadable")
        return False
    ok = True
    lanes = manifest.get("lanes")
    if not isinstance(lanes, list):
        reasons.append("ci_run_manifest: lanes must be a list")
        return False
    lane_ids = [lane.get("lane_id") for lane in lanes]
    missing = [lid for lid in rel.REQUIRED_LANE_IDS if lid not in lane_ids]
    if missing:
        reasons.append(f"ci_run_manifest: missing required lanes {missing}")
        ok = False
    for lane in lanes:
        if lane.get("status") != "PASSED":
            reasons.append(f"ci_run_manifest: lane {lane.get('lane_id')} status {lane.get('status')!r} != PASSED")
            ok = False
        observed = lane.get("observed")
        if not isinstance(observed, dict) or not observed:
            reasons.append(f"ci_run_manifest: lane {lane.get('lane_id')} has no observed expectations")
            ok = False
        elif not all(v is True for v in observed.values()):
            # Same honesty contract as receipt files: fabricated observed
            # expectations (or recorded failures) must fail closed.
            reasons.append(f"ci_run_manifest: lane {lane.get('lane_id')} observed expectations not all true")
            ok = False
    if manifest.get("all_lanes_passed") is not True:
        reasons.append("ci_run_manifest: all_lanes_passed must be true")
        ok = False
    return ok


def _validate_build_hashes(evidence_dir: Path, reasons: list[str]) -> bool:
    manifest = load_json(evidence_dir / "build_hash_manifest.json")
    if manifest is None:
        reasons.append("build_hash_manifest.json missing")
        return False
    ok = True
    hashes = manifest.get("build_input_hashes")
    if not isinstance(hashes, dict) or not hashes:
        reasons.append("build_hash_manifest: build_input_hashes must be non-empty")
        ok = False
    if any(h == "MISSING" for h in (hashes or {}).values()):
        reasons.append("build_hash_manifest: one or more build inputs MISSING")
        ok = False
    if not manifest.get("toolchain", {}).get("python"):
        reasons.append("build_hash_manifest: toolchain.python missing")
        ok = False
    return ok


def _validate_receipt_file(evidence_dir: Path, name: str, reasons: list[str]) -> bool:
    """Phase-27 lanes produce receipt-shaped dicts; require the observed map."""
    receipt = load_json(evidence_dir / name)
    if receipt is None:
        reasons.append(f"{name} missing/unreadable")
        return False
    ok = True
    if receipt.get("status") != "PASSED":
        reasons.append(f"{name}: status must be PASSED, got {receipt.get('status')!r}")
        ok = False
    observed = receipt.get("observed")
    if not isinstance(observed, dict) or not all(observed.values()):
        reasons.append(f"{name}: observed expectations not all true")
        ok = False
    if receipt.get("lane_id") is None:
        reasons.append(f"{name}: missing lane_id")
        ok = False
    return ok


def _validate_evidence_validation(evidence_dir: Path, reasons: list[str]) -> bool:
    receipt = load_json(evidence_dir / "evidence_validation_receipt.json")
    if receipt is None:
        reasons.append("evidence_validation_receipt.json missing")
        return False
    ok = True
    if receipt.get("status") != "PASSED":
        reasons.append("evidence_validation_receipt: status must be PASSED")
        ok = False
    lineage = receipt.get("phase_lineage")
    if not isinstance(lineage, dict) or not lineage:
        reasons.append("evidence_validation_receipt: phase_lineage must be non-empty")
        ok = False
    # Phases 22/23/25/26 must be PASSED on the candidate (phase 21/24 are
    # documented BLOCKED states: superseded-by-remediation / live-run preconditions).
    for key in ("phase_22", "phase_23", "phase_25", "phase_26"):
        entry = (lineage or {}).get(key) or {}
        if entry.get("passed") is not True or entry.get("status") != "PASSED":
            reasons.append(f"evidence_validation_receipt: {key} must be PASSED on the candidate")
            ok = False
    # Final bundle hashes must be present (non-MISSING).
    bundle = receipt.get("final_bundle_hashes") or {}
    missing_bundle = [n for n in FINAL_BUNDLE_FILES if bundle.get(n) == "MISSING"]
    if missing_bundle:
        reasons.append(f"evidence_validation_receipt: final bundle missing files {missing_bundle}")
        ok = False
    return ok


def _validate_findings(evidence_dir: Path, reasons: list[str]) -> bool:
    findings = load_json(evidence_dir / "open_release_findings.json")
    if findings is None:
        reasons.append("open_release_findings.json missing")
        return False
    ok = True
    if findings.get("release_blocking_count") != 0:
        reasons.append("open_release_findings: release_blocking_count must be 0")
        ok = False
    for finding in findings.get("findings", []):
        if not finding.get("finding_id") or not finding.get("impact") or not finding.get("owner"):
            reasons.append(f"open_release_findings: finding {finding.get('finding_id')} incomplete")
            ok = False
        if not finding.get("release_decision"):
            reasons.append(f"open_release_findings: finding {finding.get('finding_id')} missing release decision")
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
        reasons.append(f"phase_verdict: candidate_sha mismatch {verdict.get('candidate_sha')!r}")
        ok = False
    if not verdict.get("derived_by"):
        reasons.append("phase_verdict: missing derived_by")
        ok = False
    if not verdict.get("release_ready"):
        reasons.append("phase_verdict: missing release_ready marker (READY_FOR_CONTROLLED_RELEASE)")
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
        errors: list[str] = []
        if name in SHA_BOUND_FILES and candidate_sha:
            if receipt.get("candidate_sha") != candidate_sha:
                errors.append(f"candidate_sha mismatch: {receipt.get('candidate_sha')!r} != {candidate_sha!r}")
        if receipt.get("schema_version") != "1.0.0":
            errors.append("schema_version must be 1.0.0")
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    # -- candidate attestation ---------------------------------------------------
    workstreams["candidate_attestation"] = _validate_attestation(evidence_dir, candidate_sha, reasons)

    # -- CI matrix ----------------------------------------------------------------
    workstreams["ci_run_manifest"] = _validate_ci_manifest(evidence_dir, reasons)

    # -- build hashes --------------------------------------------------------------
    workstreams["build_hash_manifest"] = _validate_build_hashes(evidence_dir, reasons)

    # -- migration rehearsal -------------------------------------------------------
    workstreams["migration_rehearsal_receipt"] = _validate_receipt_file(
        evidence_dir, "migration_rehearsal_receipt.json", reasons
    )

    # -- release E2E ----------------------------------------------------------------
    workstreams["release_e2e_receipt"] = _validate_receipt_file(
        evidence_dir, "release_e2e_receipt.json", reasons
    )
    e2e = load_json(evidence_dir / "release_e2e_receipt.json") or {}
    if e2e.get("observed", {}).get("real_credit_e2e_not_executed") is not True:
        reasons.append("release_e2e_receipt: real_credit_e2e_not_executed must be true (approval-gated)")
        workstreams["release_e2e_receipt"] = False

    # -- evidence validation ---------------------------------------------------------
    workstreams["evidence_validation_receipt"] = _validate_evidence_validation(evidence_dir, reasons)

    # -- open findings: no release blocker -------------------------------------------
    workstreams["open_release_findings"] = _validate_findings(evidence_dir, reasons)

    # -- phase verdict ----------------------------------------------------------------
    if require_phase_verdict:
        workstreams["phase_verdict"] = _validate_phase_verdict(evidence_dir, candidate_sha, reasons)
    else:
        workstreams["phase_verdict"] = True

    verdict = derive_verdict(workstreams=workstreams, blocking_reasons=reasons)
    return verdict, workstreams, reasons


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=DEFAULT_EVIDENCE_DIR,
        description="Phase 27 evidence-mode verifier (VIDEO_PRODUCTION_PLATFORM_VERIFIED)",
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

    print(f"Phase 27 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
