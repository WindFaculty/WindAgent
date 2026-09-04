"""Architecture gates from plan sections 35 and 2 (enforced from day one).

These tests never import runtime code; they parse every V2 Python source file
and enforce the dependency direction:

    kernel  ->  (nothing)
    platform ->  kernel
    modules  ->  platform + kernel + own module packages only
    apps     ->  platform + modules through their public API

and the absolute rule: V2 must not import any package from the frozen old
WindAgent repository.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = V2_ROOT / "backend" / "src"

# Top-level packages that exist in the OLD WindAgent repository only.
LEGACY_TOP_LEVEL = frozenset(
    {
        "core",
        "orchestration",
        "intelligence",
        "providers",
        "storage",
        "tools",
        "execution",
        "workflows",
        "verification",
        "context",
        "memory",
        "observability",
        "evals",
        "plugins",
        "skills",
        "windagent_core",
        "windagent_orchestration",
        "windagent_intelligence",
        "windagent_providers",
        "windagent_storage",
        "windagent_tools",
        "windagent_execution",
        "windagent_workflows",
        "windagent_verification",
        "windagent_context",
        "windagent_memory",
        "windagent_observability",
        "windagent_evals",
        "windagent_plugins",
        "windagent_skills",
    }
)

INFRASTRUCTURE_MODULES = frozenset(
    {"fastapi", "sqlalchemy", "alembic", "httpx", "asyncpg", "uvicorn", "pydantic"}
)
STDLIB_MODULES = frozenset(sys.stdlib_module_names) | {"__future__"}

BACKEND_FILES = sorted((BACKEND_SRC / "windagent").rglob("*.py"))
SOURCE_ROOTS = [BACKEND_SRC] + sorted(
    (V2_ROOT / "apps" / app / "src").parent
    for app in ("api", "worker", "scheduler", "cli")
)
PLATFORM_CONTRACT_PACKAGES = (
    "commands",
    "queries",
    "modules",
    "jobs",
    "events",
    "persistence",
    "artifacts",
    "security",
    "observability",
)

# Phases 5 and 6 placed concrete adapters inside platform/persistence and
# platform/events (plan sections 8 and 10 target layouts).  Only the
# declared contract files remain infrastructure-free there; adapter files
# are gated separately by test_platform_adapters_import_only_the_toolchain.
# Packages not listed here keep the "every file is a contract" rule.
PLATFORM_CONTRACT_FILES: dict[str, frozenset[str]] = {
    "jobs": frozenset(
        {
            "contracts.py",
            "envelope.py",
            "errors.py",
            "registry.py",
            "result.py",
        }
    ),
    "persistence": frozenset({"contracts.py"}),
    "events": frozenset(
        {
            "contracts.py",
            "envelope.py",
            "registry.py",
            "dispatcher.py",
            "subscriptions.py",
        }
    ),
}


def _all_v2_sources() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        files.extend(p for p in root.rglob("*.py") if ".venv" not in p.parts)
    assert files, "no V2 sources discovered — scan configuration is broken"
    return files


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


@pytest.mark.architecture
def test_no_v2_file_imports_legacy_windagent_packages() -> None:
    violations: list[str] = []
    for path in _all_v2_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            top = module.split(".", 1)[0]
            if top in LEGACY_TOP_LEVEL:
                violations.append(f"{path.relative_to(V2_ROOT)}: imports {module}")
    assert not violations, "V2 must be self-contained:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_kernel_does_not_import_infrastructure_or_other_layers() -> None:
    violations: list[str] = []
    for path in (BACKEND_SRC / "windagent" / "kernel").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            top = module.split(".", 1)[0]
            second = module.split(".", 2)[1] if "." in module else ""
            if top in INFRASTRUCTURE_MODULES:
                violations.append(f"{path.name}: kernel imports {module}")
            if module == "windagent" or second in {"platform", "modules", "apps"}:
                violations.append(f"{path.name}: kernel imports {module}")
    assert not violations, "kernel must stay pure:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_kernel_only_depends_on_the_standard_library() -> None:
    """Phase 2 has no package dependency, including internal absolute imports."""
    violations: list[str] = []
    for path in (BACKEND_SRC / "windagent" / "kernel").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            top = module.split(".", 1)[0]
            if top == "windagent" or top not in STDLIB_MODULES:
                violations.append(f"{path.name}: kernel imports {module}")
    assert not violations, "kernel may only use relative imports and stdlib:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_platform_does_not_import_feature_modules_or_apps() -> None:
    violations: list[str] = []
    for path in (BACKEND_SRC / "windagent" / "platform").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            parts = module.split(".")
            if "windagent.modules" in module or "windagent_api" in parts[0]:
                violations.append(f"{path.name}: platform imports {module}")
            if parts[0].startswith(("windagent_worker", "windagent_scheduler")):
                violations.append(f"{path.name}: platform imports {module}")
    assert not violations, "platform must stay domain-agnostic:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_platform_contracts_only_depend_on_kernel_and_stdlib() -> None:
    """Phase 3 interfaces must not quietly become infrastructure adapters."""
    violations: list[str] = []
    platform_dir = BACKEND_SRC / "windagent" / "platform"
    for package in PLATFORM_CONTRACT_PACKAGES:
        package_dir = platform_dir / package
        declared_contract_files = PLATFORM_CONTRACT_FILES.get(package)
        if declared_contract_files is None:
            paths: tuple[Path, ...] = tuple(package_dir.rglob("*.py"))
        else:
            paths = tuple(
                package_dir / name
                for name in declared_contract_files
                if (package_dir / name).exists()
            )
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module in _imported_modules(tree):
                top = module.split(".", 1)[0]
                if top == "windagent" and not module.startswith("windagent.kernel"):
                    violations.append(f"{path.name}: contract imports {module}")
                elif top != "windagent" and top not in STDLIB_MODULES:
                    violations.append(f"{path.name}: contract imports {module}")
    assert not violations, "platform contracts must stay adapter-free:\n" + "\n".join(violations)


PLATFORM_ADAPTER_TOOLCHAIN = frozenset({"sqlalchemy", "alembic", "asyncpg"})

# Platform packages that hold concrete adapter files, with the windagent
# packages their adapters may import on top of kernel/configuration.
_PLATFORM_ADAPTER_DIRECTORIES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "jobs",
        frozenset(
            {
                "windagent.platform.events",
                "windagent.platform.persistence",
            }
        ),
    ),
    ("persistence", frozenset({"windagent.platform.configuration"})),
    (
        "events",
        frozenset(
            {
                "windagent.platform.configuration",
                "windagent.platform.persistence",
            }
        ),
    ),
)


@pytest.mark.architecture
def test_platform_adapters_import_only_the_platform_toolchain() -> None:
    """Platform adapters stay lean: kernel, sibling contracts, DB toolchain.

    Phase 5 moved persistence adapters into ``platform/persistence`` and
    Phase 6 the outbox/publisher into ``platform/events``; this gate keeps
    those packages from quietly growing an HTTP, web-framework or provider
    dependency.  Feature modules and apps are already excluded by
    ``test_platform_does_not_import_feature_modules_or_apps``.
    """
    violations: list[str] = []
    platform_dir = BACKEND_SRC / "windagent" / "platform"
    for package, allowed_windagent in _PLATFORM_ADAPTER_DIRECTORIES:
        contract_files = PLATFORM_CONTRACT_FILES.get(package, frozenset())
        package_dir = platform_dir / package
        for path in package_dir.rglob("*.py"):
            relative = path.relative_to(package_dir).as_posix()
            if relative in contract_files:
                continue  # gated by test_platform_contracts_only_depend_on_kernel_and_stdlib
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module in _imported_modules(tree):
                top = module.split(".", 1)[0]
                if top in STDLIB_MODULES:
                    continue
                if top == "windagent":
                    if module.startswith(
                        ("windagent.kernel", *allowed_windagent)
                    ):
                        continue
                    violations.append(f"{package}/{relative}: adapter imports {module}")
                elif top not in PLATFORM_ADAPTER_TOOLCHAIN:
                    violations.append(f"{package}/{relative}: adapter imports {module}")
    assert not violations, "platform adapters must stay lean:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_modules_do_not_import_each_other() -> None:
    violations: list[str] = []
    modules_dir = BACKEND_SRC / "windagent" / "modules"
    for path in modules_dir.rglob("*.py"):
        own = path.relative_to(modules_dir).parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            prefix = "windagent.modules."
            if module.startswith(prefix):
                other = module.removeprefix(prefix).split(".", 1)[0]
                if other != own:
                    violations.append(f"{path.name}: {own} imports {module}")
    assert not violations, "modules must interact via platform contracts:\n" + "\n".join(
        violations
    )


@pytest.mark.architecture
def test_sqlite_is_not_a_default_in_backend_source() -> None:
    """Only Settings' explicit test-environment escape hatch may mention it."""
    offenders: list[str] = []
    allowed = BACKEND_SRC / "windagent" / "platform" / "configuration" / "settings.py"
    for path in (BACKEND_SRC / "windagent").rglob("*.py"):
        if path == allowed:
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "sqlite" in text:
            offenders.append(str(path.relative_to(V2_ROOT)))
    assert not offenders, "SQLite default leaked into:\n" + "\n".join(offenders)
