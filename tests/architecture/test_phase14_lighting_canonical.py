"""VP3D Phase 14 — Lighting System canonical isolation architecture tests.

Proves the Phase 14 lighting layer meets the architecture rules:
- `intelligence/windagent_intelligence/video/lighting/` is provider-neutral
  and deterministic: imports only `windagent_core` + `windagent_intelligence`;
  never imports `windagent_tools` / `windagent_providers` / browser modules
  and never holds a model port (lighting compile is pure rules, no LLM call);
- the core domain objects (`lighting.py`) are tools/intelligence-neutral and
  stay in core;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIGHTING_DIR = (
    ROOT / "intelligence" / "windagent_intelligence" / "video" / "lighting"
)
CORE_LIGHTING = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "lighting.py"
)

WS1 = "\\s"
DOT = "\\."

UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(WS1 + "*(?:from" + WS1 + "+windagent_tools|import" + WS1 + "+windagent_tools)\\b", re.MULTILINE),
    re.compile(WS1 + "*(?:from" + WS1 + "+windagent_providers|import" + WS1 + "+windagent_providers)\\b", re.MULTILINE),
    re.compile(WS1 + "*(?:from" + WS1 + "+browser|import" + WS1 + "+browser)\\b", re.MULTILINE),
    re.compile("sys" + DOT + "path" + DOT + "(?:insert|append)" + WS1 + "*\\(", re.MULTILINE),
    re.compile("spec_from_file_location" + WS1 + "*\\(", re.MULTILINE),
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


def _phase14_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(LIGHTING_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase14_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _phase14_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase14 launches/imports upstream: {hits}"


def test_phase14_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _phase14_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            module = re.search(
                r"(?:import|from)\s+(windagent_[a-z_]+|third_party)", stripped
            )
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"phase14 imports forbidden deps: {offenders}"


def test_phase14_has_no_model_port_dependency():
    """Lighting compile is pure deterministic rules; must not call a provider."""
    for rel, text in _phase14_py_files():
        assert "PreproductionModelPort" not in text, f"{rel} should not require a model port"
        assert "model_port" not in text, f"{rel} should not hold a model port"


def test_phase14_never_emits_bpy_or_code_markers():
    """Director intent compiles to typed data; bpy transcription is a tools-layer job."""
    for rel, text in _phase14_py_files():
        assert "import bpy" not in text, f"{rel} must not import bpy"
        assert "bpy." not in text, f"{rel} must not touch bpy"
        assert "eval(" not in text and "exec(" not in text, f"{rel} must not eval/exec"


def test_core_lighting_is_tools_neutral():
    text = CORE_LIGHTING.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text
    assert "windagent_providers" not in text
    assert "import bpy" not in text
    assert "from windagent_intelligence import" not in text
    assert "from windagent_tools import" not in text
    assert "from windagent_providers import" not in text


def test_core_exports_phase14_models():
    import windagent_core.domain.video_production as vp

    for name in (
        "LightingIntentId", "LightRigPlanId", "LightingFindingId",
        "LightOverrideId", "LightingContactSheetId", "LightingMood",
        "LightingStyle", "LightingEmphasis", "LightRole",
        "LightingColorPolicy", "LightingCompileError",
        "LightingOverrideOutOfBoundsError", "LightSpec", "WorldSettings",
        "ExposureRange", "ShadowBounceBudget", "RenderPolicy",
        "LightingPreset", "LightingIntent", "LightOverride",
        "ResourceEstimate", "LightRigPlan", "LightingFindingKind",
        "LightingFinding", "LightingValidationReport", "LightingValidator",
        "LIGHTING_COMPILER_VERSION",
    ):
        assert hasattr(vp, name), f"core missing export {name}"


def test_intelligence_exports_phase14_services():
    import windagent_intelligence.video as video

    for name in (
        "LightingCompiler", "LightingCompileReceipt", "ContactSheetBuilder",
        "ContactSheetEntry", "LightingContactSheetManifest", "HISTOGRAM_BINS",
        "PRESET_REGISTRY_VERSION", "LIGHTING_COMPILER_LAYER_VERSION",
        "all_presets", "get_preset", "select_preset", "supported_preset_ids",
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
