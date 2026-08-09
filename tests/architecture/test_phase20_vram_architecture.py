"""Architecture gates for VP3D Phase 20 (VRAM budget manager)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VRAM_BUDGET = (
    ROOT
    / "tools"
    / "windagent_tools"
    / "production_engines"
    / "blender"
    / "vram_budget.py"
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


def test_vram_budget_boundary_is_bpy_free():
    imports = _imports(VRAM_BUDGET)
    assert "bpy" not in imports
    assert all(not name.startswith("bpy.") for name in imports)


def test_vram_budget_has_no_dynamic_code_execution():
    tree = ast.parse(VRAM_BUDGET.read_text(encoding="utf-8"))
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node, ast.Name)
        and node.func.id in {"eval", "exec", "compile", "__import__"}
    }
    assert forbidden_calls == set()


def test_core_never_imports_blender_vram_budget():
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
    # The adapter may reference the budget manager, but must stay free of bpy.
    imports = _imports(ADAPTER)
    assert "bpy" not in imports
    assert any(name.startswith("windagent_tools.production_engines.blender") for name in imports)
