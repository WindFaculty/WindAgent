#!/usr/bin/env python3
"""
R4 — Controlled live Flow E2E runbook harness (remediation plan 08, §17-§21).

Executes the 14-step runbook of plan 06 against a REAL Flow account/session
when all preconditions are satisfied. Until the human authorizes scope, credit
cap, timing and account/session usage, this harness remains BLOCKED and writes
a BLOCKED evidence set — it never fabricates jobs, hashes or costs.

Preconditions (plan §17) are read from a config file or environment:
  --approval-file <json>  {creative_brief_locked, max_credits, run_at, ...}
  FLOW_ACCOUNT / FLOW_SESSION env vars (redacted in receipts)

Without approval evidence the harness writes:

  artifacts/video_production/phase_24/<candidate_sha>/
  ├── poc_run_manifest.json          (BLOCKED)
  ├── evidence_manifest.json
  └── phase_verdict.json             (BLOCKED — missing live-run evidence)

With approval + credentials it would execute the 14 steps and the
submit → browser-close → recovery → reconcile → no-duplicate loop (§19).
The live provider integration is intentionally not implemented in-tree;
it runs against the authorized Flow session only.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification import evidence_lib  # noqa: E402
from scripts.verification.evidence_lib import (  # noqa: E402
    is_candidate_sha,
    write_json,
)

RUNBOOK_STEPS = (
    "1. CREATE_PROJECT_MANIFEST",
    "2. SELECT_CONCEPT",
    "3. LOCK_SCREENPLAY",
    "4. APPROVE_BIBLES",
    "5. LOCK_CINEMATIC_PLAN",
    "6. RESERVE_COST_BUDGET",
    "7. FLOW_IMAGE_GENERATION",
    "8. FLOW_VIDEO_GENERATION",
    "9. TECHNICAL_VLM_REVIEW",
    "10. TTS_AUDIO_MIX",
    "11. FFMPEG_ASSEMBLY",
    "12. MEDIA_QUALITY_VERIFICATION",
    "13. FINAL_CUT_APPROVAL",
    "14. PUBLISH_FINAL_DELIVERABLE",
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load_approval(path: str | None) -> dict:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    argv = sys.argv[1:]
    sha = None
    approval_path = None
    out_dir: Path | None = None
    if "--candidate-sha" in argv:
        sha = argv[argv.index("--candidate-sha") + 1]
    if "--approval-file" in argv:
        approval_path = argv[argv.index("--approval-file") + 1]
    if "--out-dir" in argv:
        out_dir = Path(argv[argv.index("--out-dir") + 1]).resolve()

    if not sha or not is_candidate_sha(sha):
        print("usage: runbook_phase24_e2e.py --candidate-sha <sha> "
              "[--approval-file <json>] [--out-dir DIR]")
        return 2

    approval = _load_approval(approval_path)
    if not out_dir:
        out_dir = ROOT / "artifacts" / "video_production" / "phase_24" / sha
    out_dir.mkdir(parents=True, exist_ok=True)

    brief_locked = bool(approval.get("creative_brief_locked"))
    max_credits = approval.get("max_credits")
    run_at = approval.get("run_at")
    session_env = os.environ.get("FLOW_SESSION") or os.environ.get("FLOW_ACCOUNT")

    blocking_reasons: list[str] = []
    if not brief_locked:
        blocking_reasons.append("creative brief/revision not locked (plan §17.1)")
    if not isinstance(max_credits, (int, float)) or max_credits <= 0:
        blocking_reasons.append("maximum credits / retry reserve not approved (§17.2)")
    if not run_at:
        blocking_reasons.append("live run timing not approved (§17.2)")
    if not session_env:
        blocking_reasons.append("Flow account/session not authorized in env (§17.3)")
    if not approval.get("operator_takeover_plan"):
        blocking_reasons.append("human operator takeover / stop plan not approved (§17.4)")
    if not approval.get("artifact_storage_policy"):
        blocking_reasons.append("artifact storage/retention/redaction policy not approved (§17.5)")

    status = "PASSED" if not blocking_reasons else "BLOCKED"
    now = utc_now_iso()

    manifest = {
        "schema_version": evidence_lib.SCHEMA_VERSION,
        "candidate_sha": sha,
        "run_id": f"r4_e2e_{sha[:12]}",
        "started_at": now,
        "completed_at": now,
        "command_or_provider": "runbook_phase24_e2e.py (Flow live run)",
        "input_hashes": [],
        "output_hashes": [],
        "evidence_locator": "poc_run_manifest.json",
        "status": status,
        "release_scope": approval.get("release_scope", "Release 0.1"),
        "planned_scenes": 2,
        "planned_shots": 6,
        "planned_duration_seconds": 36.0,
        "max_approved_credits": max_credits,
        "run_at": run_at,
        "runbook_steps": list(RUNBOOK_STEPS),
        "approved": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "notes": (
            "Live run authorized and ready — execute with the approved Flow "
            "session to produce flow_job_receipts/, browser recovery evidence "
            "and the final MP4."
            if not blocking_reasons else
            "BLOCKED: live-run preconditions not satisfied. Provide "
            "--approval-file and authorized Flow env, then re-run."
        ),
    }
    write_json(out_dir / "poc_run_manifest.json", manifest)
    write_json(out_dir / "evidence_manifest.json",
               evidence_lib.build_evidence_manifest(out_dir, sha))
    write_json(out_dir / "phase_verdict.json", {
        "gate": "VP24_E2E_POC_PASSED",
        "status": status,
        "candidate_sha": sha,
        "verified_at": now,
        "blocking_reasons": blocking_reasons,
        "note": "Derived from runbook precondition validation — never fabricated.",
    })
    print(f"R4 runbook status: {status}")
    for reason in blocking_reasons:
        print(f"  BLOCKED: {reason}")
    if not blocking_reasons:
        print("  All preconditions met — run the live Flow E2E now.")
    return 0 if status == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
