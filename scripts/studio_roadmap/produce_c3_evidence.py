"""Produce C3 Studio desktop shell gate evidence (studio.contract/v0.1).

Runs the desktop vitest suite plus the V3 API contract suite, scans the
Studio shell source for fake clients and sample identifiers, verifies the
real HTTP client is composed with hash-route navigation, and writes
``artifacts/studio_roadmap_01/c3/evidence.json`` and
``artifacts/studio_roadmap_01/c3/STUDIO_DESKTOP_SHELL_GATE_VERDICT.md``.

Usage: python scripts/studio_roadmap/produce_c3_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c3"
DESKTOP = REPO_ROOT / "apps" / "desktop"
STUDIO_PAGE = DESKTOP / "src" / "pages" / "StudioPage.tsx"
APP_TSX = DESKTOP / "src" / "App.tsx"

SAMPLE_ID_PATTERNS = [
    re.compile(r"vp_001"),
    re.compile(r"proj-alpha"),
    re.compile(r"proj-beta"),
]
FAKE_PATTERNS = [
    re.compile(r"\bFake\w*ApiClient\b"),
    re.compile(r"\bFakeStudio\w*\b"),
    re.compile(r"\bMockStudio\w*\b"),
]


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _run(cmd: list[str], cwd: Path) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    output = (proc.stdout + proc.stderr).strip()
    summary = ""
    for line in reversed(output.splitlines()):
        if line.strip().startswith("Test Files") or line.strip().startswith("Tests "):
            summary = line.strip()
            break
    if not summary:
        for line in reversed(output.splitlines()):
            if "passed" in line.lower() or "failed" in line.lower():
                summary = line.strip()
                break
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "summary": summary or (output.splitlines()[-1] if output else ""),
        "passed": proc.returncode == 0,
    }


def _desktop_vitest() -> dict:
    npx = r"C:\Users\Admin\AppData\Local\hermes\node\npx.cmd"
    if not Path(npx).exists():
        npx = "npx.cmd"
    return _run([npx, "vitest", "run", "--no-color"], DESKTOP)


def _python_v3() -> dict:
    return _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/unit/api/test_studio_v3_api.py",
            "tests/unit/api/test_openapi_snapshot.py",
            "--no-header",
        ],
        REPO_ROOT,
    )


def _scan_file(path: Path, patterns: list[re.Pattern]) -> list[str]:
    hits: list[str] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if any(p.search(line) for p in patterns):
            hits.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    return hits


def main() -> int:
    desktop = _desktop_vitest()
    python_v3 = _python_v3()

    page_src = STUDIO_PAGE.read_text(encoding="utf-8")
    fake_hits = _scan_file(STUDIO_PAGE, FAKE_PATTERNS)
    sample_hits = _scan_file(STUDIO_PAGE, SAMPLE_ID_PATTERNS)

    checks = {
        "desktop_suite_passes": desktop["passed"],
        "python_v3_contract_suite_passes": python_v3["passed"],
        "studio_shell_uses_real_client": "HttpStudioApiClient" in page_src
        and "FakeProductionApiClient" not in page_src,
        "hash_route_navigation_present": all(
            marker in page_src
            for marker in ["#/studio", "#/studio/series/", "#/studio/episodes/"]
        ),
        "no_fake_in_studio_shell": not fake_hits,
        "no_sample_ids_in_studio_shell": not sample_hits,
        "studio_nav_wired_in_app": "studio" in APP_TSX.read_text(encoding="utf-8")
        and "StudioPage" in APP_TSX.read_text(encoding="utf-8"),
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    evidence = {
        "evidence_id": "c3-studio-desktop-shell-gate",
        "plan": "C",
        "phase": "C3",
        "gate": "STUDIO_DESKTOP_SHELL_GATE",
        "verdict": verdict,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integration_sha": _git_sha(),
        "tests": {
            "desktop_vitest": desktop,
            "python_v3_contracts": python_v3,
        },
        "scans": {
            "fake_hits": fake_hits,
            "sample_id_hits": sample_hits,
        },
        "checks": checks,
        "studio_page_sha256": hashlib.sha256(STUDIO_PAGE.read_bytes()).hexdigest(),
        "composition_note": (
            "StudioPage composes HttpStudioApiClient over VITE_API_BASE or "
            "http://localhost:8000; V2 ProductionWorkspacePage keeps its legacy "
            "fake client behind the compatibility route (baseline defect, "
            "retired at STORY_UI_GATE per 90_MASTER_ACCEPTANCE_GATES.md)."
        ),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ARTIFACT_DIR / "STUDIO_DESKTOP_SHELL_GATE_VERDICT.md").write_text(
        _verdict_md(evidence), encoding="utf-8"
    )
    print(
        f"verdict={verdict} desktop={desktop['summary']} python={python_v3['summary']}"
    )
    return 0 if verdict == "PASS" else 1


def _verdict_md(evidence: dict) -> str:
    lines = [
        "# STUDIO_DESKTOP_SHELL_GATE — C3 verdict",
        "",
        "- Gate: STUDIO_DESKTOP_SHELL_GATE",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Integration SHA: `{evidence['integration_sha']}`",
        f"- Generated: {evidence['generated_at']}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in evidence["checks"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} — {name}")
    lines += [
        "",
        "## Test results",
        "",
    ]
    for name, res in evidence["tests"].items():
        lines.append(f"- `{res['command']}` ({name}) → {res['summary']}")
    lines += [
        "",
        "## Scans",
        "",
        f"- Fake-module hits in StudioPage: {evidence['scans']['fake_hits'] or 'none'}",
        f"- Sample-ID hits in StudioPage: {evidence['scans']['sample_id_hits'] or 'none'}",
        "",
        f"- StudioPage SHA256: `{evidence['studio_page_sha256']}`",
        "",
        f"- {evidence['composition_note']}",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/c3/evidence.json`",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
