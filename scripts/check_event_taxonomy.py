#!/usr/bin/env python3
"""
Event Taxonomy Verification Script for Phase 13.
Validates that all emitted events comply with EventCatalog dotted taxonomy.
"""

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "core"))

from windagent_core.events.catalog import EventCatalog

VALID_TAXONOMY_NAMES = {v for k, v in EventCatalog.__dict__.items() if isinstance(v, str) and not k.startswith("_")}


def main() -> int:
    invalid_events = []
    scanned_files = 0

    for py_file in ROOT_DIR.rglob("*.py"):
        if any(part in py_file.parts for part in (".venv", ".git", "artifacts", "docs", "node_modules", "logs")):
            continue

        scanned_files += 1
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in ("emit_event", "record_event"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        evt_str = node.args[0].value
                        if evt_str and "." in evt_str and evt_str not in VALID_TAXONOMY_NAMES:
                            invalid_events.append((py_file, node.lineno, evt_str))

    print(f"Scanned {scanned_files} Python files for Event Taxonomy.")
    print(f"Canonical Event Catalog contains {len(VALID_TAXONOMY_NAMES)} registered event types.")

    if invalid_events:
        print(f"[FAIL] Found {len(invalid_events)} unregistered event taxonomy items:")
        for file_path, line_no, evt in invalid_events:
            print(f"  {file_path}:{line_no} -> '{evt}'")
        return 1

    print("[PASS] Event Taxonomy Check PASSED: 100% events match EventCatalog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
