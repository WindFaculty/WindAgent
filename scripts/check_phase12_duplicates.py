#!/usr/bin/env python3
"""
AST-based Duplicate Definition and Legacy Import Linter for Phase 12.
Verifies that:
- duplicate_canonical_models = 0
- duplicate_lifecycle_enums = 0
- duplicate_event_envelopes = 0
- duplicate_root_errors = 0
- internal_legacy_event_imports = 0
"""

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Allowed canonical files for definitions
CANONICAL_ENVELOPE_FILE = ROOT_DIR / "core" / "windagent_core" / "events" / "envelope.py"
CANONICAL_LIFECYCLE_FILE = ROOT_DIR / "core" / "windagent_core" / "domain" / "lifecycle.py"
CANONICAL_ERROR_FILE = ROOT_DIR / "core" / "windagent_core" / "errors" / "exceptions.py"
CANONICAL_PROVIDER_FILE = ROOT_DIR / "core" / "windagent_core" / "contracts" / "providers" / "requests.py"
CANONICAL_PROVIDER_FILES = {
    ROOT_DIR / "core" / "windagent_core" / "contracts" / "providers" / "requests.py",
    ROOT_DIR / "core" / "windagent_core" / "contracts" / "providers" / "responses.py",
    ROOT_DIR / "core" / "windagent_core" / "contracts" / "providers" / "usage.py",
}

EXCLUDED_DIR_NAMES = {".venv", ".git", ".pytest_cache", "artifacts", "docs", "node_modules", "logs", "__pycache__", "tests", "scripts"}
EXCLUDED_PATHS = {
    ROOT_DIR / "apps" / "api" / "windagent_api" / "routers" / "compatibility.py",
    ROOT_DIR / "apps" / "api" / "windagent_api" / "adapters" / "legacy_event_mappers.py",
}


def should_skip(path: Path, root: Path = ROOT_DIR) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    if any(part.startswith(".") and part not in {".", ".."} for part in parts):
        return True
    for part in parts:
        if part in EXCLUDED_DIR_NAMES:
            return True
    if path in EXCLUDED_PATHS:
        return True
    return False


class DuplicateVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.duplicate_envelopes = []
        self.duplicate_lifecycles = []
        self.duplicate_root_errors = []
        self.duplicate_provider_models = []
        self.legacy_imports = []

    def visit_ClassDef(self, node: ast.ClassDef):
        # 1. EventEnvelope duplicate
        if node.name == "EventEnvelope" and self.file_path != CANONICAL_ENVELOPE_FILE:
            self.duplicate_envelopes.append((node.lineno, node.name))

        # 2. Lifecycle enums duplicate
        if node.name in ("TaskState", "WorkflowState", "StepState", "SessionState") and self.file_path != CANONICAL_LIFECYCLE_FILE:
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "Enum" in bases or "str" in bases:
                self.duplicate_lifecycles.append((node.lineno, node.name))

        # 3. Root errors duplicate
        if node.name == "WindAgentError" and self.file_path != CANONICAL_ERROR_FILE:
            self.duplicate_root_errors.append((node.lineno, node.name))

        # 4. Provider models duplicate
        if node.name in ("ProviderRequest", "ProviderResponse", "ProviderUsage") and self.file_path not in CANONICAL_PROVIDER_FILES:
            self.duplicate_provider_models.append((node.lineno, node.name))

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if self.file_path in EXCLUDED_PATHS:
            self.generic_visit(node)
            return
        if node.module and ("legacy" in node.module or "mock" in node.module):
            if "event" in node.module:
                self.legacy_imports.append((node.lineno, node.module))
        self.generic_visit(node)


def main() -> int:
    duplicate_envelopes = 0
    duplicate_lifecycles = 0
    duplicate_root_errors = 0
    duplicate_models = 0
    legacy_imports = 0

    scanned = 0
    for py_file in ROOT_DIR.rglob("*.py"):
        if should_skip(py_file, ROOT_DIR):
            continue

        scanned += 1
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        visitor = DuplicateVisitor(py_file)
        visitor.visit(tree)

        if visitor.duplicate_envelopes:
            print(f"Duplicate EventEnvelope in: {py_file}")
        if visitor.duplicate_provider_models:
            print(f"Duplicate Provider models in: {py_file}")

        duplicate_envelopes += len(visitor.duplicate_envelopes)
        duplicate_lifecycles += len(visitor.duplicate_lifecycles)
        duplicate_root_errors += len(visitor.duplicate_root_errors)
        duplicate_models += len(visitor.duplicate_provider_models)
        legacy_imports += len(visitor.legacy_imports)

    print(f"Phase 12 AST Duplicate Scan Results across {scanned} Python files:")
    print(f"  duplicate_canonical_models = {duplicate_models}")
    print(f"  duplicate_lifecycle_enums = {duplicate_lifecycles}")
    print(f"  duplicate_event_envelopes = {duplicate_envelopes}")
    print(f"  duplicate_root_errors = {duplicate_root_errors}")
    print(f"  internal_legacy_event_imports = {legacy_imports}")

    total_issues = duplicate_models + duplicate_lifecycles + duplicate_envelopes + duplicate_root_errors + legacy_imports

    if total_issues == 0:
        print("[PASS] Phase 12 Gate Check: ZERO duplicate definitions & legacy imports found!")
        return 0
    else:
        print(f"[FAIL] Phase 12 Gate Check: Found {total_issues} duplicate/legacy items.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
