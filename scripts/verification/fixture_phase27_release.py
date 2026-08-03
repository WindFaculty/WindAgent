#!/usr/bin/env python3
"""
Phase 27 fixture writer — deterministic contract-check fixtures for the
VP27 verifier CLI contract.

Usage:
  python fixture_phase27_release.py --out-dir <tempdir>

Writes a CONTRACT_TESTED evidence-shaped tree (all lane receipts PASSED +
aggregates + content-addressed manifest + phase_verdict) so regression tests
can exercise the verifier's read-only contract, candidate binding and schema
validation WITHOUT touching production evidence.

Refuses to write under artifacts/video_production (production evidence may
only be produced by produce_phase27_evidence.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification import release_phase27 as rel  # noqa: E402

FIXTURE_SHA = "f" * 40  # fixture-only candidate sha (never a real commit)


def _lane_receipt(lane_id: str, observed: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "candidate_sha": FIXTURE_SHA,
        "run_id": f"fixture-{lane_id}",
        "started_at": "2026-08-02T00:00:00+00:00",
        "completed_at": "2026-08-02T00:01:00+00:00",
        "command_or_provider": "fixture",
        "input_hashes": [rel.sha256_bytes(b"fixture-input-" + lane_id.encode())],
        "output_hashes": [rel.sha256_bytes(b"fixture-output-" + lane_id.encode())],
        "evidence_locator": "ci_run_manifest.json",
        "status": "PASSED",
        "lane_id": lane_id,
        "tier": "MOCK_LEVEL",
        "observed": observed,
    }


def write_fixture_set(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    attestation = _lane_receipt("ATTESTATION", {
        "head_matches_candidate": True,
        "parent_sha_known": True,
        "version_consistency_passed": True,
        "lockfiles_present": True,
        "migration_set_present": True,
        "third_party_manifest_present": True,
    })
    attestation["details"] = {
        "branch": "fixture-branch",
        "parent_sha": "e" * 40,
        "worktree_dirty_count": 0,
        "product_version": rel.PRODUCT_VERSION,
        "web_version": rel.WEB_VERSION,
        "desktop_version": rel.DESKTOP_VERSION,
    }

    migration = _lane_receipt("MIGRATION_REHEARSAL", {
        "dry_run_success": True,
        "rollback_rehearsal_success": True,
        "upgrade_success": True,
        "idempotent_rerun_success": True,
        "pre_existing_data_preserved": True,
        "canonical_tables_verified": True,
    })
    e2e = _lane_receipt("RELEASE_E2E_MOCK", {
        "real_ffmpeg_render_ok": True,
        "real_ffprobe_verify_ok": True,
        "edl_plan_typed_no_shell_metachars": True,
        "deliverable_record_traceable": True,
        "zero_real_credits_consumed": True,
        "real_credit_e2e_not_executed": True,
    })
    ev_validation = _lane_receipt("EVIDENCE_VALIDATION", {
        "phase_0_to_20_reports_passed": True,
        "phase_21_verdict_present": True,
        "phase_22_23_25_26_verdicts_passed": True,
        "phase_24_verdict_present": True,
        "final_bundle_present": True,
    })
    ev_validation["phase_lineage"] = {
        "phase_00": {"gate_artifact": "phase_report.md", "passed": True},
        "phase_21": {"gate_artifact": "phase_verdict.json", "passed": False, "status": "BLOCKED",
                     "note": "superseded-by-remediation (fixture)"},
        "phase_22": {"gate_artifact": "phase_verdict.json", "passed": True, "status": "PASSED"},
        "phase_23": {"gate_artifact": "phase_verdict.json", "passed": True, "status": "PASSED"},
        "phase_24": {"gate_artifact": "phase_verdict.json", "passed": False, "status": "BLOCKED",
                     "note": "live-run preconditions (fixture)"},
        "phase_25": {"gate_artifact": "phase_verdict.json", "passed": True, "status": "PASSED"},
        "phase_26": {"gate_artifact": "phase_verdict.json", "passed": True, "status": "PASSED"},
    }
    ev_validation["final_bundle_hashes"] = {
        name: rel.sha256_bytes(b"fixture-bundle-" + name.encode())
        for name in ("implementation_manifest.json", "upstream_manifest.json", "test_matrix.json",
                     "real_flow_e2e_receipt.json", "cost_report.json", "security_report.json",
                     "architecture_report.json", "known_limitations.md", "final_verdict.md")
    }

    ci_lanes = []
    for lane_id in rel.REQUIRED_CI_LANE_IDS:
        ci_lanes.append(_lane_receipt(lane_id, {"exit_zero": True}))
    ci_lanes[0]["observed"] = {"exit_zero": True, "stdout_no_failure_marker": True}
    # The ci_run_manifest must contain EVERY required lane (the verifier checks
    # rel.REQUIRED_LANE_IDS against it), including the three non-CI receipts.
    all_lane_rows = [
        {"lane_id": "ATTESTATION", "status": "PASSED", "tier": "MOCK_LEVEL", "observed": attestation["observed"],
         "receipt": "ci_run_manifest.json#attestation"},
        {"lane_id": "MIGRATION_REHEARSAL", "status": "PASSED", "tier": "MOCK_LEVEL",
         "observed": migration["observed"], "receipt": "migration_rehearsal_receipt.json"},
        {"lane_id": "RELEASE_E2E_MOCK", "status": "PASSED", "tier": "MOCK_LEVEL",
         "observed": e2e["observed"], "receipt": "release_e2e_receipt.json"},
        {"lane_id": "EVIDENCE_VALIDATION", "status": "PASSED", "tier": "MOCK_LEVEL",
         "observed": ev_validation["observed"], "receipt": "evidence_validation_receipt.json"},
    ]
    for lane in ci_lanes:
        all_lane_rows.append({"lane_id": lane["lane_id"], "status": "PASSED", "tier": "MOCK_LEVEL",
                              "observed": lane["observed"], "receipt": "ci_run_manifest.json#fixture"})
    all_lane_rows += [
        {"lane_id": "CI_PYTHON_UNIT_SUBSET", "status": "PASSED", "tier": "MOCK_LEVEL", "observed": {"exit_zero": True}, "receipt": "ci_run_manifest.json#python_unit"},
        {"lane_id": "CI_FFMPEG_FIXTURES", "status": "PASSED", "tier": "MOCK_LEVEL", "observed": {"ffmpeg_present": True}, "receipt": "ci_run_manifest.json#ffmpeg"},
        {"lane_id": "CI_LICENSE_NOTICE", "status": "PASSED", "tier": "MOCK_LEVEL", "observed": {"license_present": True}, "receipt": "ci_run_manifest.json#license"},
        {"lane_id": "CI_WEB_DESKTOP_PRESENCE", "status": "PASSED", "tier": "MOCK_LEVEL", "observed": {"web_package_present": True}, "receipt": "ci_run_manifest.json#web"},
    ]
    ci_manifest = {
        "schema_version": "1.0.0",
        "gate": rel.GATE,
        "candidate_sha": FIXTURE_SHA,
        "generated_at": rel.utc_now_iso(),
        "ci_mode": "PR_CI_OFFLINE_MOCK",
        "lane_count": len(all_lane_rows),
        "all_lanes_passed": True,
        "lanes": all_lane_rows,
    }

    build_hashes = {
        "schema_version": "1.0.0",
        "gate": rel.GATE,
        "candidate_sha": FIXTURE_SHA,
        "generated_at": rel.utc_now_iso(),
        "toolchain": {"python": "3.11", "ffmpeg": "fixture", "platform": "fixture"},
        "build_input_hashes": {n: rel.sha256_bytes(b"x") for n in ("uv.lock", "package-lock.json")},
    }
    findings = {
        "schema_version": "1.0.0",
        "gate": rel.GATE,
        "candidate_sha": FIXTURE_SHA,
        "generated_at": rel.utc_now_iso(),
        "release_blocking_count": 0,
        "findings": [
            {
                "finding_id": "FIX-001", "title": "fixture finding", "severity": "low",
                "impact": "fixture only", "mitigation": "fixture only",
                "owner": "fixture", "release_decision": "fixture-only",
            }
        ],
    }

    evidence_lib.write_json(out_dir / "candidate_attestation.json", attestation)
    evidence_lib.write_json(out_dir / "ci_run_manifest.json", ci_manifest)
    evidence_lib.write_json(out_dir / "build_hash_manifest.json", build_hashes)
    evidence_lib.write_json(out_dir / "migration_rehearsal_receipt.json", migration)
    evidence_lib.write_json(out_dir / "release_e2e_receipt.json", e2e)
    evidence_lib.write_json(out_dir / "evidence_validation_receipt.json", ev_validation)
    evidence_lib.write_json(out_dir / "open_release_findings.json", findings)
    evidence_lib.write_json(out_dir / "phase_verdict.json", {
        "schema_version": "1.0.0",
        "gate": rel.GATE,
        "release_gate": rel.RELEASE_GATE,
        "candidate_sha": FIXTURE_SHA,
        "status": "PASSED",
        "release_ready": True,
        "derived_by": "fixture_phase27_release.py",
        "derived_at": rel.utc_now_iso(),
        "reasons": ["fixture"],
    })
    evidence_lib.write_json(
        out_dir / "evidence_manifest.json",
        evidence_lib.build_evidence_manifest(out_dir, FIXTURE_SHA),
    )
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 27 fixture writer")
    parser.add_argument("--out-dir", required=True, help="temporary output dir for fixtures")
    args = parser.parse_args()

    out = Path(args.out_dir).resolve()
    prod_root = Path(evidence_lib.PRODUCTION_ARTIFACTS_ROOT).resolve()
    try:
        out.relative_to(prod_root)
        parser.error(
            f"--out-dir refuses production artifacts path: {out} "
            f"(fixtures may only live under a temporary test directory)"
        )
    except ValueError:
        pass

    write_fixture_set(out)
    print(f"FIXTURES written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
