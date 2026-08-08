"""VP3D Phase 18 — Facial pipeline canonical isolation architecture tests.

Proves the Phase 18 layer meets the architecture rules:
- the core domain module (`facial.py`) carries NO Blender data-block names
  (no shape-key / bone strings, no bpy) — semantic controls only; the
  adapter binding table lives in intelligence (stage_i §3);
- `intelligence/windagent_intelligence/video/facial/` is provider-neutral:
  imports only `windagent_core` + `windagent_intelligence`; never imports
  `windagent_tools` / `windagent_providers`; never executes code;
- the contract port (`FacialAnimationCompilerPort`) stays in core contracts;
- core domain is tools/intelligence-neutral;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACIAL_DIR = (
    ROOT / "intelligence" / "windagent_intelligence" / "video" / "facial"
)
CORE_FACIAL = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "facial.py"
)
CONTRACT_FACIAL = (
    ROOT / "core" / "windagent_core" / "contracts" / "video_production"
    / "facial_animation.py"
)

WS1 = "\\s"
DOT = "\\."

UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(WS1 + "*(?:from" + WS1 + "+windagent_tools|import" + WS1 + "+windagent_tools)\\b", re.MULTILINE),
    re.compile(WS1 + "*(?:from" + WS1 + "+windagent_providers|import" + WS1 + "+windagent_providers)\\b", re.MULTILINE),
    re.compile(WS1 + "*(?:from" + WS1 + "+browser|import" + WS1 + "+browser)\\b", re.MULTILINE),
    re.compile("sys" + DOT + "path" + DOT + "(?:insert|append)" + WS1 + "*\\(", re.MULTILINE),
    re.compile("subprocess" + DOT + "(?:run|Popen|call)" + WS1 + "*\\(", re.MULTILINE),
    re.compile("importlib" + DOT + "import_module" + WS1 + "*\\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
    "third_party",
)
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_intelligence")


def _facial_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(FACIAL_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase18_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _facial_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase18 launches/imports upstream: {hits}"


def test_phase18_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _facial_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            module = re.search(
                r"(?:import|from)\\s+(windagent_[a-z_]+|third_party)", stripped
            )
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"phase18 imports forbidden deps: {offenders}"


def test_phase18_never_emits_bpy_or_executes_code():
    for rel, text in _facial_py_files():
        assert "import bpy" not in text, f"{rel} must not import bpy"
        assert "bpy." not in text, f"{rel} must not touch bpy"
        assert "eval(" not in text and "exec(" not in text, \
            f"{rel} must not eval/exec"
        assert "pickle" not in text, f"{rel} must not unpickle data"
        assert "importlib" not in text, f"{rel} must not load code dynamically"


def test_phase18_domain_has_no_blender_data_block_names():
    """stage_i §3: the domain never carries bpy data-block names."""
    text = CORE_FACIAL.read_text(encoding="utf-8", errors="ignore")
    assert "import bpy" not in text
    assert "bpy." not in text
    assert "shape_key" not in text, "shape keys are adapter concerns"
    assert "shapeKey" not in text
    assert "jawOpen" not in text, "data-block names are adapter concerns"
    # semantic controls only
    assert '"jaw_open"' in text
    assert '"head_yaw"' in text


def test_phase18_adapter_binding_table_lives_in_intelligence():
    """The Blender binding table (semantic -> shape key/bone) is adapter data."""
    compiler_text = (FACIAL_DIR / "compiler.py").read_text(encoding="utf-8")
    assert "FACIAL_BINDING_TABLE" in compiler_text
    assert "shape_key" in compiler_text
    assert "jawOpen" in compiler_text


def test_core_facial_is_tools_neutral():
    text = CORE_FACIAL.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text
    assert "windagent_providers" not in text
    assert "from windagent_intelligence import" not in text


def test_contract_port_is_protocol_only():
    text = CONTRACT_FACIAL.read_text(encoding="utf-8", errors="ignore")
    assert "Protocol" in text
    assert "import bpy" not in text
    assert "windagent_tools" not in text


def test_core_exports_phase18_models():
    import windagent_core.domain.video_production as vp

    for name in (
        "PhonemeTrackId", "VisemeMapId", "EmotionCurveId", "BlinkTrackId",
        "GazeTrackId", "FacialTrackId", "FacialFindingId",
        "FacialValidationReceiptId", "BakedFacialActionId",
        "FacialRepairReceiptId",
        "VisemeShape", "FacialLayerKind", "FacialTrackStatus",
        "HeadBlendPolicy", "FacialFindingKind", "FacialRepairScope",
        "FacialInvalidationScope",
        "FacialCompileError", "VisemeMapMissingPhonemeError",
        "FacialRepairError", "FacialBakeError",
        "FACIAL_COMPILER_VERSION", "DRIFT_TOLERANCE_FRAMES",
        "PhonemeTrack", "VisemeMap", "VisemeKeyframe", "EmotionCurve",
        "BlinkTrack", "GazeTrack", "FacialAnimationTrack", "FacialFinding",
        "FacialValidationReceipt", "BakedFacialAction", "FacialRepairReceipt",
        "normalize_phoneme_track", "build_viseme_map", "compile_facial_track",
        "validate_facial_track", "bake_facial_track", "repair_facial_track",
        "build_preview_manifest",
    ):
        assert hasattr(vp, name), f"core missing export {name}"


def test_contract_exports_phase18_port():
    import windagent_core.contracts.video_production as contracts

    assert hasattr(contracts, "FacialAnimationCompilerPort")


def test_intelligence_exports_phase18_services():
    import windagent_intelligence.video as video

    for name in (
        "FacialAnimationCompiler", "FacialCompileRequest", "fake_alignment",
        "FACIAL_LAYER_VERSION", "FACIAL_BINDING_TABLE", "VIETNAMESE_LINE_A",
        "VIETNAMESE_LINE_B",
    ):
        assert hasattr(video, name), f"intelligence missing export {name}"


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".",
         "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
