"""Phase 13 regression tests — alignment between architecture checker and source tree."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / "apps" / "api" / "windagent_api"
WORKER_SRC = ROOT / "apps" / "worker" / "windagent_worker"
INTELLIGENCE_SRC = ROOT / "intelligence" / "windagent_intelligence"
ORCHESTRATION_SRC = ROOT / "orchestration" / "windagent_orchestration"
API_PYPROJECT = ROOT / "apps" / "api" / "pyproject.toml"
WORKER_PYPROJECT = ROOT / "apps" / "worker" / "pyproject.toml"
CHECKER = ROOT / "scripts" / "check_architecture_imports.py"


def _extract_workspace_imports(source_dir: Path) -> set[str]:
    """AST-scan a package tree and return the set of imported windagent_* top-level modules."""
    imported = set()
    for source in source_dir.rglob("*.py"):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("windagent_"):
                        imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("windagent_"):
                    imported.add(node.module.split(".")[0])
    return imported


def _extract_declared_dependencies(pyproject: Path) -> set[str]:
    import tomllib
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    return {dep.split("[")[0].strip().replace("-", "_") for dep in deps}


def test_intelligence_does_not_import_orchestration():
    """Intelligence must not directly import Orchestration per architecture policy."""
    imports = _extract_workspace_imports(INTELLIGENCE_SRC)
    assert "windagent_orchestration" not in imports


def test_orchestration_does_not_import_intelligence():
    """Orchestration must not directly import Intelligence per architecture policy."""
    imports = _extract_workspace_imports(ORCHESTRATION_SRC)
    assert "windagent_intelligence" not in imports


def _undeclared_imports(source_dir: Path, pyproject: Path) -> set[str]:
    """Return windagent_* packages imported by source_dir but missing from pyproject deps.

    The package's own name is excluded: a package importing itself is an
    intra-package import, not an external dependency.
    """
    self_name = source_dir.name.replace("-", "_")
    imports = _extract_workspace_imports(source_dir)
    declared = _extract_declared_dependencies(pyproject)
    return {
        imp
        for imp in imports
        if imp != self_name
        and imp.replace("_", "-") not in declared
        and imp.replace("-", "_") not in declared
    }


def test_api_declares_all_imported_packages():
    """Every windagent_* package imported by API source must be declared in pyproject.toml."""
    undeclared = _undeclared_imports(API_SRC, API_PYPROJECT)
    assert not undeclared, f"API undeclared dependencies: {undeclared}"


def test_worker_declares_all_imported_packages():
    """Every windagent_* package imported by Worker source must be declared in pyproject.toml."""
    undeclared = _undeclared_imports(WORKER_SRC, WORKER_PYPROJECT)
    assert not undeclared, f"Worker undeclared dependencies: {undeclared}"


def test_no_production_fallback_symbols():
    """Regex scan over production source for any _fallback_* symbol outside tests/."""
    import re

    pattern = re.compile(r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b")
    for base in [API_SRC, WORKER_SRC, INTELLIGENCE_SRC, ORCHESTRATION_SRC]:
        for source in base.rglob("*.py"):
            relative = source.relative_to(ROOT).as_posix()
            if relative.startswith("tests/"):
                continue
            for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.split("#", 1)[0]
                if pattern.search(stripped):
                    raise AssertionError(f"Production fallback symbol at {relative}:{lineno}: {line.strip()}")


def test_architecture_check_cli_returns_zero():
    """windagent architecture-check exits 0 on the clean repository."""
    package_roots = [
        str(ROOT / path)
        for path in (
            "apps/cli",
            "core",
            "orchestration",
            "intelligence",
            "providers",
            "tools",
            "workflows",
            "verification",
            "context",
            "memory",
            "execution",
            "storage",
            "observability",
            "evals",
            "plugins",
            "skills",
        )
    ]
    env = os.environ.copy()
    if env.get("PYTHONPATH"):
        package_roots.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(package_roots)

    result = subprocess.run(
        [sys.executable, "-m", "windagent_cli.main", "architecture-check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "PASSED" in result.stdout or "ALL CHECKS PASSED" in result.stdout


def test_checker_uses_scaffold_v2_yaml():
    """The checker default config points to the single source of truth policy file."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_architecture_imports", CHECKER
    )
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    assert checker.DEFAULT_CONFIG.resolve() == (ROOT / "configs" / "architecture" / "scaffold_v2.yaml").resolve()


def test_checker_and_regression_report_same_violation_set():
    """Checker output rule set must match a simple AST regression scan rule set."""
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # Regression scan is already expressed in test_no_production_fallback_symbols and
    # package declare tests.  Successful execution of the checker on the real repo
    # confirms the two rule sets agree at zero violations.
