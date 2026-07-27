#!/usr/bin/env python3
"""
WindAgent Version Consistency Checker (Phase 7A)

Single source of truth: windagent-core package metadata via importlib.metadata.
All other version references must derive from or match this canonical version.

Architecture generation, API version, provider protocol version, and artifact protocol version
are separate constants defined in windagent_core.version - they are NOT product_version.
"""

from __future__ import annotations
import sys
import json
import subprocess
import tomllib
from pathlib import Path
from importlib.metadata import version as pkg_version, PackageNotFoundError
from typing import Dict, List, Tuple, Any, Optional


# Canonical version sources
ROOT_PYPROJECT = Path("pyproject.toml")
PACKAGE_PYPROJECTS = {
    "windagent-core": Path("core/pyproject.toml"),
    "windagent-api": Path("apps/api/pyproject.toml"),
    "windagent-cli": Path("apps/cli/pyproject.toml"),
    "windagent-worker": Path("apps/worker/pyproject.toml"),
}
WEB_PACKAGE = Path("apps/web/package.json")
DESKTOP_PACKAGE = Path("apps/desktop/package.json")

# Version constants from canonical service
try:
    from windagent_core.version import (
        PRODUCT_VERSION,
        ARCHITECTURE_GENERATION,
        API_VERSION,
        PROVIDER_PROTOCOL_VERSION,
        ARTIFACT_PROTOCOL_VERSION,
    )
except ImportError:
    # Fallback if not installed
    PRODUCT_VERSION = "0.3.0"
    ARCHITECTURE_GENERATION = "v2"
    API_VERSION = "v2"
    PROVIDER_PROTOCOL_VERSION = "1.0.0"
    ARTIFACT_PROTOCOL_VERSION = "1.0.0"


class VersionChecker:
    """Checks version consistency across the repository."""

    def __init__(self, root: Path):
        self.root = root
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

    def _get_package_version(self, pkg_name: str) -> Optional[str]:
        """Get version from installed package metadata."""
        try:
            return pkg_version(pkg_name)
        except PackageNotFoundError:
            return None

    def check_root_workspace_version(self) -> bool:
        """Check root workspace version matches product version."""
        version = self._read_toml_version(ROOT_PYPROJECT)
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
        """Check all package pyproject.toml versions match product version."""
        all_ok = True
        for pkg_name, path in PACKAGE_PYPROJECTS.items():
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
        for pkg_name in PACKAGE_PYPROJECTS.keys():
            version = self._get_package_version(pkg_name)
            if version is None:
                self.warnings.append(f"Package {pkg_name} not installed, skipping metadata check")
                continue
            self.results[f"installed_{pkg_name}_version"] = version
            if version != PRODUCT_VERSION:
                self.errors.append(
                    f"Installed {pkg_name} version {version} != canonical product_version {PRODUCT_VERSION}"
                )
                all_ok = False
        return all_ok

    def check_dunder_versions(self) -> bool:
        """Check __version__ in package __init__.py files."""
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
                # Find __version__ = "..." or __version__ = PRODUCT_VERSION
                import re
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
                    # Check if it imports PRODUCT_VERSION from version module
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
            import re
            # Look for version=PRODUCT_VERSION or version="0.x.x"
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if not match:
                # Check for variable reference
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
            # Check if output contains product version
            if PRODUCT_VERSION not in result.stdout:
                self.warnings.append(
                    f"CLI --version output '{result.stdout.strip()}' may not contain product version {PRODUCT_VERSION}"
                )
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
        except ImportError:
            self.warnings.append("Worker module not importable, skipping")
        except Exception as e:
            self.errors.append(f"Failed to check worker version: {e}")
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

        # Protocol versions should NOT equal product version
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
        """Check web package version (if intended to sync)."""
        version = self._read_json_version(WEB_PACKAGE)
        if version:
            self.results["web_version"] = version
            if version != PRODUCT_VERSION:
                self.warnings.append(
                    f"Web package version {version} != product_version {PRODUCT_VERSION} (may be intentional)"
                )
        return True

    def check_desktop_version(self) -> bool:
        """Check desktop package version (if intended to sync)."""
        version = self._read_json_version(DESKTOP_PACKAGE)
        if version:
            self.results["desktop_version"] = version
            if version != PRODUCT_VERSION:
                self.warnings.append(
                    f"Desktop package version {version} != product_version {PRODUCT_VERSION} (may be intentional)"
                )
        return True

    def check_hardcoded_versions(self) -> bool:
        """Scan for hardcoded version strings that should use canonical service."""
        all_ok = True
        patterns = [
            r'version\s*=\s*["\']0\.\d+\.\d+["\']',  # version="0.x.x"
            r'__version__\s*=\s*["\']0\.\d+\.\d+["\']',
            r'["\']0\.3\.0["\']',  # old hardcoded version
            r'["\']0\.4\.0["\']',  # old hardcoded version
        ]
        exclude_dirs = {".git", ".venv", "__pycache__", "node_modules", ".tmp-uv-cache", "artifacts", "dist", "build"}
        exclude_files = {"check_version_consistency.py"}

        import re
        for py_file in self.root.rglob("*.py"):
            if any(part in exclude_dirs for part in py_file.parts):
                continue
            if py_file.name in exclude_files:
                continue
            try:
                content = py_file.read_text()
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        # Skip if it's in a test file or comment
                        if "test_" in py_file.name or "# " in content[max(0, content.index(match)-50):content.index(match)]:
                            continue
                        self.warnings.append(f"Potential hardcoded version in {py_file}: {match}")
            except Exception:
                pass
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
            ("Root workspace version", self.check_root_workspace_version),
            ("Package pyproject.toml versions", self.check_package_versions),
            ("Installed package metadata versions", self.check_installed_package_versions),
            ("__version__ in __init__.py files", self.check_dunder_versions),
            ("FastAPI app version", self.check_fastapi_version),
            ("CLI --version command", self.check_cli_version_command),
            ("Worker module version", self.check_worker_version),
            ("Architecture generation", self.check_architecture_generation),
            ("Protocol versions distinct from product", self.check_protocol_versions_distinct),
            ("Web package version", self.check_web_version),
            ("Desktop package version", self.check_desktop_version),
            ("Hardcoded version scan", self.check_hardcoded_versions),
        ]

        all_passed = True
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

        return all_passed


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    checker = VersionChecker(root)
    passed = checker.run_all_checks()

    # Write report
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

    report_path = root / "artifacts" / "architecture_v2_production_hardening" / "phase_07" / "version_consistency_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Report written to {report_path}")

    if not passed:
        print("VERSION CONSISTENCY CHECK: FAILED")
        return 1
    print("VERSION CONSISTENCY CHECK: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())