#!/usr/bin/env python3
"""
Phase 26 verification — VP26_SECURITY_VERIFIED (plan 07 §17).

Evidence-mode verifier (R0 contract):
  python verify_phase26_security.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase26_security.py --write-fixture <tempdir>

Gate VP26 passes ONLY when (plan §17):
  1. threat model manifest covers every plan §13 trust boundary;
  2. no secret/profile/payment canary appears in evidence/log outputs;
  3. SSRF / path traversal / prompt injection / unapproved upload blocked;
  4. terms/payment/delete/publish actions always require human confirmation;
  5. API/media/event object authorization passes (idempotency, stale
     revision, media token, cross-project events);
  6. retention/deletion has implementation and a content-free receipt;
  7. no release-blocking security/privacy finding remains;
  8. every receipt is schema-valid, honest (observed expectations derived
     from real behavior) and content-addressed by the manifest.

Read-only by default; --write-fixture only writes to a temp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_26"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import security_phase26 as sec  # noqa: E402
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
GATE = "VP26_SECURITY_VERIFIED"

# Canonical trust boundaries live in the shared harness module.
TRUST_BOUNDARIES = sec.TRUST_BOUNDARIES

REQUIRED_FILES = (
    "threat_model_manifest.json",
    "secret_redaction_report.json",
    "api_authorization_report.json",
    "file_network_sandbox_report.json",
    "privacy_deletion_receipt.json",
    "open_security_findings.json",
    "phase_verdict.json",
)
# Aggregate files that must carry candidate_sha when a sha is supplied.
SHA_BOUND_FILES = (
    "threat_model_manifest.json",
    "secret_redaction_report.json",
    "api_authorization_report.json",
    "file_network_sandbox_report.json",
    "privacy_deletion_receipt.json",
    "open_security_findings.json",
    "phase_verdict.json",
)


def write_fixtures(out_dir: Path) -> Path:
    """Deterministic contract-check fixtures for the verifier CLI contract."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "threat_model_manifest.json", {
        "schema_version": "1.0.0",
        "gate": GATE,
        "tier": "CONTRACT_TESTED",
        "generated_at": sec.utc_now_iso(),
        "note": "Fixture data only — not production evidence.",
        "trust_boundaries": TRUST_BOUNDARIES,
        "entry_count": 0,
        "entries": [],
    })
    write_json(out_dir / "contract_verdict.json", {
        "gate": GATE,
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": sec.utc_now_iso(),
    })
    return out_dir


def _validate_threat_model(evidence_dir: Path, reasons: list[str]) -> bool:
    manifest = load_json(evidence_dir / "threat_model_manifest.json")
    if manifest is None:
        reasons.append("threat_model_manifest.json missing/unreadable")
        return False
    ok = True
    boundaries = manifest.get("trust_boundaries")
    if not isinstance(boundaries, list):
        reasons.append("threat_model_manifest: trust_boundaries must be a list")
        return False
    missing = [b for b in TRUST_BOUNDARIES if b not in boundaries]
    if missing:
        reasons.append(f"threat_model_manifest: missing trust boundaries {missing}")
        ok = False
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        reasons.append("threat_model_manifest: entries must be non-empty")
        ok = False
    else:
        for entry in entries:
            for field in ("finding_id", "trust_boundary", "control", "test", "severity", "release_decision"):
                if not entry.get(field):
                    reasons.append(f"threat_model_manifest: entry {entry.get('finding_id')} missing {field}")
                    ok = False
        covered = {e.get("test") for e in entries}
        if covered != set(sec.REQUIRED_SCENARIO_IDS):
            reasons.append(
                f"threat_model_manifest: entries must cover exactly the mandatory scenarios "
                f"(got {sorted(covered - set(sec.REQUIRED_SCENARIO_IDS))}, "
                f"missing {sorted(set(sec.REQUIRED_SCENARIO_IDS) - covered)})"
            )
            ok = False
    return ok


def _validate_receipts(evidence_dir: Path, candidate_sha: str | None, reasons: list[str]) -> tuple[bool, int]:
    rec_dir = evidence_dir / "security_test_receipts"
    if not rec_dir.is_dir():
        reasons.append("missing security_test_receipts/ directory")
        return False, 0
    receipts = sorted(rec_dir.glob("*.json"))
    if not receipts:
        reasons.append("security_test_receipts/ contains no receipts")
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
        if scenario_id not in sec.REQUIRED_SCENARIO_IDS:
            reasons.append(f"{path.name}: unknown scenario_id {scenario_id!r}")
            ok = False
        if scenario_id in seen:
            reasons.append(f"{path.name}: duplicate scenario receipt for {scenario_id}")
            ok = False
        seen.add(scenario_id)
        if rec.get("tier") not in ("MOCK_LEVEL", "INTEGRATION_LEVEL"):
            reasons.append(f"{path.name}: tier must be MOCK_LEVEL/INTEGRATION_LEVEL")
            ok = False
        for key in ("input_hashes", "output_hashes"):
            if not isinstance(rec.get(key), list):
                reasons.append(f"{path.name}: {key} must be a list")
                ok = False
    missing = set(sec.REQUIRED_SCENARIO_IDS) - seen
    if missing:
        reasons.append(f"missing scenario receipts: {sorted(missing)}")
        ok = False
    return ok, len(receipts)


def _validate_controlled_env(evidence_dir: Path, reasons: list[str]) -> bool:
    ok = True
    for sid in sec.BROWSER_SESSION_SCENARIOS:
        rec = load_json(evidence_dir / "security_test_receipts" / f"{sid}.json")
        if rec is None:
            reasons.append(f"{sid}: missing receipt for controlled-environment check")
            ok = False
            continue
        if not isinstance(rec.get("controlled_environment"), dict):
            reasons.append(f"{sid}: controlled-environment receipt required (browser/session boundary)")
            ok = False
    return ok


def _cross_check_aggregate(
    evidence_dir: Path,
    aggregate_name: str,
    pairs: list[tuple[str, str, str]],
    reasons: list[str],
) -> bool:
    """Each aggregate boolean must equal the corresponding receipt observation.

    An aggregate that contradicts its own receipts (or a receipt that was
    tampered with after aggregation) fails the gate.
    """
    aggregate = load_json(evidence_dir / aggregate_name)
    if aggregate is None:
        reasons.append(f"{aggregate_name} missing")
        return False
    ok = True
    for agg_key, scenario_id, observed_key in pairs:
        agg_val = aggregate.get(agg_key)
        if not isinstance(agg_val, bool):
            reasons.append(f"{aggregate_name}: {agg_key} must be a boolean")
            ok = False
            continue
        rec = load_json(evidence_dir / "security_test_receipts" / f"{scenario_id}.json")
        rec_val = (rec or {}).get("observed", {}).get(observed_key)
        if agg_val is not rec_val:
            reasons.append(
                f"{aggregate_name}: {agg_key}={agg_val} contradicts "
                f"{scenario_id}.observed.{observed_key}={rec_val}"
            )
            ok = False
    return ok


def _validate_secret_report(evidence_dir: Path, reasons: list[str]) -> bool:
    report = load_json(evidence_dir / "secret_redaction_report.json")
    if report is None:
        reasons.append("secret_redaction_report.json missing")
        return False
    ok = True
    if not isinstance(report.get("canaries_injected"), int) or report.get("canaries_injected", 0) < 1:
        reasons.append("secret_redaction_report: canaries_injected must be >= 1")
        ok = False
    if report.get("canaries_found_in_output") != 0:
        reasons.append(f"secret_redaction_report: canaries_found_in_output must be 0, got {report.get('canaries_found_in_output')}")
        ok = False
    if report.get("evidence_locator_markers_observed") != 0:
        reasons.append("secret_redaction_report: evidence_locator markers must be 0")
        ok = False
    # Cross-check the aggregate count against the SE01 receipt's own notes.
    se01 = load_json(evidence_dir / "security_test_receipts" / "SE01.json") or {}
    receipt_found = len((se01.get("redaction_notes") or {}).get("canaries_found_in_sinks", []))
    if report.get("canaries_found_in_output") != receipt_found:
        reasons.append(
            f"secret_redaction_report: canaries_found_in_output={report.get('canaries_found_in_output')} "
            f"contradicts SE01 receipt ({receipt_found} found)"
        )
        ok = False
    return ok


def _validate_api_report(evidence_dir: Path, reasons: list[str]) -> bool:
    ok = _cross_check_aggregate(
        evidence_dir, "api_authorization_report.json",
        [
            ("idempotent_replay_dedup", "SE11", "idempotency_dedup"),
            ("stale_revision_blocked", "SE11", "stale_revision_conflict"),
            ("media_token_path_blocked", "SE11", "media_token_path_denied"),
            ("cross_project_event_denied", "SE11", "cross_project_event_denied"),
            ("stale_approval_blocked", "SE12", "stale_approval_after_catalog_change"),
        ],
        reasons,
    )
    report = load_json(evidence_dir / "api_authorization_report.json") or {}
    for key in ("idempotent_replay_dedup", "stale_revision_blocked", "media_token_path_blocked",
                "cross_project_event_denied", "stale_approval_blocked"):
        if report.get(key) is not True:
            reasons.append(f"api_authorization_report: {key} must be true")
            ok = False
    # CSRF disposition must be recorded (plan §15 matrix: stale approval/CSRF/idempotency).
    if not report.get("csrf_note"):
        reasons.append("api_authorization_report: csrf_note missing (CSRF disposition required by plan §15)")
        ok = False
    return ok


def _validate_sandbox_report(evidence_dir: Path, reasons: list[str]) -> bool:
    pairs = [
        ("path_traversal_blocked", "SE04", "traversal_blocked"),
        ("ssrf_private_ip_blocked", "SE05", "private_ip_blocked"),
        ("dns_rebinding_blocked", "SE05", "dns_rebinding_blocked"),
        ("domain_allowlist_enforced", "SE03", "allowlist_deny"),
        ("redirect_revalidated", "SE03", "redirect_revalidated"),
        ("polyglot_blocked", "SE06", "polyglot_rejected"),
        ("executable_blocked", "SE06", "wrong_mime_exec_rejected"),
        ("pixel_bomb_blocked", "SE06", "pixel_bomb_rejected"),
        ("prompt_injection_stays_data", "SE07", "injection_stays_data"),
        ("ffmpeg_filter_typed", "SE07", "filter_graph_safe"),
        ("eval_shell_blocked", "SE08", "eval_denied"),
        ("eval_shell_blocked", "SE08", "forbidden_shell_blocked"),
        ("unapproved_upload_blocked", "SE09", "outside_store_denied"),
    ]
    ok = _cross_check_aggregate(
        evidence_dir, "file_network_sandbox_report.json", pairs, reasons
    )
    report = load_json(evidence_dir / "file_network_sandbox_report.json") or {}
    for key, _, _ in pairs:
        if report.get(key) is not True:
            reasons.append(f"file_network_sandbox_report: {key} must be true")
            ok = False
    return ok


def _validate_privacy_receipt(evidence_dir: Path, reasons: list[str]) -> bool:
    ok = _cross_check_aggregate(
        evidence_dir, "privacy_deletion_receipt.json",
        [
            ("retention_cleanup_executed", "SE13", "state_cleanup_by_age"),
            ("invalidation_stale_not_deleted", "SE13", "invalidation_stale_not_deleted"),
            ("superseded_marking", "SE13", "superseded"),
        ],
        reasons,
    )
    receipt = load_json(evidence_dir / "privacy_deletion_receipt.json") or {}
    if receipt.get("retention_cleanup_executed") is not True:
        reasons.append("privacy_deletion_receipt: retention_cleanup_executed must be true")
        ok = False
    if receipt.get("invalidation_stale_not_deleted") is not True:
        reasons.append("privacy_deletion_receipt: invalidation_stale_not_deleted must be true")
        ok = False
    if receipt.get("deletion_receipt_contains_deleted_content") is not False:
        reasons.append("privacy_deletion_receipt: must NOT contain deleted content")
        ok = False
    return ok


def _validate_findings(evidence_dir: Path, reasons: list[str]) -> bool:
    findings = load_json(evidence_dir / "open_security_findings.json")
    if findings is None:
        reasons.append("open_security_findings.json missing")
        return False
    ok = True
    if findings.get("release_blocking_count") != 0:
        reasons.append("open_security_findings: release_blocking_count must be 0")
        ok = False
    for finding in findings.get("findings", []):
        if not finding.get("finding_id") or not finding.get("impact") or not finding.get("owner"):
            reasons.append(f"open_security_findings: finding {finding.get('finding_id')} incomplete")
            ok = False
        if not finding.get("release_decision"):
            reasons.append(f"open_security_findings: finding {finding.get('finding_id')} missing release decision")
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
        errors: list[str] = []
        if name in SHA_BOUND_FILES and candidate_sha:
            if receipt.get("candidate_sha") != candidate_sha:
                errors.append(f"candidate_sha mismatch: {receipt.get('candidate_sha')!r} != {candidate_sha!r}")
        if receipt.get("schema_version") != "1.0.0":
            errors.append("schema_version must be 1.0.0")
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    # -- threat model covers every trust boundary -----------------------------
    workstreams["threat_model"] = _validate_threat_model(evidence_dir, reasons)

    # -- security test receipts -------------------------------------------------
    ws, count = _validate_receipts(evidence_dir, candidate_sha, reasons)
    workstreams["security_test_receipts"] = ws
    if count != len(sec.REQUIRED_SCENARIO_IDS):
        reasons.append(
            f"security_test_receipts: expected {len(sec.REQUIRED_SCENARIO_IDS)} receipts, got {count}"
        )

    # -- controlled environment receipts for browser/profile scenarios ---------
    workstreams["controlled_environment"] = _validate_controlled_env(evidence_dir, reasons)

    # -- no secret canary in evidence/log outputs -------------------------------
    workstreams["secret_redaction_report"] = _validate_secret_report(evidence_dir, reasons)

    # -- API/media/event object authorization -----------------------------------
    workstreams["api_authorization_report"] = _validate_api_report(evidence_dir, reasons)

    # -- file/network/prompt boundaries ------------------------------------------
    workstreams["file_network_sandbox_report"] = _validate_sandbox_report(evidence_dir, reasons)

    # -- retention/deletion -------------------------------------------------------
    workstreams["privacy_deletion_receipt"] = _validate_privacy_receipt(evidence_dir, reasons)

    # -- no release-blocking security finding -------------------------------------
    workstreams["open_security_findings"] = _validate_findings(evidence_dir, reasons)

    # -- phase verdict consistent --------------------------------------------------
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
        description="Phase 26 evidence-mode verifier (VP26_SECURITY_VERIFIED)",
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

    print(f"Phase 26 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
