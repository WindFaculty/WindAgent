"""Architecture gates for VP3D Phase 19."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RENDERING = (
    ROOT
    / "tools"
    / "windagent_tools"
    / "production_engines"
    / "blender"
    / "rendering.py"
)
EXECUTOR = (
    ROOT
    / "tools"
    / "windagent_tools"
    / "production_engines"
    / "blender"
    / "scripts"
    / "execute_job.py"
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


def test_render_profile_boundary_is_bpy_free():
    imports = _imports(RENDERING)
    assert "bpy" not in imports
    assert all(not name.startswith("bpy.") for name in imports)


def test_trusted_executor_remains_pure_stdlib():
    imports = _imports(EXECUTOR)
    forbidden = [
        name
        for name in imports
        if name.startswith("windagent_") or name.startswith("pydantic")
    ]
    assert forbidden == []


def test_core_never_imports_blender_render_adapter():
    violations = []
    for path in CORE.rglob("*.py"):
        imports = _imports(path)
        if any(
            name.startswith("windagent_tools.production_engines.blender")
            for name in imports
        ):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_phase19_contract_has_no_dynamic_code_execution():
    tree = ast.parse(RENDERING.read_text(encoding="utf-8"))
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"eval", "exec", "compile", "__import__"}
    }
    assert forbidden_calls == set()

