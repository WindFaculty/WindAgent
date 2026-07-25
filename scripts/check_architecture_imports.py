#!/usr/bin/env python3
"""Fail-closed Architecture V2 policy checker."""

import argparse
import ast
import json
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = DEFAULT_ROOT / "configs" / "architecture" / "scaffold_v2.yaml"
DEFAULT_REPORT = DEFAULT_ROOT / "artifacts" / "architecture_v2_completion" / "phase_16" / "dependency_boundary_report.json"
FORBIDDEN_CORE_IMPORTS = {"aiosqlite", "fastapi", "langgraph", "mcp", "sqlalchemy", "starlette"}
APP_PACKAGES = {"api", "cli", "worker"}


def normalize_dependency(value: str) -> str:
    value = value.split("[", 1)[0].split(";", 1)[0].strip().lower().replace("_", "-")
    for marker in (">", "<", "=", "!", "~"):
        value = value.split(marker, 1)[0]
    return value


def read_pyproject(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        return tomllib.load(stream)


def package_dependencies(path: Path) -> set[str]:
    project = read_pyproject(path / "pyproject.toml").get("project", {})
    return {normalize_dependency(item) for item in project.get("dependencies", [])}


def imports_and_classes(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = []
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, item.name) for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
        elif isinstance(node, ast.ClassDef):
            fields = sorted(
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
            )
            classes.append((node.lineno, node.name, fields))
    return imports, classes


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    found = []
    active = []
    done = set()

    def visit(node: str):
        if node in active:
            found.append(active[active.index(node):] + [node])
            return
        if node in done:
            return
        active.append(node)
        for child in graph.get(node, set()):
            visit(child)
        active.pop()
        done.add(node)

    for node in graph:
        visit(node)
    return found


def check(root: Path, config: dict) -> tuple[dict, dict]:
    packages = config.get("packages", {})
    rules = config.get("global_rules", {})
    canonical = set(config.get("canonical_models", []))
    namespaces = {info["namespace"]: name for name, info in packages.items()}
    violations = []
    graph = {name: set() for name in packages}
    edges = []
    versions = defaultdict(list)
    definitions = defaultdict(list)

    def add(rule: str, file: str, line: int, message: str):
        violations.append({"rule": rule, "file": file, "line": line, "message": message})

    for required in config.get("required_top_level_packages", []):
        if not (root / required).is_dir():
            add("missing_top_level_package", required, 1, f"Top-level package missing: {required}")

    configured_members = set(config.get("workspace", {}).get("members", []))
    root_project = read_pyproject(root / "pyproject.toml")
    actual_members = set(root_project.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", configured_members))
    expected_members = {info["path"] for info in packages.values()}
    for member in sorted(expected_members - actual_members):
        add("workspace_member_missing", "pyproject.toml", 1, f"Workspace member not declared: {member}")

    for name, info in packages.items():
        package_path = root / info["path"]
        namespace_path = package_path / info["namespace"]
        if not package_path.is_dir():
            add("missing_package", info["path"], 1, f"Package path missing: {info['path']}")
            continue
        if not namespace_path.is_dir():
            add("namespace_path_mismatch", info["path"], 1, f"Namespace path missing: {info['namespace']}")
            continue

        metadata = read_pyproject(package_path / "pyproject.toml").get("project", {})
        version = metadata.get("version")
        if version:
            versions[version].append(name)
        declared = package_dependencies(package_path)
        allowed = {item.removeprefix("windagent_").removeprefix("windagent-") for item in info.get("allowed_dependencies", [])}

        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            try:
                imports, classes = imports_and_classes(source)
            except SyntaxError as error:
                add("syntax_error", relative, error.lineno or 1, str(error))
                continue

            for line, class_name, fields in classes:
                if class_name in canonical:
                    definitions[class_name].append((relative, line, fields))

            for line, module in imports:
                root_module = module.split(".")[0]
                target = namespaces.get(root_module)
                if module.startswith("apps.backend") or module.startswith("backend"):
                    if rules.get("forbid_legacy_backend_imports", True):
                        add("legacy_backend_import", relative, line, f"Legacy backend import: {module}")
                if name == "core" and root_module in FORBIDDEN_CORE_IMPORTS and rules.get("forbid_core_framework_imports", True):
                    add("core_framework_import", relative, line, f"Core imports framework: {module}")
                if target is None or target == name:
                    continue
                graph[name].add(target)
                edges.append({"from": name, "to": target, "file": relative, "line": line})
                if name in APP_PACKAGES and target in APP_PACKAGES and rules.get("forbid_cross_app_imports", True):
                    add("cross_app_dependency", relative, line, f"Cross-app import: {name} imports {target}")
                if target not in allowed:
                    add("disallowed_dependency", relative, line, f"{name} cannot depend on {target}")
                expected = normalize_dependency(packages[target].get("distribution", packages[target]["namespace"]))
                if rules.get("require_declared_workspace_dependencies", True) and expected not in declared:
                    add("undeclared_workspace_dependency", relative, line, f"Missing declared dependency: {expected}")
                if rules.get("forbid_public_api_leakage", True) and any(part.startswith("_") for part in module.split(".")[1:]):
                    add("public_api_leakage", relative, line, f"Private module import: {module}")

    if rules.get("forbid_dependency_cycles", True):
        for cycle in cycles(graph):
            add("dependency_cycle", "workspace", 1, "Dependency cycle: " + " -> ".join(cycle))

    for model, locations in definitions.items():
        if len(locations) > 1:
            signatures = {tuple(item[2]) for item in locations}
            detail = ", ".join(f"{file}:{line}" for file, line, _ in locations)
            add("duplicate_canonical_model", detail, 1, f"Duplicate {model}; field signatures: {len(signatures)}")

    if len(versions) > 1:
        add("package_version_mismatch", "workspace", 1, f"Package versions differ: {sorted(versions)}")

    graph_report = {
        "nodes": [{"id": name, "path": info["path"], "namespace": info["namespace"]} for name, info in packages.items()],
        "edges": edges,
        "adjacency_list": {name: sorted(targets) for name, targets in graph.items()},
    }
    report = {
        "status": "PASS" if not violations else "FAIL",
        "total_violations": len(violations),
        "violations": violations,
        "circular_dependency_cycles": sum(item["rule"] == "dependency_cycle" for item in violations),
    }
    return report, graph_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--graph", type=Path)
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    report, graph = check(args.root.resolve(), config)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    graph_path = args.graph or args.report.with_name("import_graph.json")
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    print(f"Architecture policy: {report['status']} ({report['total_violations']} violations)")
    for item in report["violations"]:
        print(f"[{item['rule']}] {item['file']}:{item['line']} {item['message']}")
    if report["status"] == "PASS":
        print("Zero boundary violations detected")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())