"""Architecture gates for VP3D Phase 21 (fault-tolerant render jobs)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RENDER_JOBS = (
    ROOT
    / "tools"
    / "windagent_tools"
    / "production_engines"
    / "blender"
    / "render_jobs.py"
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


def test_render_jobs_boundary_is_bpy_free():
    imports = _imports(RENDER_JOBS)
    assert "bpy" not in imports
    assert all(not name.startswith("bpy.") for name in imports)


def test_render_jobs_has_no_dynamic_code_execution():
    tree = ast.parse(RENDER_JOBS.read_text(encoding="utf-8"))
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node, ast.Name)
        and node.func.id in {"eval", "exec", "compile", "__import__"}
    }
    assert forbidden_calls == set()


def test_core_never_imports_blender_render_jobs():
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
    # The adapter may reference the recovery policy, but must stay free of bpy.
    imports = _imports(ADAPTER)
    assert "bpy" not in imports
    assert any(name.startswith("windagent_tools.production_engines.blender") for name in imports)


def test_render_jobs_only_imports_engine_neutral_dependencies():
    # No providers / no tools outside the blender package / no bpy.
    imports = _imports(RENDER_JOBS)
    for name in imports:
        assert not name.startswith("windagent_tools.windagent_providers"), name
        assert not name.startswith("windagent_tools.production_engines.") or (
            name.startswith("windagent_tools.production_engines.blender")
        ), name
