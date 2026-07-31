"""
Architecture tests for the WindAgent Video Production protocol (Phase 3).

Proves:
- core never imports implementation packages (intelligence, tools,
  providers, workflows, storage) or third_party.
- No monolith package `video_system/` exists.
- Schema/event catalog has a single canonical definition (verified by
  scripts/check_duplicate_canonical_models.py).
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_CORE_IMPORTS = (
    "windagent_intelligence",
    "windagent_tools",
    "windagent_providers",
    "windagent_workflows",
    "windagent_storage",
    "third_party",
)

VIDEO_PRODUCTION_DIR = ROOT / "core" / "windagent_core" / "domain" / "video_production"
CONTRACTS_DIR = ROOT / "core" / "windagent_core" / "contracts" / "video_production"
EVENTS_FILE = ROOT / "core" / "windagent_core" / "events" / "video_production.py"


def _iter_python_files(*roots):
    for root in roots:
        for path in root.rglob("*.py"):
            yield path


def _imported_module_names(content: str):
    """Return top-level dotted module prefixes imported by the source."""
    tree = ast.parse(content)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestCoreBoundary:
    @pytest.mark.parametrize(
        "root",
        [VIDEO_PRODUCTION_DIR, CONTRACTS_DIR],
        ids=["domain", "contracts"],
    )
    def test_no_implementation_imports_in_core_packages(self, root):
        for path in _iter_python_files(root):
            content = path.read_text(encoding="utf-8")
            imported = _imported_module_names(content)
            for forbidden in FORBIDDEN_CORE_IMPORTS:
                assert forbidden not in imported, (
                    f"{path.relative_to(ROOT)} must not import {forbidden}."
                )

    def test_events_module_has_no_implementation_imports(self):
        content = EVENTS_FILE.read_text(encoding="utf-8")
        imported = _imported_module_names(content)
        for forbidden in FORBIDDEN_CORE_IMPORTS:
            assert forbidden not in imported, (
                f"{EVENTS_FILE.relative_to(ROOT)} must not import {forbidden}."
            )


class TestNoMonolith:
    def test_no_video_system_package(self):
        assert not (ROOT / "video_system").exists()
        assert not (ROOT / "core" / "windagent_core" / "video_system").exists()


class TestSingleCanonicalDefinition:
    def test_duplicate_canonical_models_checker_registers_vp_models(self):
        checker = ROOT / "scripts" / "check_duplicate_canonical_models.py"
        content = checker.read_text(encoding="utf-8")
        for model in (
            "VideoProductionPackage",
            "VideoProject",
            "ProductionRevision",
            "CinematicPlan",
            "ReferenceAsset",
            "ApprovalDecision",
            "VideoProductionEventEnvelope",
        ):
            # Note: ReviewResult is intentionally not registered (name shared
            # with the intelligence layer's reviewer aggregate).
            assert model in content, f"{model} must be registered in the canonical model checker."
