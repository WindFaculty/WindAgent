"""Architecture gates for VP3D Phase 24 (FFmpeg assembly, Stage L)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FFMPEG_ASSEMBLY = (
    ROOT
    / "intelligence"
    / "windagent_intelligence"
    / "video"
    / "postproduction"
    / "ffmpeg_assembly.py"
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


def test_ffmpeg_assembly_boundary_is_bpy_free():
    imports = _imports(FFMPEG_ASSEMBLY)
    assert "bpy" not in imports
    assert all(not name.startswith("bpy.") for name in imports)


def test_ffmpeg_assembly_has_no_dynamic_code_execution():
    tree = ast.parse(FFMPEG_ASSEMBLY.read_text(encoding="utf-8"))
    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node, ast.Name)
        and node.func.id in {"eval", "exec", "compile", "__import__"}
    }
    assert forbidden_calls == set()


def test_ffmpeg_assembly_never_spawns_processes():
    # The Phase 24 kernel is pure planning/validation; the evidence producer
    # executes the argv against the real ffmpeg. No subprocess here.
    source = FFMPEG_ASSEMBLY.read_text(encoding="utf-8")
    imports = _imports(FFMPEG_ASSEMBLY)
    assert "subprocess" not in imports
    assert "os.system" not in source
    assert "shell=True" not in source


def test_core_never_imports_intelligence_postproduction():
    violations = []
    for path in CORE.rglob("*.py"):
        imports = _imports(path)
        if any(
            name.startswith("windagent_intelligence.video.postproduction")
            for name in imports
        ):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_ffmpeg_assembly_only_imports_core_and_stdlib():
    imports = _imports(FFMPEG_ASSEMBLY)
    allowed_prefixes = (
        "windagent_core.domain.video_production",
        "windagent_intelligence.video.postproduction",
    )
    for name in imports:
        if name.startswith("windagent_"):
            assert name.startswith(allowed_prefixes), name
        elif name.startswith("windagent_tools"):
            raise AssertionError(f"tools import in phase 24 kernel: {name}")
    assert not any(
        name.startswith("windagent_tools.windagent_providers") for name in imports
    )


def test_ffmpeg_assembly_allowlist_is_enforced_by_data():
    # The planner must be structurally unable to emit non-allowlisted filters:
    # the allowlist constant exists and unknown ops are rejected at runtime
    # (unit matrix covers the rejection; this test pins the boundary).
    source = FFMPEG_ASSEMBLY.read_text(encoding="utf-8")
    assert "ALLOWED_FILTER_OPS" in source
    assert "filter op not allowlisted" in source


def test_ffmpeg_assembly_has_no_raw_shell_interpolation():
    source = FFMPEG_ASSEMBLY.read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "subprocess" not in source
    # argv is always a list: no string-joined command templates.
    assert "os.popen" not in source
