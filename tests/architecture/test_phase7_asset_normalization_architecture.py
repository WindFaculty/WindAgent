"""
VP3D Phase 7 — Asset Normalization architecture boundary tests (Stage C §5).

Mandatory checks:
1. ``core`` (domain + contracts) never imports the normalization/tools or
   provider implementation packages.
2. ``tools/windagent_tools/media_assets/`` keeps the engine-neutral pipeline:
   no ``bpy``, no Blender adapter import, no subprocess, no upstream, no
   sys.path mutation (same contract as the Phase 7 media asset pipeline).
3. ``bpy`` may ONLY be imported inside blender-side job scripts that run
   inside blender.exe (pure stdlib module level).
4. The ``AssetNormalizerPort`` leaks no engine SDK or transport.
5. No hard-coded per-machine blender paths in the new code.
"""

import ast
import re
from pathlib import Path

from windagent_core.contracts.video_production.asset_normalizer import AssetNormalizerPort

ROOT = Path(__file__).resolve().parents[2]

NORMALIZATION_DIR = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "asset_normalization"
)
PORT_FILE = ROOT / "core" / "windagent_core" / "contracts" / "video_production" / "asset_normalizer.py"
MEDIA_ASSETS_DIR = ROOT / "tools" / "windagent_tools" / "media_assets"
BLENDER_ASSET_PIPELINE = ROOT / "tools" / "windagent_tools" / "production_engines" / "blender" / "asset_pipeline.py"
ASSET_JOB_SCRIPT = ROOT / "tools" / "windagent_tools" / "production_engines" / "blender" / "scripts" / "execute_asset_job.py"

FORBIDDEN_CORE_IMPORTS = ("windagent_providers", "windagent_tools", "windagent_intelligence", "windagent_storage", "windagent_workflows")

UPSTREAM_LAUNCH_PATTERNS = (
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
)

LEGACY_TERMS = ("google_flow", "FlowVideo", "TEXT_TO_VIDEO", "generation_mode")


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


class TestNormalizationBoundary:
    def test_core_never_imports_implementation_packages(self):
        violations = []
        for path in _iter_python_files(NORMALIZATION_DIR) + [PORT_FILE]:
            content = path.read_text(encoding="utf-8")
            for mod in _imported_modules(content):
                root = mod.split(".")[0]
                if root in FORBIDDEN_CORE_IMPORTS:
                    violations.append(f"{path.relative_to(ROOT)} imports {mod}")
        assert not violations, "core imports implementation:\n" + "\n".join(violations)

    def test_port_leaks_no_engine_sdk_or_transport(self):
        """Identifier-level check: prose may NAME engines, imports may not."""
        content = PORT_FILE.read_text(encoding="utf-8")
        identifiers = set()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                identifiers.add(node.name.lower())
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                identifiers.add(node.target.id.lower())
        for forbidden in ("bpy", "unreal", "httpx", "requests", "urllib"):
            assert forbidden not in identifiers, f"port leaks {forbidden}"
        imported = _imported_modules(content)
        for forbidden in ("windagent_providers", "windagent_tools"):
            assert forbidden not in imported, f"port imports {forbidden}"

    def test_normalizer_port_implemented_by_pipeline(self):
        from windagent_tools.media_assets.normalization import AssetNormalizer

        assert isinstance(AssetNormalizer, AssetNormalizerPort)
        for method in ("normalize", "formats_supported"):
            assert callable(getattr(AssetNormalizer, method)), f"missing {method}"

    def test_media_assets_has_no_bpy_and_no_blender_adapter_import(self):
        for path in _iter_python_files(MEDIA_ASSETS_DIR):
            content = path.read_text(encoding="utf-8")
            assert "import bpy" not in content and "from bpy" not in content, (
                f"{path.relative_to(ROOT)} imports bpy"
            )
            for mod in _imported_modules(content):
                assert "production_engines" not in mod, (
                    f"{path.relative_to(ROOT)} imports Blender adapter {mod}"
                )

    def test_media_assets_normalization_never_launches_or_imports_upstream(self):
        hits = []
        for path in _iter_python_files(MEDIA_ASSETS_DIR):
            if "normalization" not in str(path):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in UPSTREAM_LAUNCH_PATTERNS:
                for match in pattern.finditer(content):
                    hits.append(f"{path.relative_to(ROOT)}:{content[:match.start()].count(chr(10)) + 1}")
        assert hits == [], f"host normalization launches upstream: {hits}"

    def test_media_assets_import_roots_canonical(self):
        offenders = []
        for path in _iter_python_files(MEDIA_ASSETS_DIR):
            content = path.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    continue
                if "windagent" not in stripped:
                    continue
                match = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
                if match and match.group(1) not in ("windagent_core", "windagent_tools"):
                    offenders.append(f"{path.relative_to(ROOT)}: {stripped}")
        assert offenders == [], f"forbidden deps: {offenders}"

    def test_asset_job_script_pure_stdlib_module_level(self):
        content = ASSET_JOB_SCRIPT.read_text(encoding="utf-8")
        for line in content.splitlines():
            if not line or line.startswith((" ", "\t")):
                continue
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "windagent" not in stripped, f"module-level host import: {stripped}"
                assert not stripped.startswith("import bpy"), f"module-level bpy import: {stripped}"

    def test_blender_asset_pipeline_never_hardcodes_machine_paths(self):
        content = BLENDER_ASSET_PIPELINE.read_text(encoding="utf-8")
        for needle in ("C:/Program Files/Blender Foundation", "D:/Blender/"):
            assert needle not in content

    def test_new_code_free_of_legacy_flow_concepts(self):
        for path in (
            NORMALIZATION_DIR,
            MEDIA_ASSETS_DIR / "normalization",
            BLENDER_ASSET_PIPELINE.parent,
        ):
            for py in _iter_python_files(path):
                content = py.read_text(encoding="utf-8", errors="ignore")
                for term in LEGACY_TERMS:
                    assert term not in content, f"{py.relative_to(ROOT)} contains {term}"
