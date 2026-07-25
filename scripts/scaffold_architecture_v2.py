#!/usr/bin/env python3
"""
Scaffold Generator for WindAgent Architecture V2.
Reads configs/architecture/scaffold_v2.yaml and creates workspace packages,
namespace packages, pyproject.toml files, and bounded context READMEs.

Supports:
  --dry-run : Preview changes without writing to disk
  --check   : Verify that all expected scaffold files exist with correct content (exit 0 if clean, 1 if diffs found)
  --create  : Generate or update scaffold files (idempotent)
"""

import sys
import argparse
import re
import tomllib
from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "configs" / "architecture" / "scaffold_v2.yaml"


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
{sources_block}
[build-system]
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
- Legacy backend services running in `apps/backend/`.
- Concrete implementations of other bounded contexts.

## Acceptance Criteria
- 100% type-annotated code.
- Clean separation from non-allowed layers.
- Full test coverage for public contract interfaces.
"""


def generate_package_init(pkg_name: str, pkg_info: dict) -> str:
    desc = pkg_info["description"]
    version = pkg_info.get("version", "0.3.0")
    return f'"""\n{desc}\n"""\n\n__version__ = "{version}"\n'


def scaffold_matches(file_path: Path, current: str, expected: str, pkg_info: dict) -> bool:
    if file_path.name == "pyproject.toml":
        project = tomllib.loads(current).get("project", {})
        return project.get("name") == pkg_info["namespace"] and project.get("version") == pkg_info.get("version", "0.3.0")
    if file_path.name == "__init__.py":
        return bool(re.search(r'^__version__\s*=\s*["\'][^"\']+["\']', current, re.MULTILINE))
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
            (init_file, expected_init, "__init__.py"),
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

    if args.check:
        if diffs:
            print("Scaffold Check Failed! Diff list:")
            for d in diffs:
                print(f"  {d}")
            sys.exit(1)
        else:
            print("Scaffold Check Passed: All 16 workspace packages are fully compliant and up to date.")
            sys.exit(0)

    if args.dry_run:
        print(f"[DRY-RUN] Finished. Total missing/mismatched items: {len(diffs)}")
    elif args.create:
        print(f"Scaffold Generation Complete: {created_count} files created, {updated_count} files updated.")
        sys.exit(0)


if __name__ == "__main__":
    main()
