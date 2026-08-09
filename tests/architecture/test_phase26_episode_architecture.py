"""Architecture gates for VP3D Phase 26 (Multi-Scene Episode, Stage M)."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EPISODE_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video" / "episode"
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


def test_episode_never_imports_tools_or_providers():
    """The episode orchestrator is intelligence-side; legs are injected."""
    for path in _py_files(EPISODE_DIR):
        imports = _imports(path)
        assert not any(i.startswith("windagent_tools") for i in imports), path
        assert not any(i.startswith("windagent_providers") for i in imports), path


def test_episode_is_bpy_free():
    for path in _py_files(EPISODE_DIR):
        imports = _imports(path)
        assert "bpy" not in imports, path
        assert all(not i.startswith("bpy.") for i in imports), path


def test_episode_only_imports_core_and_intelligence():
    for path in _py_files(EPISODE_DIR):
        imports = _imports(path)
        foreign = {
            i
            for i in imports
            if i.startswith("windagent_")
            and not i.startswith("windagent_core")
            and not i.startswith("windagent_intelligence")
        }
        assert not foreign, f"{path}: {foreign}"


def test_core_episode_module_is_self_contained():
    """core/domain/video_production/episode.py imports only core."""
    module = CORE / "domain" / "video_production" / "episode.py"
    imports = _imports(module)
    foreign = {
        i
        for i in imports
        if i.startswith("windagent_") and not i.startswith("windagent_core")
    }
    assert not foreign, f"core episode imports: {foreign}"
    assert "bpy" not in imports


def test_core_never_imports_intelligence():
    """Core neutrality: episode domain must not reach intelligence."""
    module = CORE / "domain" / "video_production" / "episode.py"
    imports = _imports(module)
    assert not any(i.startswith("windagent_intelligence") for i in imports)


def test_episode_never_imports_golden_scene_intelligence_from_core():
    """Core episode reuses golden-scene DOMAIN models (allowed), never the
    intelligence orchestrator."""
    module = CORE / "domain" / "video_production" / "episode.py"
    imports = _imports(module)
    assert not any(i.startswith("windagent_intelligence") for i in imports)
    assert "windagent_core.domain.video_production.golden_scene" in imports


def test_episode_reuses_golden_scene_kernels_not_duplicates():
    """The episode package delegates scene kernels to golden_scene (reuse,
    backlog 1) instead of re-implementing them."""
    orchestrator = EPISODE_DIR / "orchestrator.py"
    source = orchestrator.read_text(encoding="utf-8")
    # the orchestrator must NOT vendor its own compile kernels — the golden
    # scene steps are injected by the composition root
    for kernel in ("CameraCompiler", "LightingCompiler", "AnimationCompiler",
                   "AudioMixNormalizer", "ScreenplayParser", "FacialAnimationCompiler"):
        assert kernel not in source, f"episode orchestrator vendors {kernel}"
    # it DOES reuse the golden-scene domain + step contracts
    assert "golden_scene" in source


def test_four_cache_decisions_defined():
    """Backlog 6: the cache report distinguishes hit/miss/invalidated/rejected."""
    from windagent_core.domain.video_production.enums import EpisodeCacheDecision

    values = {d.value for d in EpisodeCacheDecision}
    assert values == {"HIT", "MISS", "INVALIDATED", "REJECTED_REUSE"}
