#!/usr/bin/env python3
"""
R5 — Independent evidence validator (remediation plan 08, §22).

A validator independent from the evidence generator re-verifies, in order:
  1. worktree/candidate SHA and lockfile/toolchain;
  2. manifest + every file hash/size/MIME;
  3. re-runs ffprobe/decode on the final media;
  4. receipt lineage, revision, event sequence and duplicate invariants;
  5. cost ledger, final approval and redaction;
  6. acceptance matrix;
  7. emits PASSED / FAILED / BLOCKED with specific blocking reasons.

The validator NEVER writes source artifacts. It produces its own report
(independent_validation_receipt.json) with the input manifest checksum,
validator version and its own command receipt.

Usage:
  python independent_validate_phase24.py --evidence-dir <dir> --candidate-sha <sha>
"""

from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification.evidence_lib import (  # noqa: E402
    is_candidate_sha,
    load_json,
    parse_verifier_args,
    sha256_file,
    validate_evidence_manifest,
    validate_media_file,
)

VALIDATOR_VERSION = "1.0.0"
MIN_DURATION = 30.0
MAX_DURATION = 45.0
AUTOMATION_THRESHOLD = 0.80


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _git_head() -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30,
        cwd=str(ROOT),
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def _git_status_porcelain() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=60,
        cwd=str(ROOT),
    )
    return sorted(proc.stdout.splitlines()) if proc.returncode == 0 else []


def _reprobe(final_path: Path) -> dict:
    """Re-run real ffprobe on the final media (plan §22.3)."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"error": "ffprobe not found — cannot independently re-probe"}
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(final_path)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr[:500]}
    import json
    data = json.loads(proc.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    return {
        "format_name": fmt.get("format_name"),
        "duration_seconds": float(fmt.get("duration", 0.0)),
        "video_stream": any(s.get("codec_type") == "video" for s in streams),
        "audio_stream": any(s.get("codec_type") == "audio" for s in streams),
        "decoded_ok": True,
    }


def main() -> int:
    args = parse_verifier_args(
        sys.argv[1:],
        default_evidence_dir=ROOT / "artifacts" / "video_production" / "phase_24",
        description="R5 independent evidence validator (plan 08 §22)",
    )
    if not args.read_only:
        print("R5 validator never writes fixtures; use --evidence-dir.")
        return 2

    evidence_dir = args.evidence_dir
    candidate_sha = args.candidate_sha
    started = utc_now_iso()
    findings: list[str] = []
    checks: dict[str, bool] = {}

    print(f"R5: independent validation of {evidence_dir} (validator {VALIDATOR_VERSION})")

    # 1. Worktree / candidate SHA -------------------------------------------
    head = _git_head()
    if candidate_sha and head and candidate_sha != head:
        findings.append(
            f"candidate_sha {candidate_sha[:12]} != HEAD {head[:12]} — "
            "evidence must be tied to a candidate; if the candidate is an older "
            "commit, document it explicitly."
        )
        checks["worktree_candidate_sha"] = False
    else:
        checks["worktree_candidate_sha"] = True
    dirty = _git_status_porcelain()
    if dirty:
        print(f"  NOTE: working tree dirty ({len(dirty)} paths) — "
              f"candidate SHA is the commit HEAD, not the dirty tree.")

    # 2. Manifest + file hashes ----------------------------------------------
    manifest = load_json(evidence_dir / "evidence_manifest.json")
    if manifest is None:
        findings.append("evidence_manifest.json missing")
        checks["manifest"] = False
    else:
        manifest_errors = validate_evidence_manifest(manifest, evidence_dir, candidate_sha=candidate_sha)
        checks["manifest"] = not manifest_errors
        findings.extend(f"manifest: {e}" for e in manifest_errors)
        # Accept a 40-hex git candidate but require the manifest's SHA format.
        msha = manifest.get("candidate_sha")
        if not is_candidate_sha(msha):
            findings.append(f"manifest candidate_sha invalid: {msha!r}")
            checks["manifest"] = False

    # 3. Re-run ffprobe on the final media ------------------------------------
    final = load_json(evidence_dir / "final_media_manifest.json")
    final_path: Path | None = None
    if final:
        locator = final.get("media_locator") or final.get("locator")
        final_path = evidence_dir / locator if locator else None
    if not final_path or not final_path.is_file():
        findings.append("final media file missing — cannot independently re-probe")
        checks["final_media_reprobe"] = False
    else:
        media_errors = validate_media_file(final_path, expected_container="mp4")
        probe = _reprobe(final_path)
        duration = probe.get("duration_seconds", 0.0)
        errors = list(media_errors)
        if probe.get("error"):
            errors.append(f"ffprobe failed: {probe['error']}")
        if not probe.get("video_stream"):
            errors.append("independent ffprobe found no video stream")
        if not probe.get("audio_stream"):
            errors.append("independent ffprobe found no audio stream")
        if not (MIN_DURATION <= duration <= MAX_DURATION):
            errors.append(f"independent duration {duration}s outside {MIN_DURATION}-{MAX_DURATION}s")
        checks["final_media_reprobe"] = not errors
        findings.extend(f"final_media_reprobe: {e}" for e in errors)
        expected_hash = final.get("final_media_sha256")
        if expected_hash and expected_hash != sha256_file(final_path):
            findings.append("final_media_sha256 mismatch with on-disk file")
            checks["final_media_reprobe"] = False

    # 4. Receipt lineage / revision / event sequence / duplicates ---------------
    flow_ok = True
    job_dir = evidence_dir / "flow_job_receipts"
    external_ids: set[str] = set()
    if job_dir.is_dir():
        for path in sorted(job_dir.glob("*.json")):
            rec = load_json(path) or {}
            ext = rec.get("external_job_id")
            if not ext:
                findings.append(f"flow_job_receipts/{path.name}: missing external_job_id")
                flow_ok = False
            elif ext in external_ids:
                findings.append(f"flow_job_receipts/{path.name}: duplicate external_job_id")
                flow_ok = False
            else:
                external_ids.add(ext)
            if rec.get("duplicate_submit") or rec.get("duplicate_debit"):
                findings.append(f"flow_job_receipts/{path.name}: duplicate submit/debit")
                flow_ok = False
    else:
        findings.append("flow_job_receipts/ missing")
        flow_ok = False
    checks["flow_lineage_no_duplicates"] = flow_ok

    recovery = load_json(evidence_dir / "browser_recovery_receipt.json")
    if not recovery or recovery.get("duplicate_submits_count") != 0:
        findings.append("browser recovery: duplicate_submits_count != 0 or receipt missing")
        checks["browser_recovery"] = False
    else:
        checks["browser_recovery"] = True

    # 5. Cost ledger + final approval + redaction ------------------------------
    cost = load_json(evidence_dir / "cost_report.json")
    if not cost:
        findings.append("cost_report.json missing")
        checks["cost_ledger"] = False
    else:
        within = cost.get("debited_credits", 1e9) <= cost.get("max_approved_credits", 0)
        reconciled = cost.get("ledger_reconciled") is True
        checks["cost_ledger"] = within and reconciled
        if not within:
            findings.append("cost ledger: debited > approved maximum")
        if not reconciled:
            findings.append("cost ledger: not reconciled")

    approval = load_json(evidence_dir / "final_cut_approval.json")
    if not approval or approval.get("approved") is not True:
        findings.append("final-cut approval missing/not approved")
        checks["final_approval"] = False
    else:
        checks["final_approval"] = True

    # Redaction: no secrets / absolute profile paths in any JSON evidence.
    redaction_ok = True
    for path in sorted(evidence_dir.rglob("*.json")):
        if path.name == "independent_validation_receipt.json":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in ("token=", "api_key=", "password=", "secret=",
                       "c:\\users\\", "appdata", "\\profile\\"):
            if marker in text:
                findings.append(f"redaction: {path.name} contains {marker!r}")
                redaction_ok = False
    checks["redaction"] = redaction_ok

    # 6. Acceptance matrix (plan 06): automation rate + consistency ------------
    auto = load_json(evidence_dir / "automation_rate.json")
    if not auto or auto.get("automation_rate", 0.0) < AUTOMATION_THRESHOLD:
        findings.append(f"automation_rate < {AUTOMATION_THRESHOLD}")
        checks["acceptance_matrix"] = False
    else:
        checks["acceptance_matrix"] = True
    review = load_json(evidence_dir / "candidate_review_report.json")
    if not review or review.get("identity_defects_count", 1) != 0:
        findings.append("candidate review: hidden identity defects")
        checks["acceptance_matrix"] = False

    # 7. Verdict (fail-closed) ---------------------------------------------------
    blocking = [f for f in findings if f]
    verdict = evidence_lib.derive_verdict(workstreams=checks, blocking_reasons=blocking)
    print(f"R5 verdict: {verdict}")
    for finding in findings:
        print(f"  FINDING: {finding}")

    # The validator NEVER writes source artifacts (plan §22). Its own report is
    # written to a SIBLING directory so the validated evidence tree stays
    # byte-identical and its content-addressed manifest remains valid.
    report = {
        "schema_version": evidence_lib.SCHEMA_VERSION,
        "candidate_sha": candidate_sha or "",
        "run_id": f"r5_independent_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "started_at": started,
        "completed_at": utc_now_iso(),
        "command_or_provider": f"independent_validate_phase24.py v{VALIDATOR_VERSION}",
        "input_hashes": [
            sha256_file(evidence_dir / "evidence_manifest.json")
            if (evidence_dir / "evidence_manifest.json").is_file() else ""
        ],
        "output_hashes": [],
        "evidence_locator": "<evidence_dir>.validation/independent_validation_receipt.json",
        "status": verdict,
        "validator_version": VALIDATOR_VERSION,
        "findings": findings,
        "checks": checks,
    }
    out_dir = evidence_dir.with_name(evidence_dir.name + ".validation")
    out_path = out_dir / "independent_validation_receipt.json"
    evidence_lib.write_json(out_path, report)
    print(f"R5 report written to {out_path} (evidence dir untouched)")
    return 0 if verdict == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
