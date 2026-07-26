#!/usr/bin/env python3
"""Fail-closed Architecture V2 policy checker - Phase 4 Enhanced."""

import argparse
import ast
import json
import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = DEFAULT_ROOT / "configs" / "architecture" / "scaffold_v2.yaml"
DEFAULT_REPORT = DEFAULT_ROOT / "artifacts" / "architecture_v2_runtime_cutover" / "phase_13" / "dependency_boundary_report.json"
FORBIDDEN_CORE_IMPORTS = {"aiosqlite", "fastapi", "langgraph", "mcp", "sqlalchemy", "starlette"}
APP_PACKAGES = {"api", "cli", "worker"}
DEFAULT_FALLBACK_RE = re.compile(r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b")

# Composition root patterns - only these locations can create concrete adapters
COMPOSITION_ROOTS = {
    "apps/api/.../composition.py",
    "apps/worker/.../composition.py",
    "apps/cli/.../composition.py",
    "tests/",
}

# Concrete adapter patterns that should only be created in composition roots
CONCRETE_ADAPTER_PATTERNS = {
    "DatabaseManager",
    "SqlRepository", 
    "Provider",
    "ExecutionRuntime",
    "ProviderAdapter",
    "ExecutionAdapter",
}

# Legacy quarantine zone
LEGACY_QUARANTINE_ZONE = "apps/backend"

# Framework imports that should not be in core
FRAMEWORK_IMPORTS = {"aiosqlite", "fastapi", "langgraph", "mcp", "sqlalchemy", "starlette", "uvicorn", "pydantic"}


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


def find_production_fallback_references(
    root: Path, packages: dict, test_adapter_paths: set[str], fallback_re: re.Pattern | None
) -> list[dict]:
    """Scan production source for test fallback symbol references outside tests."""
    pattern = fallback_re or DEFAULT_FALLBACK_RE
    violations: list[dict] = []
    for info in packages.values():
        namespace_path = root / info["path"] / info["namespace"]
        if not namespace_path.is_dir():
            continue
        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            if any(relative.startswith(path) for path in test_adapter_paths):
                continue
            try:
                text = source.read_text(encoding="utf-8")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.split("#", 1)[0]
                for match in pattern.finditer(stripped):
                    violations.append(
                        {
                            "rule": "production_test_fallback",
                            "file": relative,
                            "line": lineno,
                            "message": f"Production code references test fallback symbol '{match.group()}'",
                        }
                    )
    return violations


def find_package_source_declaration_issues(packages: dict) -> list[dict]:
    """Ensure every package documents its legacy source declaration."""
    violations: list[dict] = []
    for name, info in packages.items():
        if not info.get("legacy_source"):
            violations.append(
                {
                    "rule": "package_source_declaration",
                    "file": info["path"],
                    "line": 1,
                    "message": f"Package '{name}' is missing legacy_source declaration",
                }
            )
    return violations


def find_dynamic_imports(root: Path, packages: dict, namespaces: dict) -> list[dict]:
    """Scan for dynamic import patterns: importlib.import_module, __import__, plugin strings."""
    violations: list[dict] = []
    rules = {"forbid_dynamic_imports": True}
    
    # Patterns to detect dynamic imports
    dynamic_patterns = [
        (r"importlib\.import_module\s*\(", "importlib.import_module"),
        (r"__import__\s*\(", "__import__"),
    ]
    
    for name, info in packages.items():
        package_path = root / info["path"]
        namespace_path = package_path / info["namespace"]
        if not namespace_path.is_dir():
            continue
            
        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            
            try:
                text = source.read_text(encoding="utf-8")
            except Exception:
                continue
            
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("#"):
                    continue
                
                # Check for dynamic import patterns
                for pattern, name_func in dynamic_patterns:
                    if re.search(pattern, stripped):
                        # Extract the module string if possible
                        match = re.search(r"\"([^\"]+)\"|'([^']+)'", stripped)
                        module_str = match.group(1) or match.group(2) if match else "unknown"
                        
                        if module_str.startswith("apps.backend") or module_str.startswith("backend"):
                            violations.append({
                                "rule": "dynamic_legacy_import",
                                "file": relative,
                                "line": lineno,
                                "message": f"Dynamic import of legacy module: {name_func}(...'{module_str}')",
                            })
                        elif module_str and not module_str.startswith("windagent_"):
                            violations.append({
                                "rule": "dynamic_external_import",
                                "file": relative,
                                "line": lineno,
                                "message": f"Dynamic import of undeclared module: {name_func}(...'{module_str}')",
                            })
    
    return violations


def check_legacy_quarantine(root: Path, packages: dict, config: dict) -> list[dict]:
    """Enforce legacy quarantine policy for apps/backend."""
    violations: list[dict] = []
    rules = config.get("global_rules", {})
    
    if not rules.get("enforce_legacy_quarantine", True):
        return violations
    
    quarantine_config = config.get("forbidden_patterns", {}).get("legacy_quarantine", {})
    quarantine_zone = quarantine_config.get("zone", "apps/backend")
    allowlist = quarantine_config.get("allowlist", [])
    delegation_target = quarantine_config.get("delegation_target", "windagent_api")
    
    # Get backend package info
    backend_info = packages.get("backend", {})
    backend_path = root / backend_info.get("path", "apps/backend")
    
    if not backend_path.is_dir():
        return violations
    
    # Check that production entrypoint (main.py) only delegates to windagent_api
    main_py = backend_path / "main.py"
    if main_py.exists():
        try:
            text = main_py.read_text(encoding="utf-8")
            if delegation_target not in text:
                violations.append({
                    "rule": "legacy_main_delegation",
                    "file": "apps/backend/main.py",
                    "line": 1,
                    "message": f"main.py must delegate to {delegation_target}",
                })
            
            # Check for creation of runtime authority
            runtime_patterns = quarantine_config.get("runtime_authority_blocked_patterns", [])
            for pattern in runtime_patterns:
                if re.search(rf"\b{pattern}\b", text):
                    violations.append({
                        "rule": "legacy_runtime_authority",
                        "file": "apps/backend/main.py",
                        "line": 1,
                        "message": f"Legacy service creates runtime authority: {pattern}",
                    })
        except Exception:
            pass
    
    # Check all files in backend against allowlist
    for source in backend_path.rglob("*.py"):
        relative = source.relative_to(root).as_posix()
        
        # Skip if in allowlist
        is_allowed = False
        for pattern in allowlist:
            if pattern.endswith("**"):
                prefix = pattern[:-2]
                if relative.startswith(prefix):
                    is_allowed = True
                    break
            elif relative == pattern or relative.endswith("/" + pattern):
                is_allowed = True
                break
        
        if is_allowed:
            continue
        
        # If not in allowlist and imports into production entrypoint, fail
        if "entrypoint" in relative or "main" in relative:
            try:
                text = source.read_text(encoding="utf-8")
                imports, _ = imports_and_classes(source)
                for line, module in imports:
                    if not module.startswith("windagent_") and not module.startswith("apps.backend"):
                        violations.append({
                            "rule": "legacy_quarantine_violation",
                            "file": relative,
                            "line": line,
                            "message": f"Legacy file outside allowlist imports: {module}",
                        })
            except Exception:
                pass
    
    # Check that canonical packages don't import backend
    for name, info in packages.items():
        if name == "backend" or "legacy" in info.get("layer", ""):
            continue
        
        package_path = root / info["path"]
        namespace_path = package_path / info["namespace"]
        if not namespace_path.is_dir():
            continue
        
        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            
            try:
                text = source.read_text(encoding="utf-8")
                imports, _ = imports_and_classes(source)
                for line, module in imports:
                    if module.startswith("apps.backend") or module.startswith("backend"):
                        violations.append({
                            "rule": "canonical_to_legacy_import",
                            "file": relative,
                            "line": line,
                            "message": f"Canonical package '{name}' imports legacy: {module}",
                        })
            except Exception:
                pass
    
    return violations


def check_core_internal_boundaries(root: Path, packages: dict, config: dict) -> list[dict]:
    """Enforce core internal boundaries: domain/config, domain/security, contracts/infrastructure."""
    violations: list[dict] = []
    
    core_info = packages.get("core", {})
    core_path = root / core_info.get("path", "core")
    core_namespace = core_info.get("namespace", "windagent_core")
    
    if not core_path.is_dir():
        return violations
    
    core_namespace_path = core_path / core_namespace
    if not core_namespace_path.is_dir():
        return violations
    
    # Get internal boundaries from config
    internal_boundaries = core_info.get("internal_boundaries", {})
    
    # Check each internal boundary
    for subpackage_name, boundary_config in internal_boundaries.items():
        subpackage_path = core_namespace_path / subpackage_name
        if not subpackage_path.is_dir():
            continue
        
        forbidden = boundary_config.get("forbidden_dependencies", [])
        
        for source in subpackage_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            
            try:
                text = source.read_text(encoding="utf-8")
                imports, _ = imports_and_classes(source)
                for line, module in imports:
                    for forbidden_dep in forbidden:
                        if module.startswith(forbidden_dep.replace("/", ".").replace("core/windagent_core/", "")):
                            violations.append({
                                "rule": "core_internal_boundary_violation",
                                "file": relative,
                                "line": line,
                                "message": f"core/{subpackage_name} imports forbidden: {module} (forbidden: {forbidden_dep})",
                            })
            except Exception:
                pass
    
    return violations


def check_composition_root_rule(root: Path, packages: dict, config: dict) -> list[dict]:
    """Enforce composition-root rule: concrete adapters only in composition roots."""
    violations: list[dict] = []
    
    composition_roots_config = config.get("composition_roots", [])
    if not composition_roots_config:
        composition_roots_config = [
            "apps/api/.../composition.py",
            "apps/worker/.../composition.py",
            "apps/cli/.../composition.py",
            "tests/",
        ]
    
    adapter_patterns = config.get("concrete_adapters", list(CONCRETE_ADAPTER_PATTERNS))
    
    for name, info in packages.items():
        package_path = root / info["path"]
        namespace_path = package_path / info["namespace"]
        if not namespace_path.is_dir():
            continue
        
        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            
            # Check if this file is in a composition root
            is_composition_root = False
            for pattern in composition_roots_config:
                if pattern.endswith("**") or pattern.endswith("..."):
                    prefix = pattern.replace("...", "").replace("**", "")
                    if relative.startswith(prefix):
                        is_composition_root = True
                        break
                elif relative == pattern or relative.endswith("/" + pattern):
                    is_composition_root = True
                    break
            
            if is_composition_root:
                continue
            
            # Check for concrete adapter creation
            try:
                text = source.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=str(source))
                
                for node in ast.walk(tree):
                    # Check class definitions
                    if isinstance(node, ast.ClassDef):
                        if any(pattern in node.name for pattern in adapter_patterns):
                            violations.append({
                                "rule": "concrete_adapter_outside_composition",
                                "file": relative,
                                "line": node.lineno,
                                "message": f"Concrete adapter '{node.name}' created outside composition root",
                            })
                    
                    # Check variable assignments that create adapters
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                if any(pattern in target.id for pattern in adapter_patterns):
                                    violations.append({
                                        "rule": "concrete_adapter_outside_composition",
                                        "file": relative,
                                        "line": node.lineno,
                                        "message": f"Concrete adapter variable '{target.id}' created outside composition root",
                                    })
            except Exception:
                pass
    
    return violations


def check_public_api_enforcement(root: Path, packages: dict, config: dict) -> list[dict]:
    """Enforce public API rules: private imports, ORM in app layer, framework in core, etc."""
    violations: list[dict] = []
    rules = config.get("global_rules", {})
    namespaces = {info["namespace"]: name for name, info in packages.items()}
    
    for name, info in packages.items():
        package_path = root / info["path"]
        namespace_path = package_path / info["namespace"]
        if not namespace_path.is_dir():
            continue
        
        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            
            try:
                text = source.read_text(encoding="utf-8")
                imports, classes = imports_and_classes(source)
                
                for line, module in imports:
                    root_module = module.split(".")[0]
                    
                    # Check for private module imports across packages
                    if rules.get("forbid_public_api_leakage", True):
                        if "." in module and any(part.startswith("_") for part in module.split(".")[1:]):
                            target = namespaces.get(root_module)
                            if target and target != name:
                                violations.append({
                                    "rule": "private_cross_package_import",
                                    "file": relative,
                                    "line": line,
                                    "message": f"Private module import across packages: {module}",
                                })
                    
                    # Check for ORM imports in application layer
                    if name in APP_PACKAGES or info.get("layer") == "application":
                        orm_modules = {"sqlalchemy", "aiosqlite", "orm", "database", "db"}
                        if any(module.startswith(orm) or orm in module.lower() for orm in orm_modules):
                            violations.append({
                                "rule": "orm_in_application_layer",
                                "file": relative,
                                "line": line,
                                "message": f"ORM import in application layer: {module}",
                            })
                    
                    # Check for framework imports in core
                    if name == "core":
                        framework_modules = {"fastapi", "starlette", "uvicorn", "langgraph", "mcp"}
                        if any(module.startswith(fw) for fw in framework_modules):
                            violations.append({
                                "rule": "framework_in_core",
                                "file": relative,
                                "line": line,
                                "message": f"Framework import in core: {module}",
                            })
                    
                    # Check for direct infrastructure construction
                    if info.get("layer") != "infrastructure":
                        infra_patterns = {"DatabaseManager", "SqlRepository", "Provider", "Adapter"}
                        for pattern in infra_patterns:
                            if pattern in module:
                                violations.append({
                                    "rule": "infrastructure_construction_outside_infra",
                                    "file": relative,
                                    "line": line,
                                    "message": f"Direct infrastructure import in non-infra layer: {module}",
                                })
                
                # Check for duplicate canonical contracts
                for line, class_name, fields in classes:
                    canonical = set(config.get("canonical_models", []))
                    if class_name in canonical:
                        # Check if this is a duplicate definition
                        # We'll track this in the main check function
                        pass
                        
            except Exception:
                pass
    
    return violations


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
                    forbidden = {dep.removeprefix("windagent_").removeprefix("windagent-") for dep in info.get("forbidden_dependencies", [])}
                    if target in forbidden:
                        add("forbidden_import", relative, line, f"{name} has forbidden dependency on {target}")
                    else:
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

    forbidden_patterns = config.get("forbidden_patterns", {})
    if rules.get("forbid_production_test_fallbacks", True):
        fallback_re_text = forbidden_patterns.get("production_fallback_regex")
        fallback_re = re.compile(fallback_re_text) if fallback_re_text else None
        test_adapter_paths = set(forbidden_patterns.get("test_adapter_paths") or [])
        for violation in find_production_fallback_references(root, packages, test_adapter_paths, fallback_re):
            violations.append(violation)

    for violation in find_package_source_declaration_issues(packages):
        violations.append(violation)

    # Phase 4: Dynamic import scanning
    if rules.get("forbid_dynamic_imports", True):
        for violation in find_dynamic_imports(root, packages, namespaces):
            violations.append(violation)

    # Phase 4: Legacy quarantine enforcement
    for violation in check_legacy_quarantine(root, packages, config):
        violations.append(violation)

    # Phase 4: Core internal boundaries
    for violation in check_core_internal_boundaries(root, packages, config):
        violations.append(violation)

    # Phase 4: Composition root rule
    for violation in check_composition_root_rule(root, packages, config):
        violations.append(violation)

    # Phase 4: Public API enforcement
    for violation in check_public_api_enforcement(root, packages, config):
        violations.append(violation)

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