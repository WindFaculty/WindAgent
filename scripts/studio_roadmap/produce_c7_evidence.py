"""Produce fail-closed C7 REAL_VERTICAL_SLICE_GATE evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
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
EVIDENCE_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c7"
RAW_DIR = REPO_ROOT / ".tmp" / "studio-c7"
sys.path.insert(0, str(REPO_ROOT))

from scripts.studio_roadmap.c7_desktop_evidence import (  # noqa: E402
    capture_c7_desktop_evidence,
    probe_c7_desktop_environment,
)
from scripts.studio_roadmap.c7_slice_harness import (  # noqa: E402
    CANONICAL_MODEL,
    PROVIDER_MODEL,
    assert_report,
    run_slice,
    seed_runtime,
)
from scripts.studio_roadmap.certification_launcher import (  # noqa: E402
    CertificationLauncher,
    CertificationProcessError,
    configure_utf8_stdio,
    prepare_certification_database,
)

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}", re.I),
    re.compile(
        r"(api[_-]?key|password|secret|authorization)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        re.I,
    ),
    # Query-string credentials (e.g. legacy Gemini ?key=) captured in
    # process log tails — URL text, not a labeled assignment.
    re.compile(r"[?&]key=[A-Za-z0-9._-]{8,}"),
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return result.stdout.rstrip() if result.returncode == 0 else ""


def _head_sha() -> str:
    return _git("rev-parse", "HEAD") or "unknown"


def _dirty_paths() -> List[str]:
    return [line[3:] for line in _git("status", "--porcelain=v1").splitlines() if line]


def _source_dirty_paths(paths: List[str]) -> List[str]:
    allowed = ("artifacts/studio_roadmap_01/c7/",)
    return [
        path
        for path in paths
        if not path.replace("\\", "/").startswith(allowed)
    ]


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "workspace"


def _json_file(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _versions(integration_sha: str) -> Dict[str, Any]:
    desktop = _json_file(REPO_ROOT / "apps" / "desktop" / "package.json")
    tauri = _json_file(
        REPO_ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
    )
    return {
        "integration_sha": integration_sha,
        "python": platform.python_version(),
        "os": platform.platform(),
        "api_package": _package_version("windagent-api"),
        "worker_package": _package_version("windagent-worker"),
        "desktop_package": desktop.get("version") or "unknown",
        "tauri_app": tauri.get("version") or "unknown",
        "canonical_model": CANONICAL_MODEL,
        "provider_model": PROVIDER_MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _redaction_safe(value: Any) -> bool:
    blob = json.dumps(value, ensure_ascii=False)
    return not any(pattern.search(blob) for pattern in SECRET_PATTERNS)


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def _blocked_evidence(
    evidence: Dict[str, Any], *, stage: str, failure: Exception
) -> Dict[str, Any]:
    broken = {
        "stage": stage,
        "failure": type(failure).__name__,
        "detail": str(failure),
    }
    evidence.update(
        {
            "verdict": "BLOCKED",
            "checks": evidence.get("checks", {}),
            "first_broken_hop": broken,
        }
    )
    redaction_safe = _redaction_safe(evidence)
    if not redaction_safe:
        evidence = _redact_secrets(evidence)
    evidence["redaction_safe"] = redaction_safe
    return evidence


def _write(evidence: Dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence_path = EVIDENCE_DIR / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    checksum = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    lines = [
        "# REAL_VERTICAL_SLICE_GATE — C7 verdict",
        "",
        f"- Contract: {evidence['contract']}",
        f"- Gate: {evidence['gate']}",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Integration SHA: `{evidence['integration_sha']}`",
        f"- Evidence SHA-256: `{checksum}`",
        "",
    ]
    if evidence.get("first_broken_hop"):
        lines.extend(
            [
                "## First broken hop",
                "",
                f"```json\n{json.dumps(evidence['first_broken_hop'], indent=2, ensure_ascii=False)}\n```",
                "",
            ]
        )
    if evidence.get("checks"):
        lines.extend(["## Mandatory checks", ""])
        for name, check in sorted(evidence["checks"].items()):
            passed = check.get("pass") if isinstance(check, dict) else bool(check)
            detail = check.get("detail", "") if isinstance(check, dict) else ""
            lines.append(
                f"- {'PASS' if passed else 'FAIL'} — {name}: {str(detail)[:500]}"
            )
        lines.append("")
    lines.extend(
        [
            "## Evidence policy",
            "",
            "- Source must be clean before any certification process starts.",
            "- API and worker are launcher-owned, independently supervised processes.",
            "- Durable database access is read-only evidence reconstruction after seeding.",
            "- Desktop proof comes from the real Tauri/WebView2 window and accessibility tree.",
            "- No reviewer sign-off is created by this producer.",
            "",
            "Evidence JSON: `artifacts/studio_roadmap_01/c7/evidence.json`",
            f"Generated: {evidence['versions']['generated_at']}",
            "",
        ]
    )
    (EVIDENCE_DIR / "REAL_VERTICAL_SLICE_GATE_VERDICT.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _base_evidence(head: str, dirty: List[str], source_dirty: List[str]) -> Dict[str, Any]:
    return {
        "contract": "studio.contract/v0.1",
        "gate": "REAL_VERTICAL_SLICE_GATE",
        "integration_sha": head,
        "versions": _versions(head),
        "source_worktree_clean": not source_dirty,
        "source_dirty_paths": source_dirty,
        "all_dirty_paths": dirty,
    }


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api", default=os.getenv("WINDAGENT_API_BASE", "http://127.0.0.1:8878")
    )
    parser.add_argument(
        "--db",
        default=os.getenv(
            "WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///windagent_cert.db"
        ),
    )
    parser.add_argument("--seed-only", action="store_true")
    parser.add_argument("--desktop-timeout", type=float, default=300)
    args = parser.parse_args()

    head = _head_sha()
    dirty = _dirty_paths()
    source_dirty = _source_dirty_paths(dirty)
    evidence = _base_evidence(head, dirty, source_dirty)
    if source_dirty:
        evidence.update(
            {
                "verdict": "BLOCKED",
                "checks": {},
                "redaction_safe": True,
                "first_broken_hop": {
                    "stage": "source.preflight",
                    "failure": "source_worktree_dirty",
                    "paths": source_dirty,
                },
            }
        )
        _write(evidence)
        print(json.dumps({"verdict": "BLOCKED", "paths": source_dirty}))
        return 2

    try:
        evidence["desktop_preflight"] = probe_c7_desktop_environment()
    except Exception as exc:
        evidence = _blocked_evidence(
            evidence, stage="desktop.preflight", failure=exc
        )
        _write(evidence)
        print(
            json.dumps(
                {
                    "verdict": "BLOCKED",
                    "first_broken_hop": evidence["first_broken_hop"],
                }
            )
        )
        return 2

    try:
        prepare_certification_database(args.db)
        evidence["runtime_seed"] = asyncio.run(seed_runtime(args.db))
    except Exception as exc:
        evidence = _blocked_evidence(evidence, stage="runtime.seed", failure=exc)
        _write(evidence)
        print(
            json.dumps(
                {
                    "verdict": "BLOCKED",
                    "first_broken_hop": evidence["first_broken_hop"],
                }
            )
        )
        return 2
    if args.seed_only:
        evidence.update(
            {
                "verdict": "BLOCKED",
                "checks": {},
                "redaction_safe": True,
                "first_broken_hop": {
                    "stage": "runtime.seed",
                    "failure": "seed_only_requested",
                },
            }
        )
        _write(evidence)
        return 2

    launcher = CertificationLauncher(
        db_url=args.db,
        api_base=args.api,
        canonical_model=CANONICAL_MODEL,
        log_dir=(
            RAW_DIR
            / "processes"
            / f"{head[:12]}-{hashlib.sha256(args.db.encode('utf-8')).hexdigest()[:12]}"
        ),
    )
    stage = "process.start"
    failure: Exception | None = None
    try:
        launcher.start_all()
        stage = "c7.public_vertical_slice"
        report = launcher.run_guarded(
            lambda health_check: run_slice(
                args.api, db_url=args.db, health_check=health_check
            )
        )
        assert_report(report)
        evidence.update(report)
        stage = "desktop.tauri_display"
        evidence["desktop"] = launcher.run_guarded(
            lambda health_check: capture_c7_desktop_evidence(
                api_base=args.api,
                episode_id=report["episode_id"],
                run_id=report["run_id"],
                output_dir=EVIDENCE_DIR,
                timeout_seconds=args.desktop_timeout,
                health_check=health_check,
            )
        )
        if evidence["desktop"].get("pass") is not True:
            raise RuntimeError("desktop evidence did not pass")
    except Exception as exc:  # every failure preserves the first broken boundary
        failure = exc
    finally:
        launcher.stop_all()

    evidence["process_receipts"] = _json_file(launcher.receipt_path)
    if failure is None:
        evidence["redaction_safe"] = _redaction_safe(evidence)
        if not evidence["redaction_safe"]:
            failure = RuntimeError("C7 evidence redaction scan failed")
            stage = "evidence.redaction"
    if failure is not None:
        if isinstance(failure, CertificationProcessError):
            broken = failure.first_broken_hop
        else:
            broken = {
                "stage": stage,
                "failure": type(failure).__name__,
                "detail": str(failure),
            }
        evidence.update(
            {
                "verdict": "FAIL",
                "first_broken_hop": broken,
                "checks": evidence.get("checks", {}),
            }
        )
        redaction_safe = _redaction_safe(evidence)
        if not redaction_safe:
            evidence = _redact_secrets(evidence)
        evidence["redaction_safe"] = redaction_safe
    else:
        evidence.update({"verdict": "PASS", "first_broken_hop": None})

    _write(evidence)
    print(
        json.dumps(
            {
                "verdict": evidence["verdict"],
                "first_broken_hop": evidence.get("first_broken_hop"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
