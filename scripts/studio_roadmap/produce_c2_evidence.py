"""Produce C2 Studio client/state gate evidence (studio.contract/v0.1).

Runs the studio-client/studio-state/studio-contracts vitest suites, scans
production sources for fake modules and fixed sample IDs, verifies existing
frontend packages stay green, and writes
``artifacts/studio_roadmap_01/c2/evidence.json`` and
``artifacts/studio_roadmap_01/c2/STUDIO_CLIENT_STATE_GATE_VERDICT.md``.

Usage: python scripts/studio_roadmap/produce_c2_evidence.py
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
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c2"
FRONTEND = REPO_ROOT / "frontend"
PACKAGES = FRONTEND / "packages"

SAMPLE_ID_PATTERNS = [
    re.compile(r"vp_001"),
    re.compile(r"proj-alpha"),
    re.compile(r"proj-beta"),
    re.compile(r"rev-[a-z0-9-]+-v1"),
]

FAKE_PATTERNS = [
    re.compile(r"\bFake\w*ProductionApiClient\b"),
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
        if "Tests " in line or "failed" in line.lower():
            summary = line.strip()
            break
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "summary": summary or output.splitlines()[-1] if output else "",
        "passed": proc.returncode == 0,
    }


def _vitest(package: str) -> dict:
    npx = r"C:\Users\Admin\AppData\Local\hermes\node\npx.cmd"
    if not Path(npx).exists():  # fall back to PATH lookup
        npx = "npx.cmd"
    return _run([npx, "vitest", "run", "--no-color"], PACKAGES / package)


def _scan(package: str, patterns: list[re.Pattern]) -> list[str]:
    hits: list[str] = []
    src = PACKAGES / package / "src"
    if not src.is_dir():
        return hits
    for path in sorted(src.rglob("*.ts")):
        if "__tests__" in path.parts or "__mocks__" in path.parts:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(p.search(line) for p in patterns):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    return hits


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    client = _vitest("studio-client")
    state = _vitest("studio-state")
    contracts = _vitest("studio-contracts")
    production_state = _vitest("production-state")

    fake_hits = []
    sample_hits = []
    for pkg in ("studio-client", "studio-state"):
        fake_hits += _scan(pkg, FAKE_PATTERNS)
        sample_hits += _scan(pkg, SAMPLE_ID_PATTERNS)

    checks = {
        "client_tests_pass": client["passed"],
        "state_tests_pass": state["passed"],
        "contracts_roundtrip_pass": contracts["passed"],
        "existing_frontend_untouched": production_state["passed"],
        "no_fake_in_production_src": not fake_hits,
        "no_fixed_sample_ids": not sample_hits,
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    evidence = {
        "evidence_id": "c2-studio-client-state-gate",
        "plan": "C",
        "phase": "C2",
        "gate": "STUDIO_CLIENT_STATE_GATE",
        "verdict": verdict,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integration_sha": _git_sha(),
        "tests": {
            "studio_client": client,
            "studio_state": state,
            "studio_contracts": contracts,
            "production_state": production_state,
        },
        "scans": {
            "fake_hits": fake_hits,
            "sample_id_hits": sample_hits,
        },
        "checks": checks,
        "client_source_sha256": _checksum(PACKAGES / "studio-client" / "src" / "HttpStudioApiClient.ts"),
        "state_source_sha256": _checksum(PACKAGES / "studio-state" / "src" / "StudioStore.ts"),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ARTIFACT_DIR / "STUDIO_CLIENT_STATE_GATE_VERDICT.md").write_text(
        _verdict_md(evidence), encoding="utf-8"
    )
    print(f"verdict={verdict} client={client['summary']} state={state['summary']} contracts={contracts['summary']} prod_state={production_state['summary']}")
    return 0 if verdict == "PASS" else 1


def _verdict_md(evidence: dict) -> str:
    lines = [
        "# STUDIO_CLIENT_STATE_GATE — C2 verdict",
        "",
        f"- Gate: STUDIO_CLIENT_STATE_GATE",
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
        f"- Fake-module hits in production src: {evidence['scans']['fake_hits'] or 'none'}",
        f"- Fixed sample-ID hits in production src: {evidence['scans']['sample_id_hits'] or 'none'}",
        "",
        f"- HttpStudioApiClient SHA256: `{evidence['client_source_sha256']}`",
        f"- StudioStore SHA256: `{evidence['state_source_sha256']}`",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/c2/evidence.json`",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
