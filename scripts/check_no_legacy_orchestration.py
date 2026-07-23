"""
Static Checker: No Legacy Orchestration Imports.
Enforces that no codebase files import or instantiate deleted legacy orchestration modules.
Must return exit code 0 when zero legacy orchestration imports are found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

FORBIDDEN_PATTERNS = [
    re.compile(r"from\s+services\.dag_scheduler\s+import"),
    re.compile(r"from\s+services\.recovery_service\s+import"),
    re.compile(r"from\s+services\.hermes\.supervisor\s+import"),
    re.compile(r"from\s+services\.workflow_service\s+import"),
    re.compile(r"from\s+services\.workflow_runner\s+import"),
    re.compile(r"import\s+services\.dag_scheduler"),
    re.compile(r"import\s+services\.recovery_service"),
    re.compile(r"import\s+services\.hermes\.supervisor"),
    re.compile(r"import\s+services\.workflow_service"),
    re.compile(r"import\s+services\.workflow_runner"),
]

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", "artifacts", "reports", "audit_report"}


def check_legacy_imports(root_dir: Path) -> List[Tuple[Path, int, str]]:
    violations: List[Tuple[Path, int, str]] = []

    for file_path in root_dir.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in file_path.parts):
            continue
        if file_path.name == "check_no_legacy_orchestration.py":
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), start=1):
                for pattern in FORBIDDEN_PATTERNS:
                    if pattern.search(line):
                        violations.append((file_path, line_no, line.strip()))
        except Exception as err:
            print(f"Error reading {file_path}: {err}", file=sys.stderr)

    return violations


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    violations = check_legacy_imports(root_dir)

    if violations:
        print("FAIL: Legacy orchestration imports detected in codebase:")
        for path, line_no, line_content in violations:
            print(f"  {path}:{line_no} -> {line_content}")
        return 1

    print("PASS: Zero legacy orchestration imports found across codebase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
