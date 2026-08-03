#!/usr/bin/env python3
"""
Phase 26 evidence producer — runs the mandatory security/privacy matrix at
mock/integration level and writes honest evidence (plan 07 §16).

Usage:
  python produce_phase26_evidence.py --candidate-sha <sha> [--out <dir>]

Outputs (under artifacts/video_production/phase_26/<candidate_sha>/):
  threat_model_manifest.json
  security_test_receipts/<SCENARIO_ID>.json   (13 receipts, plan §15 matrix)
  secret_redaction_report.json
  api_authorization_report.json
  file_network_sandbox_report.json
  privacy_deletion_receipt.json
  open_security_findings.json
  evidence_manifest.json        (content-addressed)
  phase_verdict.json            (derived from the verifier, never hard-coded)

Every receipt records what the real machinery observed. Aggregates are built
FROM those receipts so the verifier can cross-check them.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = ROOT / "artifacts" / "video_production" / "phase_26"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification.security_phase26 import (  # noqa: E402
    GATE,
    REQUIRED_SCENARIO_IDS,
    SECURITY_TEST_RUNNERS,
    TRUST_BOUNDARIES,
    build_api_authorization_report,
    build_file_network_sandbox_report,
    build_privacy_deletion_receipt,
    build_secret_redaction_report,
    utc_now_iso,
)

def build_threat_model_manifest(candidate_sha: str) -> Dict[str, Any]:
    """threat_model_manifest.json — every trust boundary + control + test."""
    entries: List[Dict[str, Any]] = [
        {
            "finding_id": "SEC-TM-001",
            "asset": "API/provider secrets",
            "trust_boundary": "evidence/logs",
            "threat": "secrets leak into logs, events, errors, screenshots or evidence",
            "likelihood": "medium",
            "impact": "high",
            "control": "canonical redaction (redact_text/redact_dict) + shell-output masking",
            "test": "SE01",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-002",
            "asset": "Flow account/session/profile/cookie",
            "trust_boundary": "browser profile",
            "threat": "profile readable at rest by an unauthorized process",
            "likelihood": "medium",
            "impact": "high",
            "control": "AES-GCM encryption at rest + isolated profile copies + retention cleanup",
            "test": "SE02",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-003",
            "asset": "browser session state",
            "trust_boundary": "browser UI",
            "threat": "navigation outside the approved domain or malicious redirect",
            "likelihood": "medium",
            "impact": "high",
            "control": "domain allowlist + redirect revalidation + credentials-in-URL denial",
            "test": "SE03",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-004",
            "asset": "local filesystem/database",
            "trust_boundary": "local filesystem",
            "threat": "asset path escapes the workspace via ../ or symlink",
            "likelihood": "low",
            "impact": "medium",
            "control": "canonical path sandbox with resolve()-based boundary check",
            "test": "SE04",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-005",
            "asset": "internal services / metadata endpoints",
            "trust_boundary": "internet assets",
            "threat": "downloader reaches private/loopback/link-local/metadata addresses",
            "likelihood": "medium",
            "impact": "high",
            "control": "SSRF-safe URL/IP validation incl. DNS rebinding and redirect revalidation",
            "test": "SE05",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-006",
            "asset": "project screenplay/media",
            "trust_boundary": "media files",
            "threat": "executable/polyglot/oversized asset or malicious metadata accepted",
            "likelihood": "medium",
            "impact": "high",
            "control": "ordered media validation pipeline + pixel-bomb guard + EXIF sanitization",
            "test": "SE06",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-007",
            "asset": "model output / prompts",
            "trust_boundary": "model output",
            "threat": "web/metadata text is treated as an instruction and reaches shell/filter",
            "likelihood": "medium",
            "impact": "high",
            "control": "typed envelopes + typed FFmpeg plan + shell policy (injection stays data)",
            "test": "SE07",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-008",
            "asset": "browser/process runtime",
            "trust_boundary": "browser UI",
            "threat": "arbitrary eval, cookie export, filesystem read or destructive shell executes",
            "likelihood": "low",
            "impact": "high",
            "control": "bounded browser action policy + forbidden shell patterns + typed FFmpeg argv",
            "test": "SE08",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-009",
            "asset": "provider upload boundary",
            "trust_boundary": "browser UI",
            "threat": "a file outside the approved artifact store is uploaded",
            "likelihood": "low",
            "impact": "medium",
            "control": "approved asset store enforcement in upload policy",
            "test": "SE09",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-010",
            "asset": "cost/payment/account state",
            "trust_boundary": "browser UI / API",
            "threat": "automation confirms terms/payment/delete/publish without a human",
            "likelihood": "low",
            "impact": "critical",
            "control": "confirmation-gated browser policy + permission-engine approval gating",
            "test": "SE10",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-011",
            "asset": "project data / events / media",
            "trust_boundary": "API clients",
            "threat": "cross-project media/command/event access",
            "likelihood": "medium",
            "impact": "high",
            "control": "media token format gate + idempotency + optimistic concurrency + project-scoped events; "
                      "CSRF non-applicable (backend bearer API, no cookie session) with replay protection "
                      "via idempotency keys and optimistic revision checks (SE11/SE12)",
            "test": "SE11",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-012",
            "asset": "approvals/cost state",
            "trust_boundary": "API / cost",
            "threat": "a stale approval (old revision/hash/catalog) unlocks a gate",
            "likelihood": "low",
            "impact": "high",
            "control": "hash-bound approvals + estimate-hash-bound budget approvals",
            "test": "SE12",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-TM-013",
            "asset": "rejected candidates / browser state / project references",
            "trust_boundary": "storage",
            "threat": "data outlives retention or a deletion receipt leaks deleted content",
            "likelihood": "low",
            "impact": "medium",
            "control": "retention cleanup + non-destructive invalidation + content-free deletion receipts",
            "test": "SE13",
            "residual_risk": "low",
            "severity": "low",
            "release_decision": "acceptable-for-0.1",
        },
    ]
    covered = {e["test"] for e in entries}
    return {
        "schema_version": "1.0.0",
        "gate": GATE,
        "candidate_sha": candidate_sha,
        "generated_at": utc_now_iso(),
        "trust_boundaries": TRUST_BOUNDARIES,
        "entry_count": len(entries),
        "covered_scenarios": sorted(covered),
        "notes": [
            "CSRF is non-applicable to the workspace command API (backend bearer "
            "tokens, no cookie sessions); replay protection is provided by "
            "X-Idempotency-Key dedup + optimistic revision checks (SE11/SE12).",
        ],
        "entries": entries,
    }


def build_open_findings(candidate_sha: str) -> Dict[str, Any]:
    """open_security_findings.json — known limitations with decisions.

    None are release-blocking (plan §17 gate). SEC-001 was a real gap found
    by SE01 and CLOSED in this phase (redact_shell_output now composes the
    core redactor) — it is recorded for traceability, not as open risk.
    """
    findings = [
        {
            "finding_id": "SEC-001",
            "title": "Shell output redaction gap for unquoted password=/API-key prefixes",
            "severity": "low",
            "status": "CLOSED",
            "impact": "redact_shell_output only masked sk-/bearer/quoted-password patterns; "
                      "unquoted password= and api_key= prefixes could survive in process output.",
            "mitigation": "Fixed in Phase 26: redact_shell_output now composes the canonical "
                          "core redactor (SE01 canary evidence passes).",
            "owner": "release-owner",
            "release_decision": "closed-by-fix",
        },
        {
            "finding_id": "SEC-002",
            "title": "Symlink/junction escape test not executable on hosts without symlink privilege",
            "severity": "low",
            "status": "OPEN",
            "impact": "On Windows hosts without Developer Mode, os.symlink raises WinError 1314; "
                      "the SE04 symlink sub-observation is recorded N/A on that host.",
            "mitigation": "PathSandbox enforces the boundary via resolve() on every platform; "
                          "CI on Linux runs the full symlink case; junction escape is covered by "
                          "the same resolve() boundary check.",
            "owner": "release-owner",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-003",
            "title": "Authenticated live-browser security tests are nightly/manual only",
            "severity": "low",
            "status": "OPEN",
            "impact": "Live Flow browser security scenarios are not run on every PR.",
            "mitigation": "Mock-browser policy/state tests run in PR CI; controlled nightly smoke "
                          "is bounded by the credit cap (plan §20.2).",
            "owner": "release-owner",
            "release_decision": "acceptable-for-0.1",
        },
        {
            "finding_id": "SEC-004",
            "title": "SSE/WebSocket cross-project event delivery is deployment-scoped",
            "severity": "low",
            "status": "OPEN",
            "impact": "The event envelope carries project_id; the delivery channel must scope by "
                      "project at the consumer boundary (SE11 demonstrates the check).",
            "mitigation": "Project-scoped channel check enforced at the consumer; documented in "
                          "audit_and_redaction.md.",
            "owner": "release-owner",
            "release_decision": "acceptable-for-0.1",
        },
    ]
    return {
        "schema_version": "1.0.0",
        "gate": GATE,
        "candidate_sha": candidate_sha,
        "generated_at": utc_now_iso(),
        "release_blocking_count": 0,
        "findings": findings,
    }


def build_phase_verdict(verdict: str, reasons: List[str], candidate_sha: str) -> Dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "gate": GATE,
        "candidate_sha": candidate_sha,
        "status": verdict,
        "derived_by": "scripts/verification/verify_phase26_security.py",
        "derived_at": utc_now_iso(),
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 26 evidence producer")
    parser.add_argument("--candidate-sha", required=True, help="40/64-hex candidate SHA")
    parser.add_argument("--out", default=None, help="evidence output dir (default: phase_26/<sha>)")
    args = parser.parse_args()

    if not evidence_lib.is_candidate_sha(args.candidate_sha):
        parser.error(f"--candidate-sha must be 40/64 lowercase hex, got {args.candidate_sha!r}")

    out = Path(args.out).resolve() if args.out else (DEFAULT_EVIDENCE_ROOT / args.candidate_sha)
    out.mkdir(parents=True, exist_ok=True)
    receipts_dir = out / "security_test_receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    scratch = Path(tempfile.mkdtemp(prefix="wa_phase26_scratch_"))
    try:
        # 1. Run every mandatory security scenario in its own isolated workdir.
        receipts: List[Dict[str, Any]] = []
        for scenario_id in REQUIRED_SCENARIO_IDS:
            scenario_work = scratch / scenario_id
            scenario_work.mkdir(parents=True, exist_ok=True)
            receipt = SECURITY_TEST_RUNNERS[scenario_id](scenario_work, args.candidate_sha)
            receipt["scenario_id"] = scenario_id
            receipt["input_hashes"] = [h for h in receipt.get("input_hashes", []) if h]
            receipt["output_hashes"] = [h for h in receipt.get("output_hashes", []) if h]
            receipts.append(receipt)
            evidence_lib.write_json(receipts_dir / f"{scenario_id}.json", receipt)
            print(f"  scenario {scenario_id}: all_observed={all(receipt['observed'].values())}")

        # 2. Aggregates (built FROM the receipts so the verifier can cross-check).
        threat_model = build_threat_model_manifest(args.candidate_sha)
        secret_report = build_secret_redaction_report(receipts, args.candidate_sha)
        api_report = build_api_authorization_report(receipts, args.candidate_sha)
        sandbox_report = build_file_network_sandbox_report(receipts, args.candidate_sha)
        privacy_receipt = build_privacy_deletion_receipt(receipts, args.candidate_sha)
        findings = build_open_findings(args.candidate_sha)

        # 3. Write all evidence files.
        evidence_lib.write_json(out / "threat_model_manifest.json", threat_model)
        evidence_lib.write_json(out / "secret_redaction_report.json", secret_report)
        evidence_lib.write_json(out / "api_authorization_report.json", api_report)
        evidence_lib.write_json(out / "file_network_sandbox_report.json", sandbox_report)
        evidence_lib.write_json(out / "privacy_deletion_receipt.json", privacy_receipt)
        evidence_lib.write_json(out / "open_security_findings.json", findings)

        # 4. Content-addressed evidence manifest.
        evidence_lib.write_json(
            out / "evidence_manifest.json",
            evidence_lib.build_evidence_manifest(out, args.candidate_sha),
        )

        # 5. Derive the phase verdict with the SAME verifier logic (no hard-code).
        from scripts.verification.verify_phase26_security import verify_production_evidence

        verdict, workstreams, reasons = verify_production_evidence(
            out, args.candidate_sha, require_phase_verdict=False
        )
        evidence_lib.write_json(
            out / "phase_verdict.json",
            build_phase_verdict(verdict, reasons, args.candidate_sha),
        )
        final_verdict, final_workstreams, final_reasons = verify_production_evidence(
            out, args.candidate_sha
        )
        print(f"Phase 26 verdict: {final_verdict}")
        for ws, ok in final_workstreams.items():
            print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
        for reason in final_reasons:
            print(f"  REASON: {reason}")
        return 0 if final_verdict == "PASSED" else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
