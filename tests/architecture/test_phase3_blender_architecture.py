"""
VP3D Phase 3 — Blender Runtime architecture boundary tests (plan Stage B §3).

Mandatory checks:
1. `core/windagent_core` never imports the Blender adapter package.
2. The Blender adapter implements `ProductionEnginePort` with NO engine SDK
   (`bpy`, Unreal) leaking through the IR surface.
3. No legacy Flow concepts (`google_flow`, `FlowVideo`, generation modes) in
   the Blender runtime.
4. No hard-coded per-machine blender paths in source.
5. `execute_job.py` is pure stdlib (no windagent imports) — it must run inside
   Blender's bundled Python.
"""

import ast
import inspect
from pathlib import Path

from windagent_core.contracts.video_production.production_engine import ProductionEnginePort
from windagent_tools.production_engines.blender.adapter import BlenderEngineAdapter

ROOT = Path(__file__).resolve().parents[2]

BLENDER_PKG = ROOT / "tools" / "windagent_tools" / "production_engines" / "blender"
CORE_PKG = ROOT / "core" / "windagent_core"

LEGACY_TERMS = (
    "google_flow",
    "FlowVideo",
    "FlowImage",
    "TEXT_TO_VIDEO",
    "IMAGE_TO_VIDEO",
    "FRAMES_TO_VIDEO",
    "VIDEO_EXTENSION",
    "GenerationMode",
)


def _iter_python_files(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]


def _imported_modules(content: str) -> set[str]:
    tree = ast.parse(content)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class TestPhase3BlenderArchitecture:
    def test_core_never_imports_blender_adapter(self):
        """core/domain & core/contracts must not depend on the Blender adapter."""
        violations = []
        for path in _iter_python_files(CORE_PKG):
            content = path.read_text(encoding="utf-8")
            for mod in _imported_modules(content):
                if "production_engines" in mod or "windagent_tools" in mod:
                    violations.append(f"{path.relative_to(ROOT)} imports {mod}")
        assert not violations, f"core imports adapter package:\n" + "\n".join(violations)

    def test_adapter_implements_production_engine_port(self):
        # Structural check against the runtime-checkable Protocol.
        assert issubclass(BlenderEngineAdapter, ProductionEnginePort)
        for method in (
            "submit_scene",
            "submit_shot",
            "inspect_job",
            "cancel_job",
            "download_artifact",
        ):
            assert callable(getattr(BlenderEngineAdapter, method)), f"missing {method}"
        # No engine SDK identifiers in the port-facing surface.
        port_source = inspect.getsource(ProductionEnginePort)
        for forbidden in ("bpy", "unreal"):
            assert forbidden not in port_source, f"port leaks {forbidden}"

    def test_no_legacy_flow_concepts_in_blender_runtime(self):
        violations = []
        for path in _iter_python_files(BLENDER_PKG):
            content = path.read_text(encoding="utf-8")
            for term in LEGACY_TERMS:
                if term in content:
                    violations.append(f"{path.relative_to(ROOT)} contains {term}")
        assert not violations, f"legacy Flow concepts leaked:\n" + "\n".join(violations)

    def test_no_hardcoded_machine_paths(self):
        violations = []
        for path in _iter_python_files(BLENDER_PKG):
            content = path.read_text(encoding="utf-8")
            for needle in ("C:/Program Files/Blender Foundation/Blender 5", "D:/Blender/"):
                if needle in content:
                    violations.append(f"{path.relative_to(ROOT)} hardcodes {needle}")
        assert not violations

    def test_execute_job_pure_stdlib(self):
        """execute_job.py must not import windagent — it runs inside Blender Python."""
        script = BLENDER_PKG / "scripts" / "execute_job.py"
        content = script.read_text(encoding="utf-8")
        modules = _imported_modules(content)
        forbidden = [m for m in modules if m.startswith("windagent") or m.startswith("bpy.")]
        assert not forbidden, f"execute_job.py imports non-stdlib: {forbidden}"

    def test_runtime_detector_uses_standard_locations_not_hardcoded_path(self):
        detector = BLENDER_PKG / "runtime" / "detector.py"
        content = detector.read_text(encoding="utf-8")
        # Foundation dirs are scan ROOTS (allowed); an explicit full exe path is not.
        assert "Program Files/Blender Foundation" in content
        assert "blender.exe" in content
        # Config path wins: the detector must accept configured_path.
        assert "configured_path" in content
