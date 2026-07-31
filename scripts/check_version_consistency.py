#!/usr/bin/env python3
"""
WindAgent Version Consistency Checker (Phase 7)

Single source of truth: windagent-core package metadata via importlib.metadata.
All other version references must derive from or match this canonical version.

Architecture generation, API version, provider protocol version, and artifact
protocol version are separate constants defined in windagent_core.version - they
are NOT product_version.

Usage:
    python scripts/check_version_consistency.py
    python scripts/check_version_consistency.py --root /path/to/repo
    python scripts/check_version_consistency.py --root /path/to/repo --json
"""

from __future__ import annotations
import sys
import json
import subprocess
import tomllib
import re
import argparse
from pathlib import Path
from importlib.metadata import version as pkg_version, PackageNotFoundError
from typing import Dict, List, Any, Optional


# Version constants from canonical service.
# In a source checkout without installed metadata we still need to validate
# versions.  We therefore compute a fallback workspace metadata version from the
# root pyproject.toml when importlib.metadata is unavailable.
def _derive_fallback_product_version(root: Path) -> Optional[str]:
    try:
        with open(root / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version")
    except Exception:
        return None


_FALLBACK_VERSION = _derive_fallback_product_version(Path(__file__).resolve().parent.parent)
_CANONICAL_IMPORT_ERROR: Optional[str] = None


def _load_canonical_versions() -> Dict[str, str]:
    global _CANONICAL_IMPORT_ERROR
    try:
        from windagent_core.version import (
            PRODUCT_VERSION,
            ARCHITECTURE_GENERATION,
            API_VERSION,
            PROVIDER_PROTOCOL_VERSION,
            ARTIFACT_PROTOCOL_VERSION,
        )
        return {
            "product_version": PRODUCT_VERSION,
            "architecture_generation": ARCHITECTURE_GENERATION,
            "api_version": API_VERSION,
            "provider_protocol_version": PROVIDER_PROTOCOL_VERSION,
            "artifact_protocol_version": ARTIFACT_PROTOCOL_VERSION,
        }
    except ImportError as exc:
        _CANONICAL_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
        return {
            "product_version": _FALLBACK_VERSION or "0.3.0",
            "architecture_generation": "v2",
            "api_version": "v2",
            "provider_protocol_version": "1.0.0",
            "artifact_protocol_version": "1.0.0",
        }


_CANONICAL = _load_canonical_versions()
PRODUCT_VERSION = _CANONICAL["product_version"]
ARCHITECTURE_GENERATION = _CANONICAL["architecture_generation"]
API_VERSION = _CANONICAL["api_version"]
PROVIDER_PROTOCOL_VERSION = _CANONICAL["provider_protocol_version"]
ARTIFACT_PROTOCOL_VERSION = _CANONICAL["artifact_protocol_version"]


class VersionChecker:
    """Checks version consistency across the repository."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.results: Dict[str, Any] = {}

    def _read_toml_version(self, path: Path) -> Optional[str]:
        """Read version from pyproject.toml."""
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("version")
        except Exception as e:
            self.errors.append(f"Failed to read {path}: {e}")
            return None

    def _read_json_version(self, path: Path) -> Optional[str]:
        """Read version from package.json."""
        try:
            with open(path) as f:
                data = json.load(f)
            return data.get("version")
        except Exception as e:
            self.errors.append(f"Failed to read {path}: {e}")
            return None

    def check_canonical_version_import(self) -> bool:
        """The canonical runtime version module must be importable in CI."""
        if _CANONICAL_IMPORT_ERROR is None:
            self.results["canonical_version_source"] = "windagent_core.version"
            return True
        self.errors.append(
            "Canonical version module is not importable: "
            f"{_CANONICAL_IMPORT_ERROR}"
        )
        self.results["canonical_version_source"] = "fallback_metadata"
        return False

    def _get_package_version(self, pkg_name: str) -> Optional[str]:
        """Get version from installed package metadata or workspace pyproject.toml."""
        try:
            return pkg_version(pkg_name)
        except PackageNotFoundError:
            pyprojects = self._discover_workspace_pyprojects()
            if pkg_name in pyprojects:
                return self._read_toml_version(pyprojects[pkg_name])
            return None

    def _discover_workspace_pyprojects(self) -> Dict[str, Path]:
        """Discover all workspace member pyproject.toml files."""
        discovered: Dict[str, Path] = {}
        try:
            with open(self.root / "pyproject.toml", "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            self.errors.append(f"Failed to read root pyproject.toml: {e}")
            return discovered

        members = data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
        for pattern in members:
            for pkg_dir in self.root.glob(pattern):
                pyproject = pkg_dir / "pyproject.toml"
                if not pyproject.exists():
                    continue
                try:
                    with open(pyproject, "rb") as f:
                        name = tomllib.load(f).get("project", {}).get("name")
                    if name:
                        discovered[name] = pyproject
                except Exception:
                    continue
        return discovered

    def check_root_workspace_version(self) -> bool:
        """Check root workspace version matches product version."""
        version = self._read_toml_version(self.root / "pyproject.toml")
        if version is None:
            return False
        self.results["root_workspace_version"] = version
        if version != PRODUCT_VERSION:
            self.errors.append(
                f"Root workspace version {version} != canonical product_version {PRODUCT_VERSION}"
            )
            return False
        return True

    def check_package_versions(self) -> bool:
        """Check all workspace package pyproject.toml versions match product version."""
        all_ok = True
        for pkg_name, path in self._discover_workspace_pyprojects().items():
            version = self._read_toml_version(path)
            if version is None:
                all_ok = False
                continue
            self.results[f"package_{pkg_name}_version"] = version
            if version != PRODUCT_VERSION:
                self.errors.append(
                    f"Package {pkg_name} version {version} != canonical product_version {PRODUCT_VERSION}"
                )
                all_ok = False
        return all_ok

    def check_installed_package_versions(self) -> bool:
        """Check installed package versions via importlib.metadata."""
        all_ok = True
        for pkg_name in self._discover_workspace_pyprojects().keys():
            version = self._get_package_version(pkg_name)
            if version is None:
                self.errors.append(
                    f"Package {pkg_name} is not installed; metadata check cannot run"
                )
                all_ok = False
                continue
            self.results[f"installed_{pkg_name}_version"] = version
            if version != PRODUCT_VERSION:
                self.errors.append(
                    f"Installed {pkg_name} version {version} != canonical product_version {PRODUCT_VERSION}"
                )
                all_ok = False
        return all_ok

    def check_dunder_versions(self) -> bool:
        """Check __version__ in app-layer package __init__.py files."""
        all_ok = True
        init_files = {
            "windagent_core": self.root / "core/windagent_core/__init__.py",
            "windagent_api": self.root / "apps/api/windagent_api/__init__.py",
            "windagent_cli": self.root / "apps/cli/windagent_cli/__init__.py",
            "windagent_worker": self.root / "apps/worker/windagent_worker/__init__.py",
        }
        for pkg_name, path in init_files.items():
            try:
                content = path.read_text()
                match = re.search(r'__version__\s*=\s*(["\']([^"\']+)["\']|PRODUCT_VERSION)', content)
                if match:
                    version = match.group(2) if match.group(2) else PRODUCT_VERSION
                    self.results[f"dunder_{pkg_name}_version"] = version
                    if version != PRODUCT_VERSION:
                        self.errors.append(
                            f"{pkg_name}.__version__ {version} != canonical product_version {PRODUCT_VERSION}"
                        )
                        all_ok = False
                else:
                    if "from windagent_core.version import" in content and "PRODUCT_VERSION" in content:
                        self.results[f"dunder_{pkg_name}_version"] = PRODUCT_VERSION
                    else:
                        self.warnings.append(f"No __version__ found in {path}")
            except Exception as e:
                self.errors.append(f"Failed to check {path}: {e}")
                all_ok = False
        return all_ok

    def check_fastapi_version(self) -> bool:
        """Check FastAPI app version matches product version."""
        main_py = self.root / "apps/api/windagent_api/main.py"
        try:
            content = main_py.read_text()
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if not match:
                if "version=PRODUCT_VERSION" in content:
                    self.results["fastapi_app_version"] = PRODUCT_VERSION
                    return True
                self.errors.append("FastAPI app version not found in main.py")
                return False
            version = match.group(1)
            self.results["fastapi_app_version"] = version
            if version != PRODUCT_VERSION:
                self.errors.append(
                    f"FastAPI app version {version} != canonical product_version {PRODUCT_VERSION}"
                )
                return False
        except Exception as e:
            self.errors.append(f"Failed to check FastAPI version: {e}")
            return False
        return True

    def check_cli_version_command(self) -> bool:
        """Test CLI --version command."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "windagent_cli", "--version"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=30,
            )
            self.results["cli_version_output"] = result.stdout.strip()
            self.results["cli_version_returncode"] = result.returncode
            if result.returncode != 0:
                self.errors.append(
                    "CLI --version command failed with "
                    f"exit {result.returncode}: {result.stderr.strip()}"
                )
                return False
            if PRODUCT_VERSION not in result.stdout:
                self.errors.append(
                    f"CLI --version output '{result.stdout.strip()}' does not contain product version {PRODUCT_VERSION}"
                )
                return False
        except subprocess.TimeoutExpired:
            self.errors.append("CLI --version command timed out")
            return False
        except Exception as e:
            self.errors.append(f"CLI --version failed: {e}")
            return False
        return True

    def check_worker_version(self) -> bool:
        """Check worker module version."""
        try:
            import windagent_worker
            version = getattr(windagent_worker, "__version__", None)
            if version:
                self.results["worker_module_version"] = version
                if version != PRODUCT_VERSION:
                    self.errors.append(
                        f"Worker __version__ {version} != canonical product_version {PRODUCT_VERSION}"
                    )
                    return False
            else:
                self.errors.append("Worker module has no __version__")
                return False
        except ImportError as exc:
            self.errors.append(
                f"Worker module is not importable: {type(exc).__name__}: {exc}"
            )
            return False
        except Exception as e:
            self.errors.append(f"Failed to check worker version: {e}")
            return False
        return True

    def check_api_openapi_version(self) -> bool:
        """Check that the FastAPI OpenAPI version matches product version."""
        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 "from windagent_api.main import app; print(app.version)"],
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=30,
            )
            self.results["api_openapi_returncode"] = result.returncode
            if result.returncode != 0:
                self.errors.append(
                    "API OpenAPI version command failed with "
                    f"exit {result.returncode}: {result.stderr.strip()}"
                )
                return False
            version = result.stdout.strip()
            self.results["api_openapi_version"] = version
            if version != PRODUCT_VERSION:
                self.errors.append(
                    f"API OpenAPI version {version} != canonical product_version {PRODUCT_VERSION}"
                )
                return False
        except Exception as e:
            self.errors.append(f"Failed to check API OpenAPI version: {e}")
            return False
        return True

    def check_architecture_generation(self) -> bool:
        """Verify architecture generation is v2."""
        self.results["architecture_generation"] = ARCHITECTURE_GENERATION
        if ARCHITECTURE_GENERATION != "v2":
            self.errors.append(f"Architecture generation {ARCHITECTURE_GENERATION} != expected 'v2'")
            return False
        return True

    def check_protocol_versions_distinct(self) -> bool:
        """Verify protocol versions are distinct from product version."""
        all_ok = True
        self.results["api_version"] = API_VERSION
        self.results["provider_protocol_version"] = PROVIDER_PROTOCOL_VERSION
        self.results["artifact_protocol_version"] = ARTIFACT_PROTOCOL_VERSION

        if API_VERSION == PRODUCT_VERSION:
            self.errors.append(f"API_VERSION {API_VERSION} should not equal PRODUCT_VERSION {PRODUCT_VERSION}")
            all_ok = False
        if PROVIDER_PROTOCOL_VERSION == PRODUCT_VERSION:
            self.errors.append(
                f"PROVIDER_PROTOCOL_VERSION {PROVIDER_PROTOCOL_VERSION} should not equal PRODUCT_VERSION {PRODUCT_VERSION}"
            )
            all_ok = False
        if ARTIFACT_PROTOCOL_VERSION == PRODUCT_VERSION:
            self.errors.append(
                f"ARTIFACT_PROTOCOL_VERSION {ARTIFACT_PROTOCOL_VERSION} should not equal PRODUCT_VERSION {PRODUCT_VERSION}"
            )
            all_ok = False
        return all_ok

    def check_web_version(self) -> bool:
        """Check web package version (warning only unless intended to sync)."""
        version = self._read_json_version(self.root / "apps/web/package.json")
        if version:
            self.results["web_version"] = version
            if version != PRODUCT_VERSION:
                self.warnings.append(
                    f"Web package version {version} != product_version {PRODUCT_VERSION} (may be intentional)"
                )
        return True

    def check_desktop_version(self) -> bool:
        """Check desktop package version (warning only unless intended to sync)."""
        version = self._read_json_version(self.root / "apps/desktop/package.json")
        if version:
            self.results["desktop_version"] = version
            if version != PRODUCT_VERSION:
                self.warnings.append(
                    f"Desktop package version {version} != product_version {PRODUCT_VERSION} (may be intentional)"
                )
        return True

    def check_hardcoded_versions(self) -> bool:
        """Scan for hardcoded product version strings that should use canonical service.

        Phase 5 hardening: Removed the early-return guard that disabled this scan
        when PRODUCT_VERSION == "0.3.0". The scan now always runs.
        Excludes test files, build artifacts, and the canonical version module itself.
        """
        all_ok = True
        exclude_dirs = {
            ".git",
            ".venv",
            "__pycache__",
            "node_modules",
            ".tmp-uv-cache",
            ".pytest_tmp",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "artifacts",
            "dist",
            "build",
        }
        exclude_files = {"check_version_consistency.py", "version.py", "pyproject.toml"}
        # Always-allowed: known-safe version strings or templates
        # NOTE: PRODUCT_VERSION ("0.3.0") is intentionally NOT in always_allowed.
        # Phase 5 removed the old guard that skipped scanning at version 0.3.0.
        # The scan must always run regardless of product version value.
        always_allowed = {"0.0.0", "1.0.0"}

        # The product version may be a semver string like "0.3.0". We look for
        # literal occurrences of PRODUCT_VERSION to flag places that should
        # import from windagent_core.version instead.
        for py_file in self.root.rglob("*.py"):
            relative_path = py_file.relative_to(self.root)
            if any(part in exclude_dirs for part in relative_path.parts):
                continue
            if py_file.name in exclude_files:
                continue
            if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                continue
            try:
                content = py_file.read_text()
                for version_str in [PRODUCT_VERSION]:
                    if version_str in always_allowed:
                        continue
                    if f'"{version_str}"' in content or f"'{version_str}'" in content:
                        # Check if file already imports from windagent_core.version
                        if "from windagent_core.version import" in content:
                            continue
                        self.errors.append(
                            f"Potential hardcoded product version literal in {relative_path}: "
                            f"'{version_str}' (use import from windagent_core.version instead)"
                        )
                        all_ok = False
            except Exception as exc:
                self.errors.append(
                    f"Failed to scan {relative_path}: {exc}"
                )
                all_ok = False
        return all_ok

    def run_all_checks(self) -> bool:
        """Run all version consistency checks."""
        print("Running version consistency checks...")
        print(f"Canonical product_version: {PRODUCT_VERSION}")
        print(f"Architecture generation: {ARCHITECTURE_GENERATION}")
        print(f"API version: {API_VERSION}")
        print(f"Provider protocol version: {PROVIDER_PROTOCOL_VERSION}")
        print(f"Artifact protocol version: {ARTIFACT_PROTOCOL_VERSION}")
        print()

        checks = [
            ("Canonical version import", self.check_canonical_version_import),
            ("Root workspace version", self.check_root_workspace_version),
            ("Package pyproject.toml versions", self.check_package_versions),
            ("Installed package metadata versions", self.check_installed_package_versions),
            ("__version__ in __init__.py files", self.check_dunder_versions),
            ("FastAPI app version", self.check_fastapi_version),
            ("API OpenAPI version", self.check_api_openapi_version),
            ("CLI --version command", self.check_cli_version_command),
            ("Worker module version", self.check_worker_version),
            ("Architecture generation", self.check_architecture_generation),
            ("Protocol versions distinct from product", self.check_protocol_versions_distinct),
            ("Web package version", self.check_web_version),
            ("Desktop package version", self.check_desktop_version),
            ("Hardcoded version scan", self.check_hardcoded_versions),
        ]

        all_passed = not self.errors
        for name, check_fn in checks:
            print(f"  Checking {name}...", end=" ")
            try:
                result = check_fn()
                if result:
                    print("PASS")
                else:
                    print("FAIL")
                    all_passed = False
            except Exception as e:
                print(f"ERROR: {e}")
                self.errors.append(f"Check {name} raised exception: {e}")
                all_passed = False

        print()
        if self.warnings:
            print("WARNINGS:")
            for w in self.warnings:
                print(f"  - {w}")
            print()

        if self.errors:
            print("ERRORS:")
            for e in self.errors:
                print(f"  - {e}")
            print()

        return all_passed and not self.errors


def main() -> int:
    parser = argparse.ArgumentParser(description="WindAgent Version Consistency Checker")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Report result as JSON to stdout")
    parser.add_argument(
        "--report",
        type=Path,
        help=(
            "Report path (default: artifacts/ci/version_consistency_report.json "
            "under --root)"
        ),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if not (root / "pyproject.toml").exists():
        if args.json:
            print(json.dumps({"error": f"No pyproject.toml found at {root}"}))
        else:
            print(f"ERROR: No pyproject.toml found at {root}", file=sys.stderr)
        return 2

    checker = VersionChecker(root)
    passed = checker.run_all_checks()

    report = {
        "product_version": PRODUCT_VERSION,
        "architecture_generation": ARCHITECTURE_GENERATION,
        "api_version": API_VERSION,
        "provider_protocol_version": PROVIDER_PROTOCOL_VERSION,
        "artifact_protocol_version": ARTIFACT_PROTOCOL_VERSION,
        "checks_passed": passed,
        "errors": checker.errors,
        "warnings": checker.warnings,
        "results": checker.results,
    }

    report_path = args.report or Path(
        "artifacts/ci/version_consistency_report.json"
    )
    if not report_path.is_absolute():
        report_path = root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Report written to {report_path}")

    if not passed:
        print("VERSION CONSISTENCY CHECK: FAILED")
        return 1
    print("VERSION CONSISTENCY CHECK: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
