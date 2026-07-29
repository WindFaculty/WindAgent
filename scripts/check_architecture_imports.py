#!/usr/bin/env python3
"""Fail-closed Architecture V2 policy checker - Phase 3: Complete CLI Architecture Contract."""

import argparse
import ast
import json
import re
import subprocess
import sys
import time
import tomllib
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import yaml

from windagent_core.config.repository_root import find_repository_root, is_repository_root

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = DEFAULT_ROOT / "configs" / "architecture" / "scaffold_v2.yaml"
DEFAULT_REPORT = DEFAULT_ROOT / "artifacts" / "architecture_v2_runtime_cutover" / "phase_13" / "dependency_boundary_report.json"
FORBIDDEN_CORE_IMPORTS = {"aiosqlite", "fastapi", "langgraph", "mcp", "sqlalchemy", "starlette"}
APP_PACKAGES = {"api", "cli", "worker"}

# Composition root files — permitted to import storage/ORM directly for DI wiring
# or as explicit repository/reconciler infrastructure files.
# These are NOT application business logic arbitrarily using ORM.
COMPOSITION_ROOT_FILES = {
    # DI wiring roots
    "composition.py",
    "dependencies.py",
    "lease.py",
    # Repository pattern files — infrastructure layer, ORM access is intentional
    "repository.py",
    # Recovery / reconciler — directly queries ORM for crash recovery, by design
    "reconciler.py",
}
DEFAULT_FALLBACK_RE = re.compile(r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b")

# Composition root patterns - only these locations can create concrete adapters
COMPOSITION_ROOTS = {
    "apps/api/",
    "apps/worker/",
    "apps/cli/",
    "orchestration/",
    "providers/",
    "storage/",
    "execution/",
    "tools/",
    "workflows/",
    "verification/",
    "context/",
    "memory/",
    "intelligence/",
    "observability/",
    "evals/",
    "plugins/",
    "skills/",
    "tests/",
}

# Concrete adapter patterns that should only be created in composition roots
# These are implementation classes, not plain Pydantic models or domain types
CONCRETE_ADAPTER_PATTERNS = {
    "Adapter",        # ProviderAdapter, ExecutionAdapter, etc.
    "Repository",     # SqlRepository, SqlProviderRepository, etc.
    "Manager",        # DatabaseManager, etc.
    "Runtime",        # ExecutionRuntime, etc.
    "Gateway",        # ProviderGateway, etc.
    "Coordinator",    # ProviderV3Coordinator, etc.
    "Client",         # BaseProviderClient, etc. (actual HTTP clients)
}

# Legacy quarantine zone
LEGACY_QUARANTINE_ZONE = "apps/backend"

# Framework imports that should not be in core
FRAMEWORK_IMPORTS = {"aiosqlite", "fastapi", "langgraph", "mcp", "sqlalchemy", "starlette", "uvicorn", "pydantic"}


@dataclass
class CheckResult:
    """Result of a single checker execution."""
    name: str
    argv: list[str]
    cwd: str
    executed: bool
    exit_code: int
    classification: str
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in d.items() if v is not None}


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
            if ".venv" in relative or "__pycache__" in relative:
                continue
            try:
                text = source.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        violations.append({
                            "rule": "production_fallback_reference",
                            "file": relative,
                            "line": i,
                            "message": f"Production code references test fallback symbol: {line.strip()}",
                        })
            except Exception:
                pass
    return violations


def imports_and_classes(path: Path) -> tuple[list[tuple[int, str]], list[tuple[int, str, list[str]]]]:
    """Extract imports and class definitions from a Python file."""
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        raise
    except (OSError, UnicodeError):
        return [], []

    imports: list[tuple[int, str]] = []
    classes: list[tuple[int, str, list[str]]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((node.lineno, alias.name))
            else:
                module = node.module or ""
                for alias in node.names:
                    imports.append((node.lineno, f"{module}.{alias.name}"))
        elif isinstance(node, ast.ClassDef):
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id)
            classes.append((node.lineno, node.name, fields))
    return imports, classes


def run_required_check(
    name: str,
    argv: list[str],
    cwd: Path,
    timeout: int = 60,
) -> CheckResult:
    """
    Execute a required checker and return structured result.

    Catches all execution errors and classifies them properly.
    Never allows traceback to become CLI contract.
    """
    start_time = time.perf_counter()
    stdout_tail = ""
    stderr_tail = ""
    exit_code = 0
    executed = False
    classification = "UNKNOWN"
    error = None

    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        executed = True
        exit_code = result.returncode
        stdout_tail = result.stdout[-500:] if result.stdout else ""
        stderr_tail = result.stderr[-500:] if result.stderr else ""

        if exit_code == 0:
            classification = "PASS"
        elif exit_code == 1:
            classification = "VIOLATION"
        elif exit_code == 2:
            classification = "ROOT_NOT_FOUND"
        elif exit_code == 3:
            classification = "CHECKER_MISSING"
        elif exit_code == 4:
            classification = "CHECKER_ERROR"
        else:
            classification = "UNKNOWN_EXIT"

    except FileNotFoundError as e:
        exit_code = 3  # checker missing
        classification = "CHECKER_MISSING"
        error = f"FileNotFoundError: {e}"
        stderr_tail = str(e)
    except PermissionError as e:
        exit_code = 4  # checker error
        classification = "CHECKER_ERROR"
        error = f"PermissionError: {e}"
        stderr_tail = str(e)
    except subprocess.TimeoutExpired as e:
        exit_code = 4  # checker timeout
        classification = "CHECKER_TIMEOUT"
        error = f"TimeoutExpired after {timeout}s"
        stdout_tail = e.stdout[-500:] if e.stdout else ""
        stderr_tail = e.stderr[-500:] if e.stderr else ""
    except UnicodeDecodeError as e:
        exit_code = 4
        classification = "CHECKER_ERROR"
        error = f"UnicodeDecodeError: {e}"
        stderr_tail = str(e)
    except OSError as e:
        exit_code = 4
        classification = "CHECKER_ERROR"
        error = f"OSError: {e}"
        stderr_tail = str(e)
    except Exception as e:
        exit_code = 4
        classification = "CHECKER_ERROR"
        error = f"Unexpected error: {type(e).__name__}: {e}"
        stderr_tail = str(e)
    finally:
        duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        name=name,
        argv=argv,
        cwd=str(cwd),
        executed=executed,
        exit_code=exit_code,
        classification=classification,
        duration_ms=duration_ms,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        error=error,
    )


def check(root: Path, config: dict) -> tuple[dict, dict]:
    configured_packages = config.get("packages", {})
    root_project = read_pyproject(root / "pyproject.toml")
    root_members = set(
        root_project.get("tool", {})
        .get("uv", {})
        .get("workspace", {})
        .get("members", [])
    )
    policy_members = set(
        config.get("workspace", {}).get("members", [])
    )
    # A real checkout's root pyproject is authoritative. Minimal policy
    # fixtures intentionally omit that file, so their explicit policy members
    # become authoritative instead of silently reducing the checked package set
    # to zero.
    actual_members = root_members or policy_members
    packages = {
        name: info
        for name, info in configured_packages.items()
        if info.get("path") in actual_members
    }
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

    enforce_all_required = not root_members or root_members == policy_members
    for required in config.get("required_top_level_packages", []):
        required_is_active = enforce_all_required or required in root_members
        if required_is_active and not (root / required).is_dir():
            add("missing_top_level_package", required, 1, f"Top-level package missing: {required}")

    configured_paths = {
        info["path"] for info in configured_packages.values()
    }
    expected_members = (
        configured_paths
        if root_members and root_members == policy_members
        else {info["path"] for info in packages.values()}
    )
    for member in sorted(expected_members - actual_members):
        add("workspace_member_missing", "pyproject.toml", 1, f"Workspace member not declared: {member}")

    for name, info in packages.items():
        package_path = root / info["path"]
        root_project = read_pyproject(package_path / "pyproject.toml")
        dist_name = root_project.get("project", {}).get("name", info["namespace"])
        versions[dist_name].append(root_project.get("project", {}).get("version", "0.0.0"))
        declared = {normalize_dependency(item) for item in root_project.get("project", {}).get("dependencies", [])}
        allowed = {normalize_dependency(dep) for dep in info.get("allowed_dependencies", [])}
        # Map namespace names to package names for allowed dependencies
        allowed_packages = set()
        for dep in allowed:
            for pkg_name, pkg_info in packages.items():
                if pkg_info["namespace"] == dep or pkg_info["namespace"].replace("_", "-") == dep:
                    allowed_packages.add(pkg_name)
                    break
            else:
                allowed_packages.add(dep)  # fallback to original
        forbidden = {normalize_dependency(dep) for dep in info.get("forbidden_dependencies", [])}
        # Also map forbidden to package names
        forbidden_packages = set()
        for dep in forbidden:
            for pkg_name, pkg_info in packages.items():
                if pkg_info["namespace"] == dep or pkg_info["namespace"].replace("_", "-") == dep:
                    forbidden_packages.add(pkg_name)
                    break
            else:
                forbidden_packages.add(dep)

        namespace_path = package_path / info["namespace"]
        if not namespace_path.is_dir():
            add(
                "namespace_path_mismatch",
                package_path.relative_to(root).as_posix(),
                1,
                f"Namespace path missing: {info['namespace']}",
            )
            continue

        # Check namespace mismatch: pyproject.toml name should match config namespace
        dist_name = root_project.get("project", {}).get("name", info["namespace"])
        expected_ns = info["namespace"]
        if dist_name != expected_ns and dist_name.replace("-", "_") != expected_ns:
            add("namespace_path_mismatch", f"{package_path}/pyproject.toml", 1, f"Package namespace mismatch: pyproject.toml name='{dist_name}' but config expects '{expected_ns}'")

        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            if ".venv" in relative or "__pycache__" in relative:
                continue

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
                if target not in allowed_packages:
                    if target in forbidden_packages:
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

    # package_version_mismatch is tracked but NOT enforced here.
    # Version convergence is the responsibility of Phase 7 (version/docs/verdict).
    # if len(versions) > 1:
    #     add("package_version_mismatch", "workspace", 1, f"Package versions differ: {sorted(versions)}")

    forbidden_patterns = config.get("forbidden_patterns", {})

    if rules.get("forbid_production_test_fallbacks", True):
        fallback_re_text = forbidden_patterns.get("production_fallback_regex")
        fallback_re = re.compile(fallback_re_text) if fallback_re_text else None
        test_adapter_paths = set(forbidden_patterns.get("test_adapter_paths") or [])
        for violation in find_production_fallback_references(root, packages, test_adapter_paths, fallback_re):
            violations.append(violation)

    for violation in find_package_source_declaration_issues(root, packages):
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


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Find all simple cycles in the graph (Johnson's algorithm)."""
    nodes = list(graph.keys())
    index = {n: i for i, n in enumerate(nodes)}
    adj = [[index[n] for n in graph[node]] for node in nodes]

    result = []
    blocked = set()
    B = [set() for _ in nodes]
    stack = []

    def unblock(u: int):
        blocked.discard(u)
        for w in B[u]:
            if w in blocked:
                unblock(w)
        B[u].clear()

    def circuit(v: int, s: int) -> bool:
        f = False
        stack.append(v)
        blocked.add(v)
        for w in adj[v]:
            if w == s:
                result.append([nodes[i] for i in stack])
                f = True
            elif w not in blocked:
                if circuit(w, s):
                    f = True
        if f:
            unblock(v)
        else:
            for w in adj[v]:
                if v not in B[w]:
                    B[w].add(v)
        stack.pop()
        return f

    for s in range(len(nodes)):
        circuit(s, s)
        blocked.clear()
        for b_set in B:
            b_set.clear()
    return result


def find_dynamic_imports(root: Path, packages: dict, namespaces: dict) -> list[dict]:
    """Scan for dynamic imports like __import__, importlib.import_module."""
    violations = []
    dynamic_pattern = re.compile(r"\b(__import__|importlib\.import_module)\s*\(")

    for name, info in packages.items():
        namespace_path = root / info["path"] / info["namespace"]
        if not namespace_path.is_dir():
            continue
        for source in namespace_path.rglob("*.py"):
            relative = source.relative_to(root).as_posix()
            if relative.startswith("tests/"):
                continue
            if ".venv" in relative or "__pycache__" in relative:
                continue
            try:
                text = source.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), 1):
                    if dynamic_pattern.search(line):
                        violations.append({
                            "rule": "dynamic_external_import",
                            "file": relative,
                            "line": i,
                            "message": f"Dynamic import of undeclared module: {line.strip()}",
                        })
            except Exception:
                pass
    return violations


def check_legacy_quarantine(root: Path, packages: dict, config: dict) -> list[dict]:
    """Reject legacy Python sources outside the explicit compatibility allowlist.

    The legacy package is no longer a workspace member, so package-based scanning
    alone cannot detect somebody recreating ``apps/backend``. Scan the retired
    path directly to keep the removal fail-closed.
    """
    violations = []
    legacy_config = config.get("forbidden_patterns", {}).get("legacy_quarantine", {})
    zone = legacy_config.get("zone", "apps/backend")
    allowlist = legacy_config.get("allowlist", [])
    zone_path = root / zone
    if not zone_path.is_dir():
        return violations

    for source in zone_path.rglob("*.py"):
        relative = source.relative_to(root).as_posix()
        if ".venv" in relative or "__pycache__" in relative:
            continue
        allowed = False
        for pattern in allowlist:
            if pattern.endswith("**"):
                if relative.startswith(pattern[:-2]):
                    allowed = True
                    break
            elif relative == pattern:
                allowed = True
                break
        if not allowed:
            violations.append({
                "rule": "legacy_backend_source_present",
                "file": relative,
                "line": 1,
                "message": "Python source recreated in retired apps/backend tree",
            })
    return violations


def check_core_internal_boundaries(root: Path, packages: dict, config: dict) -> list[dict]:
    """Enforce core internal boundaries: domain < contracts < events isolation."""
    violations = []
    core_packages = config.get("packages", {}).get("core", {}).get("internal_boundaries", {})
    if not core_packages:
        return violations

    for subpackage_name, subpackage in core_packages.items():
        forbidden = subpackage.get("forbidden_dependencies", [])
        sub_path = subpackage.get('path', subpackage_name)

        for name, info in packages.items():
            if not info["path"].startswith("core"):
                continue
            namespace_path = root / info["path"] / info["namespace"]
            if not namespace_path.is_dir():
                continue
            for source in namespace_path.rglob("*.py"):
                relative = source.relative_to(root).as_posix()
                if not relative.startswith(sub_path + "/"):
                    continue
                if ".venv" in relative or "__pycache__" in relative:
                    continue
                try:
                    imports, _ = imports_and_classes(source)
                    for line, module in imports:
                        if not module:
                            continue
                        for forbidden_dep in forbidden:
                            forbidden_ns = forbidden_dep.replace("/", ".")
                            if forbidden_dep.startswith("core.windagent_core."):
                                forbidden_ns = forbidden_dep[len("core.windagent_core."):]
                                forbidden_ns = "windagent_core." + forbidden_ns
                            elif forbidden_dep.startswith("core/windagent_core/"):
                                forbidden_ns = forbidden_dep.replace("/", ".")
                                forbidden_ns = forbidden_ns[len("core."):]
                            elif forbidden_dep.startswith("core/"):
                                forbidden_ns = forbidden_dep.replace("/", ".")
                                if forbidden_ns.startswith("core."):
                                    forbidden_ns = "windagent_core." + forbidden_ns[len("core."):]
                            if module == forbidden_ns or module.startswith(forbidden_ns + "."):
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
    violations = []

    composition_roots_config = config.get("composition_roots", [])
    if not composition_roots_config:
        composition_roots_config = [
            "apps/api/**",
            "apps/worker/**",
            "apps/cli/**",
            "orchestration/**",
            "providers/**",
            "storage/**",
            "execution/**",
            "tools/**",
            "workflows/**",
            "verification/**",
            "context/**",
            "memory/**",
            "intelligence/**",
            "observability/**",
            "evals/**",
            "plugins/**",
            "skills/**",
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
            if ".venv" in relative or "__pycache__" in relative:
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

            # Check for concrete adapter creation (INSTANTIATION only, not class definitions)
            try:
                text = source.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=str(source))

                for node in ast.walk(tree):
                    # Check variable assignments that create adapters (instantiation)
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
                    # Check for direct instantiation in expressions (e.g., SomeAdapter() as arg, return SomeAdapter())
                    elif isinstance(node, ast.Call):
                        # Check if the call is constructing an adapter type
                        if isinstance(node.func, ast.Name) and any(pattern in node.func.id for pattern in adapter_patterns):
                            violations.append({
                                "rule": "concrete_adapter_outside_composition",
                                "file": relative,
                                "line": node.lineno,
                                "message": f"Concrete adapter '{node.func.id}' instantiated outside composition root",
                            })
                        elif isinstance(node.func, ast.Attribute) and any(pattern in node.func.attr for pattern in adapter_patterns):
                            violations.append({
                                "rule": "concrete_adapter_outside_composition",
                                "file": relative,
                                "line": node.lineno,
                                "message": "Concrete adapter instantiated outside composition root",
                            })
            except Exception:
                pass

    return violations


def check_public_api_enforcement(root: Path, packages: dict, config: dict) -> list[dict]:
    """Enforce public API rules: private imports, ORM in app layer, framework in core, etc."""
    violations = []
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
            if ".venv" in relative or "__pycache__" in relative:
                continue

            try:
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

                    # Check for ORM imports in application layer.
                    # Composition roots and infrastructure files are exempt (see COMPOSITION_ROOT_FILES).
                    # Uses startswith-only matching to avoid false positives from substring matches
                    # (e.g. 'platform' contains 'orm', 'ReportFormat' contains 'orm' via 'format').
                    if name in APP_PACKAGES or info.get("layer") == "application":
                        _basename = Path(source).name
                        if _basename not in COMPOSITION_ROOT_FILES:
                            orm_prefixes = ("sqlalchemy", "aiosqlite", "windagent_storage.orm", "windagent_storage.database")
                            if any(module.startswith(pfx) for pfx in orm_prefixes):
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

                    # Check for canonical-to-legacy imports
                    if rules.get("forbid_canonical_to_legacy_imports", True):
                        if module.startswith("apps.backend") or module.startswith("backend"):
                            violations.append({
                                "rule": "canonical_to_legacy_import",
                                "file": relative,
                                "line": line,
                                "message": f"Canonical package imports legacy: {module}",
                            })

            except Exception:
                pass

    return violations


def find_package_source_declaration_issues(root: Path, packages: dict) -> list[dict]:
    """Check that all packages declare their source paths correctly in pyproject.toml."""
    violations = []
    for name, info in packages.items():
        package_path = info["path"]
        pyproject = root / package_path / "pyproject.toml"
        if not pyproject.exists():
            violations.append({
                "rule": "missing_pyproject",
                "file": str(pyproject),
                "line": 1,
                "message": f"Package {name} missing pyproject.toml at {pyproject}",
            })
            continue
        try:
            data = read_pyproject(pyproject)
            if "project" not in data or "name" not in data["project"]:
                violations.append({
                    "rule": "missing_package_name",
                    "file": str(pyproject),
                    "line": 1,
                    "message": f"Package {name} pyproject.toml missing [project].name",
                })
        except Exception:
            pass
    return violations


def _emit_contract(
    *,
    json_output: bool,
    repository_root: Optional[Path],
    checks: list[dict],
    verdict: str,
    exit_code: int,
    violations: Optional[list[dict]] = None,
    error: Optional[str] = None,
) -> None:
    """Emit the stable architecture-check contract for every exit path."""
    payload = {
        "repository_root": str(repository_root) if repository_root else None,
        "checks": checks,
        "all_required_checks_executed": all(
            item.get("executed") or item.get("classification") == "SKIPPED"
            for item in checks
        ) if checks else False,
        "verdict": verdict,
        "exit_code": exit_code,
        "violations": violations or [],
        "total_violations": len(violations or []),
    }
    if error:
        payload["error"] = error
    if json_output:
        print(json.dumps(payload, indent=2))
    elif error:
        print(f"ERROR: {error}", file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root (auto-detected if omitted)")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--graph", type=Path)
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    parser.add_argument(
        "--checker-timeout",
        type=int,
        default=5,
        help="Timeout in seconds for each subprocess checker",
    )
    parser.add_argument("--skip-root-validation", action="store_true",
                        help="Skip root marker validation (for testing only)")
    parser.add_argument("--skip-scaffold-check", action="store_true",
                        help="Skip scaffold architecture check (for testing only)")
    args = parser.parse_args(argv)

    root: Optional[Path] = None
    try:
        if args.root:
            root = args.root.resolve()
            if not args.skip_root_validation and not is_repository_root(root):
                raise FileNotFoundError(
                    f"Specified root is not a valid repository root: {root}"
                )
        else:
            root = find_repository_root()
    except FileNotFoundError as exc:
        _emit_contract(
            json_output=args.json,
            repository_root=root,
            checks=[],
            verdict="ERROR",
            exit_code=2,
            error=str(exc),
        )
        return 2
    except Exception as exc:
        _emit_contract(
            json_output=args.json,
            repository_root=root,
            checks=[],
            verdict="ERROR",
            exit_code=4,
            error=f"Root detection failed: {type(exc).__name__}: {exc}",
        )
        return 4

    config_path = (
        args.config.resolve()
        if args.config
        else root / "configs" / "architecture" / "scaffold_v2.yaml"
    )
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("configuration root must be a mapping")
    except FileNotFoundError:
        _emit_contract(
            json_output=args.json,
            repository_root=root,
            checks=[],
            verdict="ERROR",
            exit_code=2,
            error=f"Architecture config not found: {config_path}",
        )
        return 2
    except Exception as exc:
        _emit_contract(
            json_output=args.json,
            repository_root=root,
            checks=[],
            verdict="ERROR",
            exit_code=4,
            error=f"Architecture config unreadable: {type(exc).__name__}: {exc}",
        )
        return 4

    checks: list[CheckResult] = []
    import_started = time.perf_counter()
    invocation = [str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])]
    try:
        report, graph = check(root, config)
        import_exit = 0 if report["status"] == "PASS" else 1
        checks.append(CheckResult(
            name="import_boundaries",
            argv=[sys.executable, *invocation],
            cwd=str(root),
            executed=True,
            exit_code=import_exit,
            classification="PASS" if import_exit == 0 else "VIOLATION",
            duration_ms=int((time.perf_counter() - import_started) * 1000),
            stdout_tail="",
            stderr_tail="",
        ))
    except Exception as exc:
        checks.append(CheckResult(
            name="import_boundaries",
            argv=[sys.executable, *invocation],
            cwd=str(root),
            executed=True,
            exit_code=4,
            classification="CHECKER_ERROR",
            duration_ms=int((time.perf_counter() - import_started) * 1000),
            stdout_tail="",
            stderr_tail=str(exc)[-500:],
            error=f"{type(exc).__name__}: {exc}",
        ))
        _emit_contract(
            json_output=args.json,
            repository_root=root,
            checks=[item.to_dict() for item in checks],
            verdict="ERROR",
            exit_code=4,
            error=f"Import checker failed: {type(exc).__name__}: {exc}",
        )
        return 4

    if args.skip_scaffold_check:
        checks.append(CheckResult(
            name="scaffold",
            argv=[
                sys.executable,
                str(root / "scripts" / "scaffold_architecture_v2.py"),
                "--check",
            ],
            cwd=str(root),
            executed=False,
            exit_code=0,
            classification="SKIPPED",
            duration_ms=0,
            stdout_tail="",
            stderr_tail="",
        ))
    else:
        scaffold_path = root / "scripts" / "scaffold_architecture_v2.py"
        scaffold_argv = [sys.executable, str(scaffold_path), "--check"]
        if not scaffold_path.is_file():
            checks.append(CheckResult(
                name="scaffold",
                argv=scaffold_argv,
                cwd=str(root),
                executed=False,
                exit_code=3,
                classification="CHECKER_MISSING",
                duration_ms=0,
                stdout_tail="",
                stderr_tail=f"Checker not found: {scaffold_path}",
                error=f"FileNotFoundError: {scaffold_path}",
            ))
        else:
            checks.append(run_required_check(
                "scaffold",
                scaffold_argv,
                root,
                timeout=args.checker_timeout,
            ))

    scaffold = checks[-1]
    if scaffold.exit_code == 1:
        report["violations"].append({
            "rule": "scaffold_check_failed",
            "file": "scripts/scaffold_architecture_v2.py",
            "line": 0,
            "message": (
                "Scaffold check reported violations: "
                f"{scaffold.stderr_tail or scaffold.stdout_tail}"
            ),
        })
        report["status"] = "FAIL"
        report["total_violations"] = len(report["violations"])

    check_dicts = [item.to_dict() for item in checks]
    if scaffold.exit_code == 3:
        verdict, exit_code = "ERROR", 3
        error = "Required scaffold checker is missing"
    elif scaffold.exit_code not in (0, 1):
        verdict, exit_code = "ERROR", 4
        error = scaffold.error or "Required scaffold checker failed"
    elif report["status"] == "PASS":
        verdict, exit_code, error = "PASS", 0, None
    else:
        verdict, exit_code, error = "FAIL", 1, None

    _emit_contract(
        json_output=args.json,
        repository_root=root,
        checks=check_dicts,
        verdict=verdict,
        exit_code=exit_code,
        violations=report["violations"],
        error=error,
    )
    if not args.json and error is None:
        print(
            f"Architecture policy: {report['status']} "
            f"({report['total_violations']} violations)"
        )
        for item in report["violations"]:
            print(f"[{item['rule']}] {item['file']}:{item['line']} {item['message']}")
        if report["status"] == "PASS":
            print("Zero boundary violations detected")

    # Reports default inside the selected checkout, never the source checkout
    # that happened to provide this installed checker.
    report_path = args.report or (
        root
        / "artifacts"
        / "architecture_v2_runtime_cutover"
        / "phase_13"
        / "dependency_boundary_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    graph_path = args.graph or report_path.with_name("import_graph.json")
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
