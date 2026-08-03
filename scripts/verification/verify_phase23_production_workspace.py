#!/usr/bin/env python3
"""
Phase 23 verification — VP23_PRODUCTION_WORKSPACE_VERIFIED (remediation plan 08, R3).

Evidence-mode verifier (R0 contract):
  python verify_phase23_production_workspace.py --evidence-dir <dir> --candidate-sha <sha>
  python verify_phase23_production_workspace.py --write-fixture <tempdir>

Gate VP23 passes only when every build/test receipt is DERIVED from a real
command execution (argv, cwd, lockfile hash, exit code, stdout/stderr hash,
duration, candidate SHA, output bundle hash) — never self-reported counters
(plan §15/§16). Hard-coded or un-run receipts are FAILED.

Required evidence (plan §16):
  api_integration_receipt.json    real API V2 calls (approve/reject/override/cost/stale)
  realtime_e2e_receipt.json       cursor replay, reconnect without duplicate actions
  web_command_receipt.json        real web unit/build command execution
  web_build_manifest.json         real output bundle hashes
  desktop_command_receipt.json    real desktop unit/build command execution
  desktop_build_manifest.json     real output bundle hashes
  accessibility_core_flow_receipt.json
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = ROOT / "artifacts" / "video_production" / "phase_23"

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


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_fixtures(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "workspace_contract_fixture.json", {
        "gate": "VP23_PRODUCTION_WORKSPACE_VERIFIED",
        "tier": "CONTRACT_TESTED",
        "generated_at": utc_now_iso(),
        "note": "Deterministic workspace contract checks (fixture only).",
        "checks": {
            "snapshot_structure_valid": True,
            "stale_revision_rejection": True,
            "override_reason_required": True,
            "cursor_replay_recovery": True,
        },
    })
    write_json(out_dir / "contract_verdict.json", {
        "gate": "VP23_PRODUCTION_WORKSPACE_VERIFIED",
        "tier": "CONTRACT_TESTED",
        "status": "CONTRACT_TESTED",
        "note": "Fixture data only — not production evidence.",
        "generated_at": utc_now_iso(),
    })
    return out_dir


# ---------------------------------------------------------------------------
# Production evidence validation (gate VP23)
# ---------------------------------------------------------------------------

REQUIRED_FILES = (
    "api_integration_receipt.json",
    "realtime_e2e_receipt.json",
    "web_command_receipt.json",
    "web_build_manifest.json",
    "desktop_command_receipt.json",
    "desktop_build_manifest.json",
    "accessibility_core_flow_receipt.json",
)


def _validate_command_receipt(
    receipt: dict | None,
    name: str,
    reasons: list[str],
    candidate_sha: str | None = None,
) -> bool:
    """Real command-execution receipt: argv, cwd, lockfile hash, exit code,
    stdout/stderr hashes, duration, candidate SHA, output bundle hash."""
    errors: list[str] = []
    if receipt is None:
        errors.append(f"{name}: receipt missing")
    else:
        for field in ("argv", "cwd", "lockfile_sha256", "exit_code",
                      "stdout_sha256", "stderr_sha256", "duration_seconds",
                      "candidate_sha", "output_bundle_sha256"):
            if field not in receipt:
                errors.append(f"{name}: missing field {field}")
        if not isinstance(receipt.get("argv"), list) or not receipt["argv"]:
            errors.append(f"{name}: argv must be a non-empty list (real command)")
        if receipt.get("exit_code") != 0:
            errors.append(f"{name}: exit_code must be 0 for a passing build/test")
        for key in ("lockfile_sha256", "stdout_sha256", "stderr_sha256", "output_bundle_sha256"):
            val = receipt.get(key)
            if not evidence_lib.is_sha256(val):
                errors.append(f"{name}: {key} must be 64-hex (real hash)")
        if not isinstance(receipt.get("duration_seconds"), (int, float)) or receipt.get("duration_seconds", 0) <= 0:
            errors.append(f"{name}: duration_seconds must be > 0 (real execution time)")
        sha = receipt.get("candidate_sha")
        if not evidence_lib.is_candidate_sha(sha):
            errors.append(f"{name}: candidate_sha must be 40/64-hex")
        elif candidate_sha and sha != candidate_sha:
            errors.append(
                f"{name}: candidate_sha mismatch (receipt {sha!r} != expected {candidate_sha!r})"
            )
    reasons.extend(errors)
    return not errors


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
        if name in ("web_command_receipt.json", "desktop_command_receipt.json"):
            ok = _validate_command_receipt(receipt, name, reasons, candidate_sha=candidate_sha)
            workstreams[name] = ok
            continue
        errors = validate_production_receipt(receipt or {}, candidate_sha=candidate_sha)
        workstreams[name] = not errors
        reasons.extend(f"{name}: {e}" for e in errors)

    # API integration: real HTTP calls with status codes + revision preservation.
    api = load_json(evidence_dir / "api_integration_receipt.json")
    if api:
        calls = api.get("api_calls")
        if not isinstance(calls, list) or not calls:
            reasons.append("api_integration_receipt: api_calls must be a non-empty list")
            workstreams["api_integration_receipt"] = False
        else:
            for call in calls:
                status = call.get("status_code")
                # Intentionally-expected rejections (409 stale, 403 unauthorized)
                # are valid evidence of fail-closed authorization, not failures.
                if call.get("expected"):
                    continue
                if not isinstance(status, int) or status >= 400:
                    reasons.append(
                        f"api_integration_receipt: {call.get('endpoint')} returned "
                        f"unexpected non-2xx status {status}"
                    )
                    workstreams["api_integration_receipt"] = False
                    break
                if call.get("path") and not call["path"].startswith("/api/v2"):
                    reasons.append("api_integration_receipt: calls must target API V2")
                    workstreams["api_integration_receipt"] = False
                    break
            else:
                workstreams["api_integration_receipt"] = workstreams.get("api_integration_receipt", True)

    # Realtime E2E: reconnect must not duplicate actions.
    rt = load_json(evidence_dir / "realtime_e2e_receipt.json")
    if rt:
        if rt.get("duplicate_actions_after_reconnect") is not False:
            reasons.append("realtime_e2e_receipt: reconnect duplicated actions")
            workstreams["realtime_e2e_receipt"] = False
        if rt.get("cursor_replay_verified") is not True:
            reasons.append("realtime_e2e_receipt: cursor replay not verified")
            workstreams["realtime_e2e_receipt"] = False
        if "realtime_e2e_receipt" not in workstreams:
            workstreams["realtime_e2e_receipt"] = True
    else:
        reasons.append("realtime_e2e_receipt.json missing")
        workstreams["realtime_e2e_receipt"] = False

    # Build manifests: real output bundle hashes matching dist artifacts.
    for name, dist_hint in (("web_build_manifest.json", "apps/web/dist"),
                            ("desktop_build_manifest.json", "apps/desktop/dist")):
        receipt = load_json(evidence_dir / name)
        if not receipt:
            workstreams[name] = False
            continue
        bundle = receipt.get("output_bundle")
        if not isinstance(bundle, dict) or not bundle:
            reasons.append(f"{name}: output_bundle map missing")
            workstreams[name] = False
            continue
        bundle_ok = True
        for rel, expected in bundle.items():
            candidate = ROOT / dist_hint / rel
            if not candidate.is_file():
                reasons.append(f"{name}: bundle file missing in repo dist: {rel}")
                bundle_ok = False
                continue
            if not evidence_lib.is_sha256(expected) or expected != evidence_lib.sha256_file(candidate):
                reasons.append(f"{name}: bundle hash mismatch for {rel}")
                bundle_ok = False
        workstreams[name] = bundle_ok

    verdict = derive_verdict(workstreams=workstreams, blocking_reasons=reasons)
    return verdict, workstreams, reasons


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=DEFAULT_EVIDENCE_DIR,
        description="Phase 23 evidence-mode verifier (VP23_PRODUCTION_WORKSPACE_VERIFIED)",
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

    print(f"Phase 23 verdict: {verdict}")
    for ws, ok in workstreams.items():
        print(f"  {ws}: {'PASS' if ok else 'FAIL'}")
    for reason in reasons:
        print(f"  REASON: {reason}")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
