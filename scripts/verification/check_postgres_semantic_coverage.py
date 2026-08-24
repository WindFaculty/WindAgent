#!/usr/bin/env python3
"""
Postgres Semantic Coverage Checker (T7).

Validates that the postgres semantic manifest is complete and that
every required capability has at least one collected test carrying
the `postgres` marker, and that `pytest -m postgres --collect-only`
returns non-zero.

Usage:
    python scripts/verification/check_postgres_semantic_coverage.py --root .
    python scripts/verification/check_postgres_semantic_coverage.py --root . --report artifacts/test-refactor/t7/postgres/semantic_manifest_report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, Any, List

REQUIRED_SEMANTICS = [
    "cas",
    "lease_fencing",
    "multi_worker_claim",
    "idempotency_concurrency",
    "outbox_atomicity",
    "transaction_isolation",
    "unique_constraint_race",
    "replica_coordination",
    "durable_route_lock",
    "migration_integrity",
    "postgres_vertical_slice",
]

def load_manifest(root: Path) -> Dict[str, Any]:
    manifest_path = root / "tests" / "manifests" / "postgres_semantics.yaml"
    if not manifest_path.exists():
        print(f"FAIL: manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)
    import yaml
    data = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    return data, manifest_path

def collect_postgres_nodeids(root: Path) -> List[str]:
    # Use uv run pytest -m postgres --collect-only -q
    cmd = ["uv", "run", "pytest", "-m", "postgres", "--collect-only", "-q"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    if result.returncode not in (0, 5):  # 5 is no tests collected? but we treat as fail
        print(f"FAIL: pytest -m postgres --collect-only failed: {result.stderr[:2000]}", file=sys.stderr)
        # still try to parse
    nodeids = [line.strip() for line in result.stdout.splitlines() if "::" in line]
    return nodeids, result

def has_postgres_marker(path: Path, nodeid_pattern: str) -> bool:
    # Check if file/class/test has @pytest.mark.postgres
    # nodeid_pattern may be "tests/.../test_file.py::Class::method" or "tests/.../test_file.py"
    # We need to verify that the file or the specific test has marker
    # Simplify: check file contains marker if pattern is file-level, else check specific class/method
    # For now, check file text contains marker and that the test definition is preceded by marker
    # We'll do simple: if file contains "@pytest.mark.postgres" or 'pytestmark = pytest.mark.postgres' then consider file has marker
    # For per-test, we check if the test function/class is decorated
    file_part = nodeid_pattern.split("::")[0]
    fp = Path(file_part)
    if not fp.exists():
        # try absolute
        fp = Path.cwd() / file_part
    if not fp.exists():
        return False
    text = fp.read_text(encoding='utf-8', errors='ignore')
    # If file has pytestmark postgres, then all tests in file are postgres
    if "pytestmark" in text and "postgres" in text:
        return True
    if "@pytest.mark.postgres" in text:
        # Need to check if the specific nodeid's test is marked
        # For simplicity, if file contains marker, assume at least one test in file is marked, but we need to ensure the specific nodeid is marked
        # We can check if the class or function for nodeid is preceded by marker
        parts = nodeid_pattern.split("::")
        if len(parts) == 1:
            # file-level, check if file contains marker
            return "@pytest.mark.postgres" in text or "pytestmark" in text
        elif len(parts) == 2:
            # file::test or file::class
            target = parts[1]
            # Find pattern: @pytest.mark.postgres before def test_target or class target
            pattern = re.compile(r"@pytest\.mark\.postgres[^\n]*\n[^\n]*\n?\s*(async )?def\s+"+re.escape(target)+r"|@pytest\.mark\.postgres[^\n]*\n[^\n]*class\s+"+re.escape(target), re.MULTILINE)
            if pattern.search(text):
                return True
            # Also check if class is marked and test is inside class (for file::class::test, we need to check class marker)
            # For len 3, check class marker
            return False
        elif len(parts) == 3:
            klass, func = parts[1], parts[2]
            # Check if class has marker or func has marker
            class_pattern = re.compile(r"@pytest\.mark\.postgres[^\n]*\n[^\n]*class\s+"+re.escape(klass), re.MULTILINE)
            func_pattern = re.compile(r"@pytest\.mark\.postgres[^\n]*\n[^\n]*\n?\s*(async )?def\s+"+re.escape(func), re.MULTILINE)
            if class_pattern.search(text) or func_pattern.search(text):
                return True
            # Also check if file has class-level marker via pytestmark inside class? Less common
            return False
    return False

def main() -> int:
    parser = argparse.ArgumentParser(description="Postgres semantic coverage checker")
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--report", help="Write JSON report to path")
    parser.add_argument("--manifest", default="tests/manifests/postgres_semantics.yaml", help="Manifest path relative to root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    data, manifest_path = load_manifest(root)

    report: Dict[str, Any] = {
        "root": str(root),
        "manifest": str(manifest_path),
        "required_semantics": REQUIRED_SEMANTICS,
        "manifest_keys": list(data.keys()) if isinstance(data, dict) else [],
        "missing_required": [],
        "extra_keys": [],
        "invalid_references": [],
        "marker_missing": [],
        "by_semantic": {},
        "collected_count": 0,
        "status": "PASS",
        "errors": [],
    }

    # Check required semantics present
    if not isinstance(data, dict):
        report["errors"].append("manifest is not a dict")
        report["status"] = "FAIL"
    else:
        for req in REQUIRED_SEMANTICS:
            if req not in data:
                report["missing_required"].append(req)
                report["status"] = "FAIL"
            else:
                val = data[req]
                if not isinstance(val, list) or not val:
                    report["errors"].append(f"semantic {req} must be non-empty list")
                    report["status"] = "FAIL"
                else:
                    # Validate each entry exists as file or nodeid
                    for entry in val:
                        # Entry may be file path or nodeid
                        # Check if file exists or nodeid file part exists
                        file_part = entry.split("::")[0]
                        fp = root / file_part
                        if not fp.exists():
                            report["invalid_references"].append(f"{req}: {entry} -> file not found")
                            report["status"] = "FAIL"
                        # Also check marker
                        if not has_postgres_marker(root / file_part if (root / file_part).exists() else Path(file_part), entry):
                            # For now, also check if any collected postgres nodeids contain this entry pattern
                            report["marker_missing"].append(f"{req}: {entry} missing @pytest.mark.postgres")
                            # Don't immediately fail; but we will fail if marker missing
        report["by_semantic"] = {k: len(v) if isinstance(v, list) else 0 for k, v in data.items()} if isinstance(data, dict) else {}

    # Collect postgres tests
    collected, proc = collect_postgres_nodeids(root)
    report["collected_count"] = len(collected)
    report["collected_sample"] = collected[:20]
    report["collect_stderr"] = proc.stderr[:2000] if proc else ""
    report["collect_returncode"] = proc.returncode if proc else -1

    if len(collected) == 0:
        report["errors"].append("pytest -m postgres --collect-only returned 0 tests")
        report["status"] = "FAIL"

    # Ensure each required semantic has at least one collected test that matches its manifest entries
    # For each semantic, check if any collected nodeid matches any manifest entry pattern (prefix match)
    for req in REQUIRED_SEMANTICS:
        if req not in data or not isinstance(data[req], list):
            continue
        manifest_entries = data[req]
        matched = False
        for entry in manifest_entries:
            # entry may be file path, check if any collected starts with entry or file part
            for nid in collected:
                if nid.startswith(entry) or nid == entry or entry in nid:
                    matched = True
                    break
                # Also allow file-level match: if entry is file path, collected under that file counts
                if entry.endswith(".py") and nid.startswith(entry):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            report["errors"].append(f"semantic {req} has no collected postgres test matching manifest")
            report["status"] = "FAIL"

    # Also ensure every manifest entry that is a nodeid actually exists as a collected test? Not strictly, but check if entry is nodeid and not in collected, it's still okay if marker missing? But we already flagged marker_missing
    # For now, also fail if marker_missing non-empty
    if report["marker_missing"]:
        report["errors"].append(f"{len(report['marker_missing'])} manifest entries missing postgres marker")
        report["status"] = "FAIL"
    if report["invalid_references"]:
        report["status"] = "FAIL"
    if report["missing_required"]:
        report["status"] = "FAIL"

    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"Report written to {out} ({report['status']})")

    if report["status"] == "PASS":
        print(f"PASS: postgres semantic coverage OK — {len(collected)} tests collected")
        for req in REQUIRED_SEMANTICS:
            print(f"  {req}: {data.get(req, [])[:1]}")
        return 0
    else:
        print("FAIL: postgres semantic coverage violations", file=sys.stderr)
        for err in report["errors"]:
            print(f"  - {err}", file=sys.stderr)
        if report["marker_missing"]:
            print(f"  marker_missing ({len(report['marker_missing'])}):", file=sys.stderr)
            for mm in report["marker_missing"][:10]:
                print(f"    {mm}", file=sys.stderr)
        if report["invalid_references"]:
            print("  invalid_references:", file=sys.stderr)
            for ir in report["invalid_references"][:10]:
                print(f"    {ir}", file=sys.stderr)
        if report["missing_required"]:
            print(f"  missing_required: {report['missing_required']}", file=sys.stderr)
        print(f"  collected: {len(collected)}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
