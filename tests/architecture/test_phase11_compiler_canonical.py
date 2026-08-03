"""Phase 11 - Reference Binding + Prompt Compiler canonical isolation tests
(plan 03 §4, §24.4).

Proves the Phase 11 layers
(`intelligence/windagent_intelligence/video/reference_selector/` and
`intelligence/windagent_intelligence/video/prompt_compiler/`) meet the Phase 11
architecture rules:
- no upstream import / sys.path mutation / subprocess (clean-room, plan §4);
- provider-neutral: imports only `windagent_core` + `windagent_intelligence`;
  never imports `windagent_tools` / `windagent_providers` / browser modules;
- the binding + compiler layers are fully deterministic (no model port
  required);
- core domain objects (ReferenceBinding / ReferenceBindingPlan /
  ReferenceBindingValidator / PromptBlock / CompiledPrompt /
  FlowGenerationSpecification / PromptCompilerIssue / PromptSecurityFinding /
  compute_request_hash) live in core and stay intelligence/tools-neutral;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SELECTOR_DIR = (
    ROOT / "intelligence" / "windagent_intelligence" / "video" / "reference_selector"
)
PROMPT_COMPILER_DIR = (
    ROOT / "intelligence" / "windagent_intelligence" / "video" / "prompt_compiler"
)
CORE_REFERENCE_BINDING = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "reference_binding.py"
)
CORE_PROMPT_COMPILER = (
    ROOT / "core" / "windagent_core" / "domain" / "video_production" / "prompt_compiler.py"
)

UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call)\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
)
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_intelligence")


def _phase11_py_files() -> list[tuple[str, str]]:
    files = []
    for directory in (REFERENCE_SELECTOR_DIR, PROMPT_COMPILER_DIR):
        for py in sorted(directory.rglob("*.py")):
            rel = py.relative_to(ROOT).as_posix()
            files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase11_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _phase11_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase11 launches/imports upstream: {hits}"


def test_phase11_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _phase11_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"phase11 imports forbidden deps: {offenders}"


def test_phase11_has_no_model_port_dependency():
    """Phase 11 binding + compilation is deterministic; must not call a provider."""
    for rel, text in _phase11_py_files():
        assert "PreproductionModelPort" not in text, f"{rel} should not require a model port"
        assert "model_port" not in text, f"{rel} should not hold a model port"


def test_core_phase11_models_are_tools_neutral():
    for path in (CORE_REFERENCE_BINDING, CORE_PROMPT_COMPILER):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "windagent_tools" not in text
        assert "windagent_intelligence" not in text
        assert "windagent_providers" not in text


def test_core_exports_phase11_models():
    import windagent_core.domain.video_production as vp

    for name in (
        "ReferenceBinding",
        "ReferenceBindingPlan",
        "ReferenceBindingIssue",
        "ReferenceBindingValidator",
        "compute_reference_binding_hash",
        "ReferenceBindingRole",
        "ReferenceBindingIssueCode",
        "PromptBlock",
        "CompiledPrompt",
        "FlowGenerationSpecification",
        "PromptCompilerIssue",
        "PromptSecurityFinding",
        "PromptBlockType",
        "PromptCompilerIssueCode",
        "compute_prompt_hash",
        "compute_request_hash",
    ):
        assert hasattr(vp, name), f"core missing export {name}"
    import windagent_core as core

    assert hasattr(core, "ReferenceBindingPlan")
    assert hasattr(core, "FlowGenerationSpecification")
    assert hasattr(core, "compute_request_hash")


def test_intelligence_exports_phase11_services():
    import windagent_intelligence.video as video

    for name in (
        "ReferenceBindingPlanner",
        "ReferenceBindingPlanReceipt",
        "PromptCompiler",
        "CompiledRequestReceipt",
        "PromptBlockBuilder",
        "PromptSanitizer",
        "ModeCompiler",
    ):
        assert hasattr(video, name), f"intelligence missing export {name}"


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
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
