#!/usr/bin/env python3
"""
Phase 26 fixture writer — deterministic contract-check fixtures for the
VP26 verifier CLI contract.

Usage:
  python fixture_phase26_security.py --out-dir <tempdir>

Writes a CONTRACT_TESTED evidence-shaped tree (receipts with all-True
observed expectations + aggregate reports + content-addressed manifest) so
regression tests can exercise the verifier's read-only contract, candidate
binding and schema validation WITHOUT touching production evidence.

Refuses to write under artifacts/video_production (production evidence may
only be produced by produce_phase26_evidence.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification import security_phase26 as sec  # noqa: E402

FIXTURE_SHA = "f" * 40  # fixture-only candidate sha (never a real commit)

_OBSERVED_BY_SCENARIO: dict[str, dict[str, bool]] = {
    "SE01": {"all_canaries_redacted_in_logs": True, "nested_dict_masked": True,
             "secret_key_values_masked": True},
    "SE02": {"encrypted_at_rest": True, "no_plaintext_leak": True,
             "roundtrip_integrity": True, "wrong_key_rejected": True,
             "isolated_profile_cleanup": True},
    "SE03": {"allowlist_allow": True, "allowlist_deny": True,
             "credentials_deny": True, "redirect_revalidated": True,
             "public_host_allowed": True},
    "SE04": {"traversal_blocked": True, "absolute_escape_blocked": True,
             "windows_separator_blocked": True, "legit_path_allowed": True,
             "symlink_escape_blocked": True},
    "SE05": {"private_ip_blocked": True, "scheme_blocked": True,
             "credentials_blocked": True, "no_host_blocked": True,
             "dns_rebinding_blocked": True, "public_allowed": True},
    "SE06": {"wrong_mime_exec_rejected": True, "polyglot_rejected": True,
             "svg_rejected": True, "archive_rejected": True,
             "wrong_mime_text_rejected": True, "zero_byte_rejected": True,
             "pixel_bomb_rejected": True, "exif_stripped": True,
             "metadata_canary_absent_downstream": True},
    "SE07": {"injection_stays_data": True, "filter_graph_safe": True,
             "shell_blocked": True, "metadata_not_instruction": True},
    "SE08": {"eval_denied": True, "cookie_export_denied": True,
             "filesystem_read_denied": True, "forbidden_shell_blocked": True,
             "ffmpeg_argv_typed_no_metachars": True},
    "SE09": {"store_allowed": True, "outside_store_denied": True,
             "no_store_denied": True},
    "SE10": {"terms_confirmation": True, "publish_requires_approval": True,
             "unknown_deny": True, "hard_deny": True,
             "explicit_approval_allows": True},
    "SE11": {"media_token_valid": True, "media_token_path_denied": True,
             "idempotency_dedup": True, "stale_revision_conflict": True,
             "cross_project_event_denied": True},
    "SE12": {"wrong_hash_approval_rejected": True,
             "duplicate_approval_idempotent": True, "approval_hash_bound": True,
             "stale_approval_after_catalog_change": True},
    "SE13": {"state_cleanup_by_count": True, "state_cleanup_by_age": True,
             "invalidation_stale_not_deleted": True, "superseded": True,
             "deletion_receipt_no_content": True},
}


def write_fixture_set(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir = out_dir / "security_test_receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    receipts: list[dict] = []
    for scenario_id in sec.REQUIRED_SCENARIO_IDS:
        receipt = {
            "schema_version": "1.0.0",
            "candidate_sha": FIXTURE_SHA,
            "run_id": f"fixture-{scenario_id}",
            "started_at": "2026-08-02T00:00:00+00:00",
            "completed_at": "2026-08-02T00:01:00+00:00",
            "command_or_provider": "fixture",
            "input_hashes": [sec.sha256_bytes(b"fixture-input-" + scenario_id.encode())],
            "output_hashes": [sec.sha256_bytes(b"fixture-output-" + scenario_id.encode())],
            "evidence_locator": f"security_test_receipts/{scenario_id}.json",
            "status": "PASSED",
            "scenario_id": scenario_id,
            "tier": "MOCK_LEVEL",
            "observed": _OBSERVED_BY_SCENARIO[scenario_id],
            "controlled_environment": (
                {"isolation": "fixture", "note": "contract test only"}
                if scenario_id in sec.BROWSER_SESSION_SCENARIOS else None
            ),
        }
        receipt = {k: v for k, v in receipt.items() if v is not None}
        receipts.append(receipt)
        evidence_lib.write_json(receipts_dir / f"{scenario_id}.json", receipt)

    evidence_lib.write_json(out_dir / "threat_model_manifest.json", {
        "schema_version": "1.0.0",
        "gate": sec.GATE,
        "candidate_sha": FIXTURE_SHA,
        "generated_at": sec.utc_now_iso(),
        "trust_boundaries": sec.TRUST_BOUNDARIES,
        "entry_count": len(sec.REQUIRED_SCENARIO_IDS),
        "notes": ["CSRF non-applicable (fixture)"],
        "entries": [
            {
                "finding_id": f"TM-FIX-{sid}",
                "asset": spec["threat"],
                "trust_boundary": spec["trust_boundary"],
                "threat": spec["threat"],
                "likelihood": "low",
                "impact": "medium",
                "control": "fixture",
                "test": sid,
                "residual_risk": "low",
                "severity": "low",
                "release_decision": "fixture-only",
            }
            for sid, spec in ((s["scenario_id"], s) for s in sec.MANDATORY_SCENARIOS)
        ],
    })
    evidence_lib.write_json(out_dir / "secret_redaction_report.json", {
        "schema_version": "1.0.0", "gate": sec.GATE, "candidate_sha": FIXTURE_SHA,
        "generated_at": sec.utc_now_iso(),
        "canaries_injected": len(sec.CANARY_SECRETS),
        "canaries_found_in_output": 0,
        "redaction_targets": ["logs", "errors", "events", "screenshots", "shell_output"],
        "evidence_locator_markers_observed": 0,
        "derived_from": "security_test_receipts/SE01.json",
    })
    evidence_lib.write_json(out_dir / "api_authorization_report.json", {
        "schema_version": "1.0.0", "gate": sec.GATE, "candidate_sha": FIXTURE_SHA,
        "generated_at": sec.utc_now_iso(),
        "idempotent_replay_dedup": True,
        "stale_revision_blocked": True,
        "media_token_path_blocked": True,
        "cross_project_event_denied": True,
        "stale_approval_blocked": True,
        "csrf_note": "backend bearer API without cookie sessions -> CSRF non-applicable (fixture)",
        "derived_from": ["security_test_receipts/SE11.json", "security_test_receipts/SE12.json"],
    })
    evidence_lib.write_json(out_dir / "file_network_sandbox_report.json", {
        "schema_version": "1.0.0", "gate": sec.GATE, "candidate_sha": FIXTURE_SHA,
        "generated_at": sec.utc_now_iso(),
        "path_traversal_blocked": True, "ssrf_private_ip_blocked": True,
        "dns_rebinding_blocked": True, "domain_allowlist_enforced": True,
        "redirect_revalidated": True, "polyglot_blocked": True,
        "executable_blocked": True, "pixel_bomb_blocked": True,
        "prompt_injection_stays_data": True, "ffmpeg_filter_typed": True,
        "eval_shell_blocked": True, "unapproved_upload_blocked": True,
        "derived_from": [f"security_test_receipts/{sid}.json" for sid in
                         ("SE03", "SE04", "SE05", "SE06", "SE07", "SE08", "SE09")],
    })
    evidence_lib.write_json(out_dir / "privacy_deletion_receipt.json", {
        "schema_version": "1.0.0", "gate": sec.GATE, "candidate_sha": FIXTURE_SHA,
        "generated_at": sec.utc_now_iso(),
        "retention_cleanup_executed": True,
        "invalidation_stale_not_deleted": True,
        "superseded_marking": True,
        "deletion_receipt_contains_deleted_content": False,
        "derived_from": "security_test_receipts/SE13.json",
    })
    evidence_lib.write_json(out_dir / "open_security_findings.json", {
        "schema_version": "1.0.0", "gate": sec.GATE, "candidate_sha": FIXTURE_SHA,
        "generated_at": sec.utc_now_iso(),
        "release_blocking_count": 0,
        "findings": [
            {
                "finding_id": "FIX-001", "title": "fixture finding",
                "severity": "low", "status": "OPEN",
                "impact": "fixture only", "mitigation": "fixture only",
                "owner": "fixture", "release_decision": "fixture-only",
            }
        ],
    })
    evidence_lib.write_json(out_dir / "phase_verdict.json", {
        "schema_version": "1.0.0", "gate": sec.GATE, "candidate_sha": FIXTURE_SHA,
        "status": "PASSED", "derived_by": "fixture_phase26_security.py",
        "derived_at": sec.utc_now_iso(), "reasons": ["fixture"],
    })
    evidence_lib.write_json(
        out_dir / "evidence_manifest.json",
        evidence_lib.build_evidence_manifest(out_dir, FIXTURE_SHA),
    )
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 26 fixture writer")
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
