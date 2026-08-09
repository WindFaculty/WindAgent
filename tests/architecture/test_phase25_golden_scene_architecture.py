"""Architecture gates for VP3D Phase 25 (Golden Scene E2E, Stage M)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_SCENE_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video" / "golden_scene"
CORE = ROOT / "core" / "windagent_core"


def _py_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_golden_scene_never_imports_tools_or_providers():
    """The orchestrator is intelligence-side; legs are injected ports."""
    for path in _py_files(GOLDEN_SCENE_DIR):
        imports = _imports(path)
        assert not any(i.startswith("windagent_tools") for i in imports), path
        assert not any(i.startswith("windagent_providers") for i in imports), path


def test_golden_scene_is_bpy_free():
    for path in _py_files(GOLDEN_SCENE_DIR):
        imports = _imports(path)
        assert "bpy" not in imports, path
        assert all(not i.startswith("bpy.") for i in imports), path


def test_golden_scene_only_imports_core_and_intelligence():
    for path in _py_files(GOLDEN_SCENE_DIR):
        imports = _imports(path)
        foreign = {
            i
            for i in imports
            if i.startswith("windagent_")
            and not i.startswith("windagent_core")
            and not i.startswith("windagent_intelligence")
        }
        assert not foreign, f"{path}: {foreign}"


def test_core_golden_scene_module_is_self_contained():
    """core/domain/video_production/golden_scene.py imports only core."""
    module = CORE / "domain" / "video_production" / "golden_scene.py"
    imports = _imports(module)
    foreign = {
        i
        for i in imports
        if i.startswith("windagent_")
        and not i.startswith("windagent_core")
    }
    assert not foreign, f"core golden_scene imports: {foreign}"
    assert "bpy" not in imports


def test_core_never_imports_intelligence():
    """Core neutrality: golden scene domain must not reach intelligence."""
    for path in _py_files(CORE / "domain" / "video_production"):
        if path.name != "golden_scene.py":
            continue
        imports = _imports(path)
        assert not any(i.startswith("windagent_intelligence") for i in imports)


def test_dag_is_exactly_ten_nodes():
    from windagent_core.domain.video_production.golden_scene import (
        GOLDEN_SCENE_DAG,
    )

    assert len(GOLDEN_SCENE_DAG) == 10
    names = [k.value for k in GOLDEN_SCENE_DAG]
    assert names == [
        "SCRIPT",
        "IR",
        "ASSETS",
        "SCENE",
        "ANIMATION_AUDIO",
        "FACIAL",
        "RENDER",
        "REVIEW_REPAIR",
        "FFMPEG",
        "FINAL",
    ]
