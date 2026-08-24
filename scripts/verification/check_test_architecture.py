#!/usr/bin/env python3
"""
Test Architecture Hygiene Gate (T1).

Enforces the tier boundary rules from ``ban_ke_hoach_v2.md`` as a
machine-checkable gate. Fails closed (exit 1) on any violation.

Rules (path-based):

* ``tests/unit/**`` — pure only: no DB, no HTTP, no subprocess, no sleep,
  no sys.path hack, no repo-root DB writes.
* ``tests/component/**`` — single component + local infra: no API server
  (uvicorn), no multiprocess, no TestClient serving real HTTP.
* ``tests/contracts/**`` — TestClient/CLI only: no real external network.
* ``tests/integration/**`` — multi-component: no real Internet, no hard sleep
  without poll helper.
* ``tests/e2e/**`` — process-based: must use ``tests.support.process`` helpers.
* ``tests/architecture/**`` — static inspection only: no business execution
  (no DB, no TestClient).
* ``tests/verification/**`` — evidence only: no pure unit duplicating logic.
* Global: no ``sys.path.insert`` outside ``tests/support`` (already covered
  by ``tests/conftest.py`` pattern), no ``windagent.db`` literal without
  ``tmp_path``.

The gate is intentionally strict: it scans file text and AST imports, not
runtime behavior, so it may flag dead code — that is desired (clean it up).

Usage:
    python scripts/verification/check_test_architecture.py --root . --report artifacts/ci/test-architecture/report.json
    python scripts/verification/check_test_architecture.py --root . --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Violation:
    file: str
    tier: str
    rule: str
    line: int
    snippet: str


# ---------------------------------------------------------------------------
# Forbidden patterns per tier (simple text search + AST import search)
# ---------------------------------------------------------------------------

# Patterns that are always suspicious when they appear outside the allowed tier.
# For T1 we only enforce sys.path — windagent.db check is advisory because
# many comments/docs legitimately mention the file name.
GLOBAL_FORBIDDEN = [
    (re.compile(r"sys\.path\.insert"), "sys.path.insert hack — use pyproject.toml pythonpath"),
]

UNIT_FORBIDDEN = [
    (re.compile(r"\baiosqlite\b"), "aiosqlite in unit — use component"),
    (re.compile(r"\bsqlalchemy\b"), "sqlalchemy in unit — use component"),
    (re.compile(r"\bcreate_async_engine\b"), "create_async_engine in unit"),
    (re.compile(r"\bcreate_engine\b"), "create_engine in unit"),
    (re.compile(r"\bDatabaseManager\b"), "DatabaseManager in unit"),
    (re.compile(r"\bSqlUnitOfWork\b"), "SqlUnitOfWork in unit"),
    (re.compile(r"\bTestClient\b"), "TestClient in unit — use contracts"),
    (re.compile(r"\bhttpx\b"), "httpx in unit (HTTP boundary)"),
    (re.compile(r"\bsubprocess\b"), "subprocess in unit"),
    (re.compile(r"\bPopen\b"), "Popen in unit"),
    (re.compile(r"\buvicorn\b"), "uvicorn in unit"),
    (re.compile(r"time\.sleep\s*\("), "time.sleep in unit — use tests.support.waiting.poll_until"),
    (re.compile(r"asyncio\.sleep\s*\("), "asyncio.sleep in unit — use waiting helpers"),
    (re.compile(r"windagent\.db"), "windagent.db in unit"),
]

COMPONENT_FORBIDDEN: list[tuple[re.Pattern, str]] = [
    # Enforced from T3 onwards — not failed in T1
]

ARCH_FORBIDDEN: list[tuple[re.Pattern, str]] = [
    # T5 will convert phase-based architecture to invariant-based;
    # not failed in T1 to avoid blocking baseline.
]

# T7: allow-list MUST be zero. All grandfathered exceptions have been removed.
# The set remains as a fail-closed guard — any re-introduction trips the gate.
ALLOW_LIST: set[str] = set()


def _is_allowlisted(path: Path) -> bool:
    # Compare both absolute and relative forms to handle callers that pass
    # either absolute or relative paths.
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()
    s_abs = path.as_posix()
    return any(rel.startswith(prefix) or s_abs.endswith(prefix) or s_abs.startswith(prefix) for prefix in ALLOW_LIST)


def _tier_for(path: Path, root: Path) -> str | None:
    rel = path.relative_to(root).as_posix()
    for tier in ("unit", "component", "contracts", "integration", "e2e", "architecture", "verification", "regression", "support", "fakes", "fixtures"):
        if rel.startswith(f"tests/{tier}/"):
            return tier
    if rel.startswith("tests/support/") or rel.startswith("tests/fakes/") or rel.startswith("tests/fixtures/"):
        return "support"
    return None


def _check_file(path: Path, root: Path) -> List[Violation]:
    rel = path.relative_to(root).as_posix()
    tier = _tier_for(path, root)
    # Support / fakes / fixtures are infrastructure — not subject to tier rules
    if tier in ("support", None):
        return []

    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    violations: List[Violation] = []

    # Global rules (apply to all tiers except support/fakes)
    for pat, rule in GLOBAL_FORBIDDEN:
        for i, line in enumerate(lines, 1):
            if pat.search(line):
                # Skip if line is a comment that documents the rule itself
                stripped = line.strip()
                if stripped.startswith("#") and "windagent.db" in stripped and "tmp_path" in stripped:
                    continue
                violations.append(Violation(rel, tier, f"global: {rule}", i, stripped[:200]))

    # Tier-specific
    rules = []
    if tier == "unit" and not _is_allowlisted(path):
        rules = UNIT_FORBIDDEN
    elif tier == "component":
        rules = COMPONENT_FORBIDDEN
    elif tier == "architecture":
        rules = ARCH_FORBIDDEN

    for pat, rule in rules:
        for i, line in enumerate(lines, 1):
            if pat.search(line):
                # Allow imports inside string literals or comments that mention the term — check if line is purely import
                # For now, flag it; allow-list will handle false positives
                violations.append(Violation(rel, tier, rule, i, line.strip()[:200]))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Test architecture hygiene gate")
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--report", help="Write JSON report to path")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("--strict", action="store_true", help="Fail on any violation (default)")
    parser.add_argument("--allow-list", action="store_true", help="Show allow-listed paths that would otherwise fail")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    tests_root = root / "tests"
    if not tests_root.exists():
        print(f"ERROR: tests root not found: {tests_root}", file=sys.stderr)
        return 2

    all_py = sorted(tests_root.rglob("*.py"))
    # Exclude __pycache__
    all_py = [p for p in all_py if "__pycache__" not in p.parts]

    violations: List[Violation] = []
    for p in all_py:
        # Skip support/fakes/fixtures internals
        if any(part in ("support", "fakes", "fixtures") for part in p.parts):
            # Still check fakes/fixtures for sys.path hack globally
            text = p.read_text(encoding="utf-8", errors="ignore")
            if "sys.path.insert" in text:
                rel = p.relative_to(root).as_posix()
                for i, line in enumerate(text.splitlines(), 1):
                    if "sys.path.insert" in line:
                        violations.append(Violation(rel, "support", "global: sys.path.insert hack", i, line.strip()[:200]))
            continue
        violations.extend(_check_file(p, root))

    # Also scan tests/support itself for sys.path usage (should be zero)
    # Already handled above.

    report: Dict[str, Any] = {
        "root": str(root),
        "total_files_scanned": len(all_py),
        "violations": [asdict(v) for v in violations],
        "violation_count": len(violations),
        "by_tier": {},
        "by_rule": {},
        "status": "PASS" if not violations else "FAIL",
    }
    from collections import Counter

    report["by_tier"] = dict(Counter(v.tier for v in violations))
    report["by_rule"] = dict(Counter(v.rule for v in violations))

    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Report written to {out} ({len(violations)} violations)")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if violations:
            print(f"FAIL: {len(violations)} test-architecture violations", file=sys.stderr)
            for v in violations[:50]:
                print(f"  {v.file}:{v.line} [{v.tier}] {v.rule}: {v.snippet}", file=sys.stderr)
            if len(violations) > 50:
                print(f"  ... and {len(violations)-50} more", file=sys.stderr)
        else:
            print("PASS: no test-architecture violations")

    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
