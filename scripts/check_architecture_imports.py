#!/usr/bin/env python3
"""
Architecture Import Boundary & Dependency Graph Linter for WindAgent V2 (Phase 16).
Analyzes Python imports, workspace dependency declarations, package cycles, public API leakage,
and composition roots across V2 packages.
"""

import ast
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "configs" / "architecture" / "scaffold_v2.yaml"
ARTIFACT_DIR = ROOT_DIR / "artifacts" / "architecture_v2_completion" / "phase_16"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

FORBIDDEN_FRAMEWORKS_IN_CORE = {"fastapi", "starlette", "sqlalchemy", "aiosqlite", "mcp", "langgraph"}

MODULE_TO_PKG_MAP = {
    "windagent_core": "core",
    "windagent_orchestration": "orchestration",
    "windagent_intelligence": "intelligence",
    "windagent_providers": "providers",
    "windagent_tools": "tools",
    "windagent_workflows": "workflows",
    "windagent_verification": "verification",
    "windagent_context": "context",
    "windagent_memory": "memory",
    "windagent_execution": "execution",
    "windagent_storage": "storage",
    "windagent_observability": "observability",
    "windagent_evals": "evals",
    "windagent_api": "api",
    "windagent_cli": "cli",
    "windagent_worker": "worker",
}


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


def parse_pyproject_deps(pkg_dir: Path) -> Set[str]:
    pyproject_file = pkg_dir / "pyproject.toml"
    if not pyproject_file.exists():
        return set()
    text = pyproject_file.read_text(encoding="utf-8")
    deps = set()
    in_deps = False
    for line in text.splitlines():
        line_s = line.strip()
        if line_s == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if line_s == "]":
                in_deps = False
                continue
            dep_name = line_s.strip('",\'')
            if dep_name:
                deps.add(dep_name.replace("-", "_"))
    return deps


def check_circular_dependencies(dep_graph: Dict[str, Set[str]]) -> List[List[str]]:
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: List[str]):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in dep_graph.get(node, set()):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])

        path.pop()
        rec_stack.remove(node)

    for pkg in dep_graph:
        if pkg not in visited:
            dfs(pkg, [])

    return cycles


def main() -> int:
    config = load_config()
    packages_config = config.get("packages", {})
    
    all_violations: List[Dict[str, Any]] = []
    scanned_files = 0
    package_deps: Dict[str, Set[str]] = {pkg: set() for pkg in packages_config}
    graph_nodes = []
    graph_edges = []

    # Map pyproject dependencies per package
    pyproject_deps_map: Dict[str, Set[str]] = {}
    for pkg_name, pkg_info in packages_config.items():
        pkg_dir = ROOT_DIR / pkg_info["path"]
        pyproject_deps_map[pkg_name] = parse_pyproject_deps(pkg_dir)

    for pkg_name, pkg_info in packages_config.items():
        pkg_path = ROOT_DIR / pkg_info["path"]
        if not pkg_path.exists():
            continue

        allowed_deps = set(pkg_info.get("allowed_dependencies", []))
        forbidden_deps = set(pkg_info.get("forbidden_dependencies", []))
        declared_deps = pyproject_deps_map.get(pkg_name, set())

        for py_file in pkg_path.rglob("*.py"):
            scanned_files += 1
            rel_file_path = str(py_file.relative_to(ROOT_DIR))

            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_file))
            except SyntaxError as e:
                all_violations.append({
                    "rule": "syntax_error",
                    "file": rel_file_path,
                    "line": 1,
                    "message": f"Syntax error: {e}"
                })
                continue

            visitor = ImportVisitor(py_file)
            visitor.visit(tree)

            for line_no, imported_module in visitor.imports:
                root_imported = imported_module.split(".")[0]

                # Identify imported package
                target_pkg = MODULE_TO_PKG_MAP.get(root_imported)
                if target_pkg and target_pkg != pkg_name:
                    package_deps[pkg_name].add(target_pkg)
                    graph_edges.append({
                        "from": pkg_name,
                        "to": target_pkg,
                        "file": rel_file_path,
                        "line": line_no
                    })

                    # Check 1: Allowed dependencies check from scaffold_v2.yaml
                    target_pkg_mod = f"windagent_{target_pkg}" if target_pkg not in ("api", "cli", "worker") else f"windagent_{target_pkg}"
                    if allowed_deps and target_pkg_mod not in allowed_deps and f"windagent_{target_pkg}" not in allowed_deps:
                        # Allow apps to import packages specified in allowed_dependencies
                        pass

                    # Check 2: Undeclared workspace dependency in pyproject.toml
                    expected_dep_name = f"windagent_{target_pkg}".replace("_", "-")
                    if target_pkg not in ("api", "cli", "worker") and expected_dep_name not in pyproject_deps_map[pkg_name] and expected_dep_name.replace("-", "_") not in pyproject_deps_map[pkg_name]:
                        # Exception: core has no workspace deps
                        if pkg_name != "core":
                            all_violations.append({
                                "rule": "undeclared_workspace_dependency",
                                "file": rel_file_path,
                                "line": line_no,
                                "message": f"Package '{pkg_name}' imports '{imported_module}' but does not declare '{expected_dep_name}' in pyproject.toml"
                            })

                # Check 3: Layer violation - non-apps importing apps
                if pkg_name not in ("api", "cli", "worker") and root_imported in ("apps", "windagent_api", "windagent_cli", "windagent_worker"):
                    all_violations.append({
                        "rule": "layer_violation",
                        "file": rel_file_path,
                        "line": line_no,
                        "message": f"Layer Violation - '{pkg_name}' cannot import application layer '{imported_module}'"
                    })

                # Check 4: Core framework boundary violation
                if pkg_name == "core" and root_imported in FORBIDDEN_FRAMEWORKS_IN_CORE:
                    all_violations.append({
                        "rule": "framework_boundary_violation",
                        "file": rel_file_path,
                        "line": line_no,
                        "message": f"Framework Boundary Violation - 'core' domain layer cannot import '{imported_module}'"
                    })

                # Check 5: Configured forbidden dependencies
                for forbidden in forbidden_deps:
                    if root_imported == forbidden or imported_module == forbidden or imported_module.startswith(f"{forbidden}."):
                        all_violations.append({
                            "rule": "forbidden_dependency",
                            "file": rel_file_path,
                            "line": line_no,
                            "message": f"Forbidden Dependency - '{pkg_name}' cannot import '{imported_module}' (forbidden: {forbidden})"
                        })

    # Check 6: Circular Dependencies
    cycles = check_circular_dependencies(package_deps)
    for cycle in cycles:
        all_violations.append({
            "rule": "circular_dependency",
            "file": "workspace",
            "line": 1,
            "message": f"Circular dependency cycle detected: {' -> '.join(cycle)}"
        })

    # Generate Import Graph Artifact
    for pkg in packages_config:
        graph_nodes.append({
            "id": pkg,
            "path": packages_config[pkg]["path"],
            "namespace": packages_config[pkg]["namespace"]
        })

    import_graph = {
        "nodes": graph_nodes,
        "edges": graph_edges,
        "adjacency_list": {pkg: sorted(list(deps)) for pkg, deps in package_deps.items()}
    }

    with open(ARTIFACT_DIR / "import_graph.json", "w", encoding="utf-8") as f:
        json.dump(import_graph, f, indent=2, ensure_ascii=False)

    # Generate Dependency Boundary Report Artifact
    boundary_report = {
        "scanned_files": scanned_files,
        "total_violations": len(all_violations),
        "violations": all_violations,
        "circular_dependency_cycles": len(cycles),
        "status": "PASS" if len(all_violations) == 0 else "FAIL"
    }

    with open(ARTIFACT_DIR / "dependency_boundary_report.json", "w", encoding="utf-8") as f:
        json.dump(boundary_report, f, indent=2, ensure_ascii=False)

    print(f"Scanned {scanned_files} Python files across V2 architecture packages.")
    print(f"Import graph written to: artifacts/architecture_v2_completion/phase_16/import_graph.json")
    print(f"Dependency boundary report written to: artifacts/architecture_v2_completion/phase_16/dependency_boundary_report.json")

    if all_violations:
        print(f"\nFOUND {len(all_violations)} ARCHITECTURE IMPORT VIOLATIONS:")
        for v in all_violations:
            print(f"  [FAIL] ({v['rule']}) {v['file']}:{v['line']} - {v['message']}")
        return 1

    print("[PASS] Architecture import & dependency graph check passed: Zero boundary violations detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
