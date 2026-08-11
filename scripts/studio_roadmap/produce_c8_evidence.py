"""Produce C8 ``RECOVERY_VERTICAL_SLICE_GATE`` evidence.

PASS is intentionally impossible from a dirty tree or without a same-SHA C7
PASS.  In those cases the script writes a deterministic BLOCKED report and
does not start/stop any processes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c8"
C7_EVIDENCE = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c7" / "evidence.json"
RAW_DIR = REPO_ROOT / ".tmp" / "studio-c8"

sys.path.insert(0, str(REPO_ROOT))

from scripts.studio_roadmap.c7_slice_harness import seed_runtime  # noqa: E402
from scripts.studio_roadmap.c8_recovery_harness import (  # noqa: E402
    ManagedTopology,
    assert_recovery_report,
    run_recovery_slice,
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}", re.I),
    re.compile(r"(api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"]{8,}", re.I),
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=20
    )
    return result.stdout.rstrip() if result.returncode == 0 else ""


def _head_sha() -> str:
    return _git("rev-parse", "HEAD") or "unknown"


def _dirty_paths() -> List[str]:
    return [line[3:] for line in _git("status", "--porcelain=v1").splitlines() if line]


def _source_dirty_paths(paths: List[str]) -> List[str]:
    allowed = (
        "artifacts/studio_roadmap_01/c7/",
        "artifacts/studio_roadmap_01/c8/",
    )
    return [path for path in paths if not path.replace("\\", "/").startswith(allowed)]


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _integration_sha(evidence: Dict[str, Any]) -> str:
    return str(
        evidence.get("integration_sha")
        or (evidence.get("versions") or {}).get("integration_sha")
        or (evidence.get("git") or {}).get("head_sha")
        or ""
    )


def preflight() -> Dict[str, Any]:
    head = _head_sha()
    dirty = _dirty_paths()
    source_dirty = _source_dirty_paths(dirty)
    c7 = _load_json(C7_EVIDENCE)
    blockers: List[str] = []
    if source_dirty:
        blockers.append("source_worktree_dirty")
    if not c7:
        blockers.append("c7_evidence_missing")
    elif c7.get("verdict") != "PASS":
        blockers.append("c7_not_pass")
    elif c7.get("redaction_safe") is not True:
        blockers.append("c7_redaction_scan_not_pass")
    if c7 and _integration_sha(c7) != head:
        blockers.append("c7_integration_sha_mismatch")
    if c7 and not c7.get("series_id"):
        blockers.append("c7_series_id_missing")
    return {
        "head_sha": head,
        "source_worktree_clean": not source_dirty,
        "dirty_paths": dirty,
        "source_dirty_paths": source_dirty,
        "c7_path": C7_EVIDENCE.relative_to(REPO_ROOT).as_posix(),
        "c7_present": bool(c7),
        "c7_verdict": c7.get("verdict"),
        "c7_integration_sha": _integration_sha(c7),
        "series_id": c7.get("series_id"),
        "blockers": blockers,
    }


def _run_ui_recovery_tests() -> Dict[str, Any]:
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    commands = [
        (
            "studio_state_cursor",
            [npm, "test", "--", "src/__tests__/store.test.ts"],
            REPO_ROOT / "frontend" / "packages" / "studio-state",
        ),
        (
            "desktop_server_truth",
            [npm, "test", "--", "src/test/studioStoryTests.test.tsx"],
            REPO_ROOT / "apps" / "desktop",
        ),
    ]
    results: Dict[str, Any] = {}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, command, cwd in commands:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        raw = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raw_path = RAW_DIR / f"{name}.log"
        raw_path.write_text(raw, encoding="utf-8")
        results[name] = {
            "command": " ".join(command),
            "exit_code": result.returncode,
            "tail": raw.splitlines()[-1] if raw else "",
            "raw_log": raw_path.relative_to(REPO_ROOT).as_posix(),
            "raw_log_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        }
    return results


def _redaction_safe(value: Any) -> bool:
    blob = json.dumps(value, ensure_ascii=False)
    return not any(pattern.search(blob) for pattern in SECRET_PATTERNS)


def _base_evidence(pre: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase": "C8",
        "gate": "RECOVERY_VERTICAL_SLICE_GATE",
        "contract": "studio.contract/v0.1",
        "integration_sha": pre["head_sha"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "raw_log_retention": ".tmp/studio-c8 (local/CI artifact only; not gate authority)",
        },
        "preflight": pre,
    }


def _write(evidence: Dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence_path = EVIDENCE_DIR / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    checksum = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    lines = [
        "# RECOVERY_VERTICAL_SLICE_GATE — C8 verdict",
        "",
        f"- Contract: {evidence['contract']}",
        f"- Gate: {evidence['gate']}",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Integration SHA: `{evidence['integration_sha']}`",
        f"- Evidence SHA-256: `{checksum}`",
        "",
    ]
    if evidence.get("blockers"):
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {item}" for item in evidence["blockers"])
        lines.append("")
    if evidence.get("checks"):
        lines.extend(["## Checks", ""])
        lines.extend(
            f"- {'PASS' if passed else 'FAIL'} — {name}"
            for name, passed in evidence["checks"].items()
        )
        lines.append("")
    lines.extend(
        [
            "## Evidence policy",
            "",
            "- The harness mutates Studio state only through the public V3 API.",
            "- Database reads observe claims, generations and duplicates; no row repair is allowed.",
            "- The only queue operation is an expected-to-fail stale-fence renewal.",
            "- Raw process/test logs stay under `.tmp/studio-c8` or CI artifact storage.",
            "",
            "Evidence JSON: `artifacts/studio_roadmap_01/c8/evidence.json`",
            f"Generated: {evidence['generated_at']}",
            "",
        ]
    )
    (EVIDENCE_DIR / "RECOVERY_VERTICAL_SLICE_GATE_VERDICT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8878")
    parser.add_argument(
        "--db",
        default=os.getenv("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent_cert.db"),
    )
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    pre = preflight()
    evidence = _base_evidence(pre)
    if pre["blockers"] or args.preflight_only:
        evidence.update(
            {
                "verdict": "BLOCKED",
                "blockers": pre["blockers"] or ["preflight_only_requested"],
                "checks": {},
            }
        )
        _write(evidence)
        print(json.dumps({"verdict": "BLOCKED", "blockers": evidence["blockers"]}))
        return 2

    topology = ManagedTopology(db_url=args.db, api_base=args.api, log_dir=RAW_DIR)
    try:
        evidence["runtime_seed"] = asyncio.run(seed_runtime(args.db))
        report = run_recovery_slice(
            api_base=args.api,
            db_url=args.db,
            series_id=pre["series_id"],
            topology=topology,
        )
        ui = _run_ui_recovery_tests()
        report["checks"]["desktop_cursor_recovery_contract"] = all(
            result["exit_code"] == 0 for result in ui.values()
        )
        report["checks_total"] = len(report["checks"])
        report["checks_passed"] = sum(bool(value) for value in report["checks"].values())
        assert_recovery_report(report)
        evidence.update(report)
        evidence["ui_recovery_tests"] = ui
        evidence["redaction_safe"] = _redaction_safe(evidence)
        if not evidence["redaction_safe"]:
            raise RuntimeError("C8 evidence redaction scan failed")
        evidence["verdict"] = "PASS"
        evidence["blockers"] = []
    except Exception as exc:  # evidence must preserve the first broken boundary
        evidence.update(
            {
                "verdict": "FAIL",
                "blockers": [f"{type(exc).__name__}: {exc}"],
                "checks": evidence.get("checks", {}),
            }
        )
    finally:
        topology.close()

    _write(evidence)
    print(json.dumps({"verdict": evidence["verdict"], "blockers": evidence["blockers"]}))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
