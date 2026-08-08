"""VP3D Phase 17 — AI Motion Adapter canonical isolation architecture tests.

Proves the Phase 17 adapter layer meets the architecture rules:
- `intelligence/windagent_intelligence/video/ai_motion/` is provider-neutral:
  imports only `windagent_core` + `windagent_intelligence`; never imports
  `windagent_tools` / `windagent_providers` / browser modules; never
  launches processes or loads code dynamically. Providers enter ONLY
  through the `MotionGenerationPort` / `TextToMotionPort` /
  `VideoToMotionPort` protocols — a fake adapter implements them, a real
  provider would too;
- the adapter never executes anything: no bpy, no eval/exec, no pickle —
  raw AI motion payloads and metadata stay inert strings (stage_h §6);
- the core domain objects (`ai_motion.py`) are tools/intelligence-neutral
  and stay in core;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI_MOTION_DIR = (
    ROOT / "intelligence" / "windagent_intelligence" / "video" / "ai_motion"
)
CORE_AI_MOTION = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "ai_motion.py"
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


def _phase17_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(AI_MOTION_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase17_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _phase17_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase17 launches/imports upstream: {hits}"


def test_phase17_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _phase17_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            module = re.search(
                r"(?:import|from)\s+(windagent_[a-z_]+|third_party)", stripped
            )
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"phase17 imports forbidden deps: {offenders}"


def test_phase17_providers_only_via_ports():
    """No concrete provider is imported; the ports are the only boundary."""
    for rel, text in _phase17_py_files():
        assert "windagent_providers" not in text, f"{rel} imports a provider"
    # the fake adapter is the only 'provider' and it lives here as an
    # implementation of the ports
    assert "FakeMotionAdapter" in (
        AI_MOTION_DIR / "fake_adapter.py").read_text(encoding="utf-8")


def test_phase17_never_emits_bpy_or_executes_code():
    """Raw AI motion is inert data — no execution surface anywhere."""
    for rel, text in _phase17_py_files():
        assert "import bpy" not in text, f"{rel} must not import bpy"
        assert "bpy." not in text, f"{rel} must not touch bpy"
        assert "eval(" not in text and "exec(" not in text, \
            f"{rel} must not eval/exec"
        assert "pickle" not in text, f"{rel} must not unpickle provider data"
        assert "importlib" not in text, f"{rel} must not load code dynamically"


def test_phase17_has_no_llm_model_port_dependency():
    """The motion ports are motion-specific; the LLM port is not reused."""
    for rel, text in _phase17_py_files():
        assert "PreproductionModelPort" not in text, \
            f"{rel} must not depend on the LLM completion port"


def test_core_ai_motion_is_tools_neutral():
    text = CORE_AI_MOTION.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text
    assert "windagent_providers" not in text
    assert "import bpy" not in text
    assert "from windagent_intelligence import" not in text
    assert "from windagent_tools import" not in text
    assert "from windagent_providers import" not in text


def test_core_exports_phase17_models():
    import windagent_core.domain.video_production as vp

    for name in (
        "MotionCapabilityId", "MotionRequestId", "RawMotionArtifactId",
        "MotionCandidateId", "MotionFindingId", "SkeletonRemapReceiptId",
        "MotionOutputFormat", "MotionCandidateStatus", "MotionRetryKind",
        "MotionGenerationError", "MotionCapabilityMismatchError",
        "MotionQuarantineViolationError", "MotionRetryBudgetExceededError",
        "MOTION_ADAPTER_COMPILER_VERSION", "MALICIOUS_METADATA_MARKERS",
        "MotionCapability", "MotionGenerationRequest", "RawMotionArtifact",
        "SkeletonRemapReceipt", "MotionCandidate", "MotionFindingKind",
        "MotionFinding", "MotionValidationReport", "MotionValidator",
    ):
        assert hasattr(vp, name), f"core missing export {name}"


def test_intelligence_exports_phase17_services():
    import windagent_intelligence.video as video

    for name in (
        "AiMotionAdapter", "MotionApproveReceipt", "FakeMotionAdapter",
        "FAKE_PROVIDER", "FAKE_MODEL", "FAKE_MODEL_VERSION", "FAKE_SKELETON",
        "MotionGenerationPort", "TextToMotionPort", "VideoToMotionPort",
        "TransientProviderError", "SkeletonRemapService",
        "REQUIRED_TARGET_BONES", "MOTION_ADAPTER_LAYER_VERSION",
        "TRACK_PROVENANCE_FIELDS",
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
