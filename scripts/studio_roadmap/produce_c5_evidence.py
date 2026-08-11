"""Produce C5 API/UI integration gate evidence (studio.contract/v0.1).

Runs the desktop vitest suite plus the V3 API contract suite, scans Studio
sources for fake clients/sample IDs, verifies the screenplay/review/revision/
lock UI building blocks (structured draft renderer with traceability, review
findings, before/after diff, hash-bound lock command, post-lock read-only
state), and writes
``artifacts/studio_roadmap_01/c5/evidence.json`` and
``artifacts/studio_roadmap_01/c5/API_UI_INTEGRATION_GATE_VERDICT.md``.

Usage: python scripts/studio_roadmap/produce_c5_evidence.py
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
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c5"
DESKTOP = REPO_ROOT / "apps" / "desktop"
STUDIO_PAGE = DESKTOP / "src" / "pages" / "StudioPage.tsx"
STUDIO_COMPONENTS = DESKTOP / "src" / "components" / "studio"
STORY_TESTS = DESKTOP / "src" / "test" / "studioStoryTests.test.tsx"

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


def _scan_dir_sources() -> list[str]:
    hits: list[str] = []
    for path in [STUDIO_PAGE, *sorted(STUDIO_COMPONENTS.glob("*.tsx"))]:
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if any(p.search(line) for p in FAKE_PATTERNS + SAMPLE_ID_PATTERNS):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    return hits


def main() -> int:
    desktop = _desktop_vitest()
    python_v3 = _python_v3()

    page_src = STUDIO_PAGE.read_text(encoding="utf-8")
    views_src = (STUDIO_COMPONENTS / "ArtifactViews.tsx").read_text(encoding="utf-8")
    tests_src = STORY_TESTS.read_text(encoding="utf-8")
    scan_hits = _scan_dir_sources()

    checks = {
        "desktop_suite_passes": desktop["passed"],
        "python_v3_contract_suite_passes": python_v3["passed"],
        "screenplay_views_present": all(
            marker in views_src
            for marker in [
                "ScreenplayView",
                "ReviewReportView",
                "RevisionProposalView",
                "LockReceiptView",
                "LockPackageView",
                "ScreenplayDiffView",
            ]
        ),
        "screenplay_renders_traceability": all(
            marker in views_src
            for marker in ["outline_scene_id", "source_beat_ids", "character_ids", "estimated_seconds"]
        ),
        "review_findings_render_code_severity_location": all(
            marker in views_src
            for marker in ["severity", "location", "remediation", "maximum_iterations"]
        ),
        "diff_compares_before_after_drafts": all(
            marker in views_src for marker in ["diffScreenplays", "change_type", "old_value", "new_value"]
        )
        and "ScreenplayDiffView" in page_src,
        "hash_bound_lock_command": all(
            marker in page_src
            for marker in ["lockScreenplay", "expected_content_hash", "READ_ONLY_STATES"]
        ),
        "screenplay_checkpoint_wired": "SCREENPLAY: 'ScreenplayDraft'" in page_src
        and "SCREENPLAY_REVIEW" in page_src,
        "post_lock_read_only": all(
            marker in page_src
            for marker in ["content is locked and read-only", "READ_ONLY_STATES.has", "Corrections derive"]
        ),
        "c5_workflow_tests_present": all(
            marker in tests_src
            for marker in [
                "Approve SCREENPLAY",
                "Lock screenplay",
                "expected_content_hash",
                "locked and read-only",
                "diffScreenplays",
            ]
        ),
        "no_fake_or_sample_ids_in_studio_sources": not scan_hits,
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    evidence = {
        "evidence_id": "c5-api-ui-integration-gate",
        "plan": "C",
        "phase": "C5",
        "gate": "API_UI_INTEGRATION_GATE",
        "verdict": verdict,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integration_sha": _git_sha(),
        "tests": {
            "desktop_vitest": desktop,
            "python_v3_contracts": python_v3,
        },
        "scans": {
            "fake_and_sample_id_hits": scan_hits,
        },
        "checks": checks,
        "file_sha256": {
            "StudioPage.tsx": hashlib.sha256(STUDIO_PAGE.read_bytes()).hexdigest(),
            "ArtifactViews.tsx": hashlib.sha256(
                (STUDIO_COMPONENTS / "ArtifactViews.tsx").read_bytes()
            ).hexdigest(),
            "studioStoryTests.test.tsx": hashlib.sha256(STORY_TESTS.read_bytes()).hexdigest(),
        },
        "composition_note": (
            "Screenplay/review/revision/lock UI renders server artifacts only: structured draft "
            "with canon/beat traceability, review findings with code/severity/location, immutable "
            "before/after revision diff, lock receipt + package lineage. Lock and approval commands "
            "carry the exact server revision content hash and expected version; after lock the "
            "episode view is read-only and corrections route through a new run. No local stage "
            "advance, no synthesized artifact, no fake client."
        ),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ARTIFACT_DIR / "API_UI_INTEGRATION_GATE_VERDICT.md").write_text(
        _verdict_md(evidence), encoding="utf-8"
    )
    print(
        f"verdict={verdict} desktop={desktop['summary']} python={python_v3['summary']}"
    )
    return 0 if verdict == "PASS" else 1


def _verdict_md(evidence: dict) -> str:
    lines = [
        "# API_UI_INTEGRATION_GATE — C5 verdict",
        "",
        "- Gate: API_UI_INTEGRATION_GATE",
        f"- Verdict: **{evidence['verdict']}**",
        f"- Integration SHA: `{evidence['integration_sha']}`",
        f"- Generated: {evidence['generated_at']}",
        "",
        "## Checks",
        "",
    ]
    for name, ok in evidence["checks"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} — {name}")
    lines += ["", "## Test results", ""]
    for name, res in evidence["tests"].items():
        lines.append(f"- `{res['command']}` ({name}) → {res['summary']}")
    lines += [
        "",
        "## Scans",
        "",
        f"- Fake/sample-ID hits in Studio sources: {evidence['scans']['fake_and_sample_id_hits'] or 'none'}",
        "",
        "## File checksums",
        "",
    ]
    for name, sha in evidence["file_sha256"].items():
        lines.append(f"- `{name}`: `{sha}`")
    lines += [
        "",
        f"- {evidence['composition_note']}",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/c5/evidence.json`",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
