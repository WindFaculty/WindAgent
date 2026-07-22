#!/usr/bin/env python3
"""
Architecture Import Boundary Linter for WindAgent V2.
Uses AST parsing to analyze Python imports across V2 packages and enforce dependency rules:
- `core` cannot import `apps` or web/ORM frameworks (fastapi, sqlalchemy, mcp, langgraph).
- Core/domain modules cannot import external infrastructure/apps.
- Lower/core layers cannot import upper application layers (apps/api, apps/cli, apps/worker).
"""

import ast
import sys
from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "configs" / "architecture" / "scaffold_v2.yaml"

FORBIDDEN_FRAMEWORKS_IN_CORE = {"fastapi", "starlette", "sqlalchemy", "aiosqlite", "mcp", "langgraph"}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config path {CONFIG_PATH} not found.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ImportVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.imports = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append((node.lineno, alias.name))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self.imports.append((node.lineno, node.module))
        self.generic_visit(node)


def check_file_imports(file_path: Path, pkg_name: str, pkg_info: dict) -> list[str]:
    violations = []
    forbidden_deps = set(pkg_info.get("forbidden_dependencies", []))
    
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as e:
        return [f"SYNTAX ERROR in {file_path}: {e}"]

    visitor = ImportVisitor(file_path)
    visitor.visit(tree)

    for line_no, imported_module in visitor.imports:
        root_imported = imported_module.split(".")[0]

        # Rule 1: No package outside apps can import apps
        if pkg_name not in ("api", "cli", "worker") and root_imported in ("apps", "windagent_api", "windagent_cli", "windagent_worker"):
            violations.append(
                f"{file_path}:{line_no}: Layer Violation - '{pkg_name}' cannot import application layer '{imported_module}'"
            )

        # Rule 2: core cannot import forbidden frameworks (FastAPI, SQLAlchemy, etc.)
        if pkg_name == "core" and root_imported in FORBIDDEN_FRAMEWORKS_IN_CORE:
            violations.append(
                f"{file_path}:{line_no}: Framework Boundary Violation - 'core' domain layer cannot import '{imported_module}'"
            )

        # Rule 3: Check explicitly forbidden dependencies from scaffold_v2.yaml
        for forbidden in forbidden_deps:
            if root_imported == forbidden or imported_module == forbidden or imported_module.startswith(f"{forbidden}."):
                violations.append(
                    f"{file_path}:{line_no}: Configured Boundary Violation - '{pkg_name}' cannot import '{imported_module}' (forbidden: {forbidden})"
                )

    return violations


def main() -> int:
    config = load_config()
    packages = config.get("packages", {})
    all_violations = []
    scanned_files = 0

    for pkg_name, pkg_info in packages.items():
        pkg_path = ROOT_DIR / pkg_info["path"]
        if not pkg_path.exists():
            continue

        for py_file in pkg_path.rglob("*.py"):
            scanned_files += 1
            file_violations = check_file_imports(py_file, pkg_name, pkg_info)
            all_violations.extend(file_violations)

    print(f"Scanned {scanned_files} Python files across V2 architecture packages.")
    
    if all_violations:
        print(f"\nFOUND {len(all_violations)} ARCHITECTURE IMPORT VIOLATIONS:")
        for v in all_violations:
            print(f"  [FAIL] {v}")
        return 1
    
    print("[PASS] Architecture import check passed: Zero boundary violations detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
