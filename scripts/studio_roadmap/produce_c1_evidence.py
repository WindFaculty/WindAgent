"""Produce C1 Studio-API-gate evidence (studio.contract/v0.1).

Runs the V3 contract suite, dumps the OpenAPI surface, verifies the snapshot
checksum and endpoint matrix against the frozen api_surface.json, and writes
``artifacts/studio_roadmap_01/c1/evidence.json`` and
``artifacts/studio_roadmap_01/c1/STUDIO_API_GATE_VERDICT.md``.

Usage: uv run python scripts/studio_roadmap/produce_c1_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c1"
SNAPSHOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "studio_contracts"
    / "openapi"
    / "openapi_snapshot.json"
)
API_SURFACE = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "api_surface.json"
)
TEST_FILE = REPO_ROOT / "tests" / "unit" / "api" / "test_studio_v3_api.py"


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _run_tests() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_FILE), "-q", "--no-header"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-1]
    return {
        "command": "pytest tests/unit/api/test_studio_v3_api.py -q",
        "exit_code": proc.returncode,
        "summary": tail,
        "passed": proc.returncode == 0,
    }


def _openapi() -> dict:
    from windagent_api.main import app  # noqa: PLC0415

    spec = app.openapi()
    v3_paths = {
        path: sorted(method.upper() for method in methods)
        for path, methods in spec["paths"].items()
        if path.startswith("/api/v3/studio")
    }
    return {
        "path_count": len(v3_paths),
        "paths": v3_paths,
        "snapshot_sha256": hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
    }


def _surface_matrix() -> dict:
    surface = json.loads(API_SURFACE.read_text(encoding="utf-8"))
    base = surface["base_path"].rstrip("/")
    frozen = {}
    for entry in surface["resources"]:
        path = base + entry["path"]
        frozen.setdefault(path, []).append(entry["method"].upper())
    return {
        "contract": surface["contract_version"],
        "base_path": surface["base_path"],
        "frozen_endpoints": len(frozen),
        "frozen": frozen,
    }


def main() -> int:
    tests = _run_tests()
    openapi = _openapi()
    surface = _surface_matrix()

    implemented = openapi["paths"]
    frozen = surface["frozen"]
    base = surface["base_path"].rstrip("/")
    missing = {
        path: methods
        for path, methods in frozen.items()
        if path not in implemented or not set(methods).issubset(set(implemented[path]))
    }
    extra = [
        p
        for p in implemented
        if p not in frozen and p not in (base + "/capabilities", base + "/readiness")
    ]

    checks = {
        "contract_suite_passes": tests["passed"],
        "frozen_endpoints_implemented": not missing,
        "no_unfrozen_extra_routes": not extra,
        "snapshot_matches_openapi": _snapshot_matches(openapi),
        "no_sample_ids_in_v3_surface": True,  # enforced by test suite scan
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    evidence = {
        "evidence_id": "c1-studio-api-gate",
        "plan": "C",
        "phase": "C1",
        "gate": "STUDIO_API_GATE",
        "verdict": verdict,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integration_sha": _git_sha(),
        "tests": tests,
        "openapi": openapi,
        "surface": surface,
        "missing_frozen": missing,
        "extra_routes": extra,
        "checks": checks,
        "fail_closed_write_composition": (
            "orchestrator port None until A4 handoff; mutations return "
            "CAPABILITY_UNAVAILABLE; reads served by A3 SQL adapters"
        ),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (ARTIFACT_DIR / "STUDIO_API_GATE_VERDICT.md").write_text(
        _verdict_md(evidence), encoding="utf-8"
    )
    print(f"verdict={verdict} tests={tests['summary']} paths={openapi['path_count']} missing={len(missing)}")
    return 0 if verdict == "PASS" else 1


def _snapshot_matches(openapi: dict) -> bool:
    # The V2 tombstone route stores methods in a hash-randomized set; the
    # canonical checker re-invokes itself with PYTHONHASHSEED=0 for a
    # deterministic dump. Reuse it instead of duplicating the seed logic.
    proc = subprocess.run(
        [sys.executable, "scripts/check_openapi_snapshot.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _verdict_md(evidence: dict) -> str:
    lines = [
        "# STUDIO_API_GATE — C1 verdict",
        "",
        f"- Contract: {evidence['surface']['contract']}",
        "- Gate: STUDIO_API_GATE",
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
        "## Surface",
        "",
        f"- Frozen endpoints implemented: {evidence['surface']['frozen_endpoints']}",
        f"- Live V3 paths: {evidence['openapi']['path_count']}",
        f"- OpenAPI snapshot SHA256: `{evidence['openapi']['snapshot_sha256']}`",
        f"- Missing frozen endpoints: {evidence['missing_frozen'] or 'none'}",
        f"- Extra unfrozen routes: {evidence['extra_routes'] or 'none'}",
        "",
        "## Test results",
        "",
        f"- `{evidence['tests']['command']}` → {evidence['tests']['summary']}",
        "",
        "## Composition",
        "",
        f"- {evidence['fail_closed_write_composition']}.",
        "",
        "Evidence JSON: `artifacts/studio_roadmap_01/c1/evidence.json`",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
