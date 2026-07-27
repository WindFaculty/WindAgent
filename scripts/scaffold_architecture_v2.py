#!/usr/bin/env python3
"""
Scaffold Generator for WindAgent Architecture V2.
Reads configs/architecture/scaffold_v2.yaml and creates workspace packages,
namespace packages, pyproject.toml files, and bounded context READMEs.

Supports:
  --dry-run : Preview changes without writing to disk
  --check   : Verify required scaffold contracts without overwriting maintained docs
  --create  : Generate or update scaffold files (idempotent)

Design notes for Phase 7 convergence:
  * Package __init__.py files derive __version__ from the canonical version
    authority (windagent_core.version.PRODUCT_VERSION).
  * App-layer packages (api, cli, worker) may declare required public exports in
    the scaffold config.  The generator emits a guarded block for these exports;
    the checker validates that the required symbols are exported rather than
    comparing the whole file.  This preserves hand-maintained documentation and
    additional app-layer re-exports across scaffold runs.
  * For packages WITHOUT declared public exports, the scaffold generator only
    enforces the canonical __version__ line; any hand-maintained public re-exports
    are preserved.
"""

import sys
import argparse
import re
import tomllib
import ast
from collections import defaultdict
from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "configs" / "architecture" / "scaffold_v2.yaml"

# Marker used to identify the generated public-exports block so it can be
# refreshed without destroying surrounding hand-maintained content.
EXPORTS_BEGIN = "# SCOPED_PUBLIC_EXPORTS_BEGIN"
EXPORTS_END = "# SCOPED_PUBLIC_EXPORTS_END"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_package_pyproject(pkg_name: str, pkg_info: dict) -> str:
    namespace = pkg_info["namespace"]
    desc = pkg_info["description"]
    version = pkg_info.get("version", "0.3.0")
    workspace_deps = [
        f"windagent-{dep.removeprefix('windagent_').removeprefix('windagent-').replace('_', '-')}"
        for dep in pkg_info.get("allowed_dependencies", [])
    ]
    deps = [*pkg_info.get("external_dependencies", []), *workspace_deps]
    deps_str = "\n".join(f'    "{dep}",' for dep in deps)
    deps_block = f"dependencies = [\n{deps_str}\n]" if deps else "dependencies = []"
    sources = "\n".join(f"{dep} = {{ workspace = true }}" for dep in workspace_deps)
    sources_block = f"\n[tool.uv.sources]\n{sources}\n" if sources else ""

    return f"""[project]
name = "{namespace}"
version = "{version}"
description = "{desc}"
readme = "README.md"
requires-python = ">=3.10"
{deps_block}
{sources_block}[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{namespace}"]
"""


def generate_package_readme(pkg_name: str, pkg_info: dict) -> str:
    namespace = pkg_info["namespace"]
    path = pkg_info["path"]
    desc = pkg_info["description"]
    allowed = pkg_info.get("allowed_dependencies", [])
    forbidden = pkg_info.get("forbidden_dependencies", [])
    legacy = pkg_info.get("legacy_source", "")

    allowed_str = "\n".join([f"- `{dep}`" for dep in allowed]) if allowed else "- None (leaf module)"
    forbidden_str = "\n".join([f"- `{dep}`" for dep in forbidden]) if forbidden else "- None"

    return f"""# {pkg_name.upper()} ({namespace})

## Responsibility
{desc}

## Target Package
`{path}/{namespace}`

## Allowed Dependencies
{allowed_str}

## Forbidden Dependencies
{forbidden_str}

## Legacy Migration Source
`{legacy}`

## Public API (Target)
- Expected domain models, interfaces, and public handlers for {pkg_name}.
- Exposed strictly via `{namespace}` top-level exports.

## Out-of-Scope
- Retired legacy implementation (Architecture V2 packages are authoritative).
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
"""


def _build_public_export_block(pkg_info: dict) -> str:
    """Generate the guarded public-exports block from declarative config."""
    required = pkg_info.get("public_exports", {}).get("required", {})
    if not required:
        return ""

    # Group symbols by source module for clean imports.
    by_module: dict[str, list[str]] = defaultdict(list)
    for symbol, module in required.items():
        by_module[module].append(symbol)

    lines = [EXPORTS_BEGIN, "# Required public exports maintained by scaffold config"]
    for module in sorted(by_module):
        symbols = sorted(by_module[module])
        lines.append(f"from {module} import {', '.join(symbols)}")

    all_symbols = sorted(required.keys())
    lines.append(f"__all__ = {all_symbols!r}")
    lines.append(EXPORTS_END)
    return "\n".join(lines)


def generate_package_init(pkg_name: str, pkg_info: dict) -> str:
    """Template used only when an __init__.py does not already exist."""
    desc = pkg_info["description"]
    body = f'"""\n{desc}\n"""\n\nfrom windagent_core.version import PRODUCT_VERSION\n'
    export_block = _build_public_export_block(pkg_info)
    if export_block:
        body += f"\n{export_block}\n"
    body += "\n__version__ = PRODUCT_VERSION\n"
    return body


def _extract_init_exports(source: str) -> tuple[set[str], bool]:
    """Parse __init__.py source and return exported symbols + whether version is canonical."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(), False

    exported = set()
    version_canonical = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exported.add(elt.value)
                    elif target.id == "__version__":
                        if (
                            isinstance(node.value, ast.Name)
                            and node.value.id == "PRODUCT_VERSION"
                        ):
                            version_canonical = True
                        elif (
                            isinstance(node.value, ast.Constant)
                            and node.value.value == "0.3.0"
                        ):
                            # During Phase 7 convergence we perform one-time
                            # migration from the historical frozen value to the
                            # canonical version authority.
                            version_canonical = False
                            # Allow scaffold --create to rewrite it.
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                # Treat direct imports at module top-level as public exports when
                # they are not private by convention.
                if not alias.asname and not alias.name.startswith("_"):
                    exported.add(alias.name)

    return exported, version_canonical


def _update_init_contents(current: str, pkg_info: dict) -> str:
    """
    Migrate an existing __init__.py to canonical form without discarding
    hand-maintained public exports.

    Ensures:
      * Canonical version import is present.
      * __version__ is set to PRODUCT_VERSION.
      * Config-declared required symbols are present in __all__.
    """
    required = pkg_info.get("public_exports", {}).get("required", {})

    # Normalize __version__ assignment to canonical authority.
    current = re.sub(
        r'^[ \t]*__version__\s*=\s*["\'][^"\']+["\']\s*$',
        "__version__ = PRODUCT_VERSION",
        current,
        flags=re.MULTILINE,
    )
    if "__version__" not in current:
        current += "\n__version__ = PRODUCT_VERSION\n"

    # Ensure canonical version import line is present, placed after the leading
    # module docstring if one exists so we don't break documentation style.
    import_line = "from windagent_core.version import PRODUCT_VERSION"
    if import_line not in current:
        docstring_match = re.match(r'^(\s*"""[\s\S]*?"""\n?)', current)
        if docstring_match:
            end = docstring_match.end()
            current = current[:end] + "\n" + import_line + "\n" + current[end:]
        else:
            current = import_line + "\n" + current

    if not required:
        return current

    exported, _ = _extract_init_exports(current)
    missing = set(required.keys()) - exported
    if not missing:
        return current

    # Inject or replace a guarded public-exports block at the end of the file.
    block = _build_public_export_block(pkg_info)
    # Strip any existing guarded block to avoid duplication.
    pattern = re.compile(
        rf"\n?{re.escape(EXPORTS_BEGIN)}.*?{re.escape(EXPORTS_END)}\n?",
        re.DOTALL,
    )
    current = pattern.sub("\n", current)
    current = current.rstrip() + "\n\n" + block + "\n"
    return current


def scaffold_matches(file_path: Path, current: str, expected: str, pkg_info: dict) -> bool:
    if file_path.name == "pyproject.toml":
        project = tomllib.loads(current).get("project", {})
        return project.get("name") == pkg_info["namespace"] and project.get("version") == pkg_info.get("version", "0.3.0")
    if file_path.name == "__init__.py":
        exported, version_ok = _extract_init_exports(current)
        if not version_ok:
            return False
        required = pkg_info.get("public_exports", {}).get("required", {})
        missing = set(required.keys()) - exported
        if missing:
            return False
        return True
    if file_path.name == "README.md":
        # Package READMEs become maintained runtime documentation after the
        # initial scaffold. Require identity and a responsibility heading, but
        # do not force them back to the historical generated migration text.
        return (
            current.lstrip().startswith("# ")
            and "## Responsibility" in current
            and pkg_info["namespace"] in current
        )
    return current.strip() == expected.strip()


def main():
    parser = argparse.ArgumentParser(description="Architecture V2 Scaffold Generator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview scaffold actions")
    group.add_argument("--check", action="store_true", help="Check scaffold consistency")
    group.add_argument("--create", action="store_true", help="Create or update scaffold files")

    args = parser.parse_args()
    config = load_config()
    packages = config.get("packages", {})

    diffs = []
    created_count = 0
    updated_count = 0

    for pkg_name, pkg_info in packages.items():
        pkg_rel_path = pkg_info["path"]
        namespace = pkg_info["namespace"]

        pkg_dir = ROOT_DIR / pkg_rel_path
        namespace_dir = pkg_dir / namespace
        init_file = namespace_dir / "__init__.py"
        pyproject_file = pkg_dir / "pyproject.toml"
        readme_file = pkg_dir / "README.md"

        expected_pyproject = generate_package_pyproject(pkg_name, pkg_info)
        expected_readme = generate_package_readme(pkg_name, pkg_info)
        expected_init = generate_package_init(pkg_name, pkg_info)

        target_files = [
            (pyproject_file, expected_pyproject, "pyproject.toml"),
            (readme_file, expected_readme, "README.md"),
        ]

        for file_path, expected_content, desc_name in target_files:
            rel_file_path = file_path.relative_to(ROOT_DIR)

            if not file_path.exists():
                diffs.append(f"MISSING: {rel_file_path}")
                if args.create:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(expected_content, encoding="utf-8")
                    created_count += 1
                elif args.dry_run:
                    print(f"[DRY-RUN] Would create: {rel_file_path}")
            else:
                current_content = file_path.read_text(encoding="utf-8")
                if not scaffold_matches(file_path, current_content, expected_content, pkg_info):
                    diffs.append(f"MISMATCH: {rel_file_path}")
                    if args.create:
                        file_path.write_text(expected_content, encoding="utf-8")
                        updated_count += 1
                    elif args.dry_run:
                        print(f"[DRY-RUN] Would update: {rel_file_path}")

        # __init__.py is handled separately: if missing generate the template;
        # if present, migrate canonical bits without destroying existing exports.
        rel_init = init_file.relative_to(ROOT_DIR)
        if not init_file.exists():
            diffs.append(f"MISSING: {rel_init}")
            if args.create:
                init_file.parent.mkdir(parents=True, exist_ok=True)
                init_file.write_text(expected_init, encoding="utf-8")
                created_count += 1
            elif args.dry_run:
                print(f"[DRY-RUN] Would create: {rel_init}")
        else:
            current_init = init_file.read_text(encoding="utf-8")
            migrated_init = _update_init_contents(current_init, pkg_info)
            if not scaffold_matches(init_file, current_init, expected_init, pkg_info):
                diffs.append(f"MISMATCH: {rel_init}")
                if args.create:
                    init_file.write_text(migrated_init, encoding="utf-8")
                    updated_count += 1
                elif args.dry_run:
                    print(f"[DRY-RUN] Would update: {rel_init}")

    if args.check:
        if diffs:
            print("Scaffold Check Failed! Diff list:")
            for d in diffs:
                print(f"  {d}")
            sys.exit(1)
        else:
            print("Scaffold Check Passed: All workspace packages are fully compliant and up to date.")
            sys.exit(0)

    if args.dry_run:
        print(f"[DRY-RUN] Finished. Total missing/mismatched items: {len(diffs)}")
    elif args.create:
        print(f"Scaffold Generation Complete: {created_count} files created, {updated_count} files updated.")
        sys.exit(0)


if __name__ == "__main__":
    main()
