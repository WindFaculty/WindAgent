"""Architecture gates for VP3D Phase 22 (3D technical reviewer)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TECHNICAL_REVIEW = (
    ROOT
    / "tools"
    / "windagent_tools"
    / "production_engines"
    / "blender"
    / "technical_review.py"
)
ADAPTER = (
    ROOT
    / "tools"
    / "windagent_tools"
    / "production_engines"
    / "blender"
    / "adapter.py"
)
CORE = ROOT / "core" / "windagent_core"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_technical_review_boundary_is_bpy_free():
    imports = _imports(TECHNICAL_REVIEW)
    assert "bpy" not in imports
    assert all(not name.startswith("bpy.") for name in imports)


def test_technical_review_has_no_dynamic_code_execution():
    tree = ast.parse(TECHNICAL_REVIEW.read_text(encoding="utf-8"))
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node, ast.Name)
        and node.func.id in {"eval", "exec", "compile", "__import__"}
    }
    assert forbidden_calls == set()


def test_core_never_imports_blender_technical_review():
    violations = []
    for path in CORE.rglob("*.py"):
        imports = _imports(path)
        if any(
            name.startswith("windagent_tools.production_engines.blender")
            for name in imports
        ):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_adapter_keeps_engine_boundary_intact():
    imports = _imports(ADAPTER)
    assert "bpy" not in imports
    assert any(
        name.startswith("windagent_tools.production_engines.blender")
        for name in imports
    )


def test_technical_review_only_imports_engine_neutral_dependencies():
    imports = _imports(TECHNICAL_REVIEW)
    for name in imports:
        assert not name.startswith("windagent_tools.windagent_providers"), name
        assert not name.startswith("windagent_tools.production_engines.") or (
            name.startswith("windagent_tools.production_engines.blender")
        ), name


def test_technical_review_reuses_phase20_vram_kernel():
    # The VRAM pre-render gate must reuse the Phase 20 budget kernel, not
    # re-implement VRAM math (Stage K §2: extend, don't fork).
    text = TECHNICAL_REVIEW.read_text(encoding="utf-8")
    assert "VramMitigationPlanner" in text
    assert "SceneResourceManifest" in text


def test_vlm_reviewer_boundary_is_bpy_free():
    VLM = (
        ROOT
        / "tools"
        / "windagent_tools"
        / "production_engines"
        / "blender"
        / "vlm_reviewer.py"
    )
    imports = _imports(VLM)
    assert "bpy" not in imports
    assert all(not name.startswith("bpy.") for name in imports)
    assert "windagent_tools.windagent_providers" not in imports


def test_vlm_reviewer_has_no_dynamic_code_execution():
    VLM = (
        ROOT
        / "tools"
        / "windagent_tools"
        / "production_engines"
        / "blender"
        / "vlm_reviewer.py"
    )
    tree = ast.parse(VLM.read_text(encoding="utf-8"))
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node, ast.Name)
        and node.func.id in {"eval", "exec", "compile", "__import__"}
    }
    assert forbidden_calls == set()
