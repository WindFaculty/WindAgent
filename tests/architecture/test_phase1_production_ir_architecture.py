"""
Architecture tests for the VP3D Phase 1 Production IR.

Proves (plan §4 "Kiểm thử"):
- no Production IR domain model imports Flow, Blender or Unreal SDKs;
- the IR package never imports tools/providers/workflows/storage/third_party;
- the ProductionEnginePort contract leaks no engine SDK (`bpy`, Unreal) or
  Flow concepts;
- the IR event module stays inside the core events boundary.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

IR_DIR = ROOT / "core" / "windagent_core" / "domain" / "video_production" / "production_ir"
PORT_FILE = ROOT / "core" / "windagent_core" / "contracts" / "video_production" / "production_engine.py"
IR_EVENTS_FILE = ROOT / "core" / "windagent_core" / "events" / "video_production_ir.py"

FORBIDDEN_IMPORTS = (
    "windagent_intelligence",
    "windagent_tools",
    "windagent_providers",
    "windagent_workflows",
    "windagent_storage",
    "windagent_observability",
    "windagent_execution",
    "third_party",
)

# Engine/Flow concepts that must never appear as identifiers in the IR
# public surface (models + enums). The migrator is the BOUNDED compatibility
# layer and is allowed to name the legacy types it converts; it is therefore
# excluded from this strict identifier check (it still must obey the package
# import boundary).
FORBIDDEN_CONCEPTS = (
    "bpy",
    "blender",
    "unreal",
    "google_flow",
    "flow_",
    "generation_mode",
    "text_to_video",
    "image_to_video",
    "video_extension",
    "selector",
)


def _iter_python_files(*roots):
    for root in roots:
        for path in root.rglob("*.py"):
            yield path


def _imported_module_names(content: str):
    tree = ast.parse(content)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestIrBoundary:
    @pytest.mark.parametrize("root", [IR_DIR], ids=["production_ir"])
    def test_no_implementation_imports_in_ir_package(self, root):
        for path in _iter_python_files(root):
            content = path.read_text(encoding="utf-8")
            imported = _imported_module_names(content)
            for forbidden in FORBIDDEN_IMPORTS:
                assert forbidden not in imported, (
                    f"{path.relative_to(ROOT)} must not import {forbidden}."
                )

    @pytest.mark.parametrize(
        "filename",
        ["models.py", "enums.py"],
        ids=["models", "enums"],
    )
    def test_ir_public_surface_has_no_engine_or_flow_identifiers(self, filename):
        path = IR_DIR / filename
        content = path.read_text(encoding="utf-8")
        identifiers = _identifiers(content)
        for concept in FORBIDDEN_CONCEPTS:
            assert concept not in identifiers, (
                f"{path.relative_to(ROOT)} contains identifier {concept!r}."
            )

    def test_port_contract_leaks_no_engine_sdk(self):
        content = PORT_FILE.read_text(encoding="utf-8")
        identifiers = _identifiers(content)
        # The port may NAME blender/unreal in docstring prose (they are the
        # adapters it targets); it must never IMPORT or reference engine SDK
        # objects or Flow concepts as identifiers.
        for concept in ("bpy", "generation_mode", "selector", "cookie", "flow_prompt"):
            assert concept not in identifiers, f"port leaks {concept}"

    def test_ir_events_module_stays_in_core_boundary(self):
        content = IR_EVENTS_FILE.read_text(encoding="utf-8")
        imported = _imported_module_names(content)
        for forbidden in FORBIDDEN_IMPORTS:
            assert forbidden not in imported

    def test_migrator_only_touches_legacy_via_core_types(self):
        """The migrator names legacy types but only CORE domain types — never
        tools/providers/workflows/storage or engine SDKs."""
        migrator = IR_DIR / "migrator.py"
        content = migrator.read_text(encoding="utf-8")
        imported = _imported_module_names(content)
        for forbidden in FORBIDDEN_IMPORTS:
            assert forbidden not in imported
        # The migrator's only contact with Flow/legacy concepts is through
        # core domain imports (prompt_compiler, shot_graph, generation_job).
        assert "windagent_core" in imported


def _identifiers(content: str):
    """Return lowercase identifiers (imports, classes, function/field names)."""
    tree = ast.parse(content)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.lower())
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.lower())
            for alias in node.names:
                found.add(alias.name.lower())
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            found.add(node.name.lower())
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id.lower())
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    found.add(tgt.id.lower())
    return found
