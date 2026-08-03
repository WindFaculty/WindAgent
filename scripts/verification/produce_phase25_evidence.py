#!/usr/bin/env python3
"""
Phase 25 evidence producer — runs the mandatory chaos matrix + soak at
mock/integration level and writes honest evidence (plan 07 §10).

Usage:
  python produce_phase25_evidence.py --candidate-sha <sha> [--out <dir>]

Outputs (under artifacts/video_production/phase_25/<candidate_sha>/):
  chaos_scenario_manifest.json
  failure_injection_receipts/<SCENARIO_ID>.json   (15 receipts)
  duplicate_side_effect_audit.json
  recovery_timing_report.json
  soak_test_report.json
  open_reliability_findings.json
  evidence_manifest.json        (content-addressed)
  phase_verdict.json            (derived from the verifier, never hard-coded)

No simulated ffmpeg, no self-reported counters: every receipt records what
the real machinery actually observed.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = ROOT / "artifacts" / "video_production" / "phase_25"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification.chaos_phase25 import (  # noqa: E402
    MANDATORY_SCENARIOS,
    REQUIRED_SCENARIO_IDS,
    SCENARIO_RUNNERS,
    build_recovery_timing_report,
    collect_duplicate_audit,
    run_soak,
    utc_now_iso,
)


def build_manifest(receipts: list[dict], candidate_sha: str) -> dict:
    """chaos_scenario_manifest.json — every mandatory scenario + outcome."""
    by_id = {r.get("scenario_id") or r["run_id"]: r for r in receipts}
    scenarios = []
    for spec in MANDATORY_SCENARIOS:
        rid = spec["scenario_id"]
        receipt = by_id.get(rid)
        observed = receipt.get("observed", {}) if receipt else {}
        scenarios.append({
            **spec,
            "status": "PASSED" if receipt and all(observed.values()) else "FAILED",
            "observed_expectations": observed,
            "receipt": f"failure_injection_receipts/{rid}.json" if receipt else None,
        })
    return {
        "schema_version": "1.0.0",
        "gate": "VP25_RECOVERY_AND_CHAOS_VERIFIED",
        "candidate_sha": candidate_sha,
        "tier": "MOCK_INTEGRATION_LEVEL",
        "generated_at": utc_now_iso(),
        "note": "All 15 mandatory scenarios executed against real orchestration "
                "machinery with provider/browser injected fakes (plan §8).",
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def build_open_findings() -> dict:
    """open_reliability_findings.json — known limitations with decisions.

    None of these are release-blocking (plan §11 gate: no release-blocking
    reliability finding may remain).
    """
    findings = [
        {
            "finding_id": "REL-001",
            "title": "Live Flow chaos only in nightly/manual (not PR CI)",
            "severity": "low",
            "impact": "Browser-against-live-Flow chaos scenarios are not run on "
                      "every PR; regression coverage of those paths relies on "
                      "mock browser + controlled nightly runs.",
            "mitigation": "Controlled-environment receipts for all browser/session "
                          "scenarios (mock browser); nightly live smoke bounded by "
                          "credit cap (plan §20.2).",
            "owner": "release-owner",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "REL-002",
            "title": "ffprobe binary required for technical review on the host",
            "severity": "low",
            "impact": "CH06/CH07 real-media rejection depends on ffprobe presence.",
            "mitigation": "VideoInspectionPolicy fails closed when the inspector "
                          "is unavailable (VideoProbeUnavailableError); CI installs "
                          "ffmpeg (present in the evidence run).",
            "owner": "release-owner",
            "release_decision": "acceptable-for-0.1",
        },
    ]
    return {
        "schema_version": "1.0.0",
        "gate": "VP25_RECOVERY_AND_CHAOS_VERIFIED",
        "release_blocking_count": 0,
        "findings": findings,
    }


def build_phase_verdict(verdict: str, reasons: list[str], candidate_sha: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "gate": "VP25_RECOVERY_AND_CHAOS_VERIFIED",
        "candidate_sha": candidate_sha,
        "status": verdict,
        "derived_by": "scripts/verification/verify_phase25_reliability.py",
        "derived_at": utc_now_iso(),
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 25 evidence producer")
    parser.add_argument("--candidate-sha", required=True, help="40/64-hex candidate SHA")
    parser.add_argument("--out", default=None, help="evidence output dir (default: phase_25/<sha>)")
    args = parser.parse_args()

    if not evidence_lib.is_candidate_sha(args.candidate_sha):
        parser.error(f"--candidate-sha must be 40/64 lowercase hex, got {args.candidate_sha!r}")

    out = Path(args.out).resolve() if args.out else (DEFAULT_EVIDENCE_ROOT / args.candidate_sha)
    out.mkdir(parents=True, exist_ok=True)
    receipts_dir = out / "failure_injection_receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    scratch = Path(tempfile.mkdtemp(prefix="wa_phase25_scratch_"))
    try:
        # 1. Run every mandatory scenario in its own isolated workdir.
        receipts: list[dict] = []
        for scenario_id in REQUIRED_SCENARIO_IDS:
            scenario_work = scratch / scenario_id
            scenario_work.mkdir(parents=True, exist_ok=True)
            receipt = SCENARIO_RUNNERS[scenario_id](scenario_work, args.candidate_sha)
            receipt["scenario_id"] = scenario_id
            # Ensure the receipt hashes reference the real files produced.
            receipt["input_hashes"] = [h for h in receipt.get("input_hashes", []) if h]
            receipt["output_hashes"] = [h for h in receipt.get("output_hashes", []) if h]
            receipts.append(receipt)
            evidence_lib.write_json(receipts_dir / f"{scenario_id}.json", receipt)
            print(f"  scenario {scenario_id}: all_observed={all(receipt['observed'].values())}")

        # 2. Soak / repeat.
        soak_work = scratch / "soak"
        soak_work.mkdir(parents=True, exist_ok=True)
        soak_report = run_soak(soak_work, args.candidate_sha)
        print(f"  soak: {soak_report['iterations']} runs, "
              f"duplicates={soak_report['duplicate_events_total']}, "
              f"leaks={soak_report['leaks_total']}, "
              f"all_terminal={soak_report['all_runs_terminal']}")

        # 3. Aggregates.
        manifest = build_manifest(receipts, args.candidate_sha)
        duplicate_audit = collect_duplicate_audit(receipts)
        timing_report = build_recovery_timing_report(receipts)
        findings = build_open_findings()

        # 4. Write all evidence files.
        evidence_lib.write_json(out / "chaos_scenario_manifest.json", manifest)
        evidence_lib.write_json(out / "duplicate_side_effect_audit.json", duplicate_audit)
        evidence_lib.write_json(out / "recovery_timing_report.json", timing_report)
        evidence_lib.write_json(out / "soak_test_report.json", soak_report)
        evidence_lib.write_json(out / "open_reliability_findings.json", findings)

        # 5. Content-addressed evidence manifest.
        manifest_file = evidence_lib.build_evidence_manifest(out, args.candidate_sha)
        evidence_lib.write_json(out / "evidence_manifest.json", manifest_file)

        # 6. Derive the phase verdict with the SAME verifier logic (no hard-code).
        from scripts.verification.verify_phase25_reliability import verify_production_evidence

        # Bootstrap: derive the verdict first (phase_verdict.json not required),
        # then write it and re-verify with the full gate including the verdict.
        verdict, workstreams, reasons = verify_production_evidence(
            out, args.candidate_sha, require_phase_verdict=False
        )
        evidence_lib.write_json(out / "phase_verdict.json",
                                build_phase_verdict(verdict, reasons, args.candidate_sha))
        final_verdict, final_workstreams, final_reasons = verify_production_evidence(
            out, args.candidate_sha
        )
        print(f"Phase 25 verdict: {final_verdict}")
        for ws, ok in final_workstreams.items():
            print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
        for reason in final_reasons:
            print(f"  REASON: {reason}")
        return 0 if final_verdict == "PASSED" else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
