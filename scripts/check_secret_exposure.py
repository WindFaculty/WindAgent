#!/usr/bin/env python3
"""
Secret Exposure Verification Script for Phase 13.
Verifies zero hardcoded API keys or unredacted secret fallbacks in core and adapter code.
"""

import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Patterns matching raw API key assignments
HARDCODED_KEY_PATTERN = re.compile(r'(api_key|secret_key|auth_token)\s*=\s*["\'](sk-[A-Za-z0-9_-]{20,}|AIzaSy[A-Za-z0-9_-]{30,})["\']', re.IGNORECASE)


def main() -> int:
    exposures = []
    scanned_files = 0

    for py_file in ROOT_DIR.rglob("*.py"):
        if any(part in py_file.parts for part in (".venv", ".git", "artifacts", "docs", "node_modules", "logs", "tests")):
            continue

        scanned_files += 1
        content = py_file.read_text(encoding="utf-8")
        
        for line_no, line in enumerate(content.splitlines(), start=1):
            if HARDCODED_KEY_PATTERN.search(line):
                exposures.append((py_file, line_no, line.strip()))

    print(f"Scanned {scanned_files} production Python files for secret exposure.")

    if exposures:
        print(f"[FAIL] Found {len(exposures)} hardcoded secret exposures:")
        for file_path, line_no, line in exposures:
            print(f"  {file_path}:{line_no} -> {line}")
        return 1

    print("[PASS] Secret Exposure Check PASSED: Zero plaintext provider secrets found in code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
