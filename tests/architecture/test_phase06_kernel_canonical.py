"""Phase 6 - Pre-production kernel canonical isolation tests (plan 02 §16.5).

Proves the canonical kernel (`intelligence/windagent_intelligence/video/`)
meets the upstream-retirement and provider-neutrality requirements of
plan 02 §16.1 / §16.5 / §18:
- the kernel never imports or launches the quarantined upstream
  (`third_party/videoclaw`) and never mutates `sys.path`;
- the kernel depends only on `windagent_core` (domain) + pydantic — no
  `windagent_providers` / `windagent_tools` / `windagent_workflows` imports;
- every model-backed capability uses a versioned, hashed `PromptSpec`.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KERNEL_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video"

# Real launch/import mechanisms that would execute upstream code or poison
# sys.path. These are forbidden inside the canonical kernel package.
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


def _kernel_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(KERNEL_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_kernel_never_launches_or_imports_upstream():
    """No upstream import / sys.path mutation / subprocess in the kernel."""
    hits = []
    for rel, text in _kernel_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"kernel launches/imports upstream: {hits}"


def test_kernel_dependency_roots_are_provider_neutral():
    """Kernel imports only windagent_core + windagent_intelligence (+pydantic)."""
    offenders = []
    for rel, text in _kernel_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"kernel imports forbidden deps: {offenders}"


def test_kernel_model_backed_capabilities_declare_versioned_prompts():
    """Every model-backed capability ships a semantic-version PromptSpec."""
    from windagent_intelligence.video.ideation.brief_expander import (
        BRIEF_EXPANSION_PROMPT_V1,
    )
    from windagent_intelligence.video.ideation.outliner import OUTLINE_PROMPT_V1
    from windagent_intelligence.video.screenplay.writer import SCREENPLAY_PROMPT_V1
    from windagent_intelligence.video.style_design.designer import STYLE_DESIGN_PROMPT_V1
    from windagent_intelligence.video.continuation.service import CONTINUATION_PROMPT_V1
    from windagent_intelligence.video.asset_prompts.builder import (
        CHARACTER_PORTRAIT_PROMPT_V1,
        LOCATION_PROMPT_V1,
        STYLE_PROMPT_V1,
    )

    registered = [
        BRIEF_EXPANSION_PROMPT_V1,
        OUTLINE_PROMPT_V1,
        SCREENPLAY_PROMPT_V1,
        STYLE_DESIGN_PROMPT_V1,
        CONTINUATION_PROMPT_V1,
        CHARACTER_PORTRAIT_PROMPT_V1,
        LOCATION_PROMPT_V1,
        STYLE_PROMPT_V1,
    ]
    assert registered, "no prompt specs registered"
    for spec in registered:
        # Semantic version + 64-char deterministic content hash.
        parts = spec.version.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts), spec.capability
        assert re.fullmatch(r"[0-9a-f]{64}", spec.content_hash), spec.capability
        assert spec.capability and spec.template


def test_kernel_identity_is_never_display_name_only():
    """StableIdFactory derives IDs from seed+value+seq (fixes DEF-003)."""
    from windagent_intelligence.video.ids import StableIdFactory

    factory = StableIdFactory(seed="phase6-test")
    # Two logical characters with the same display name get distinct IDs.
    a0 = factory.character_id("豆豆", 0)
    a1 = factory.character_id("豆豆", 1)
    assert a0 != a1, "duplicate display names must not merge identity"
    # Deterministic across factories with the same seed.
    assert factory.character_id("豆豆", 0) == StableIdFactory(seed="phase6-test").character_id("豆豆", 0)
    # IDs are stable across runs (fully deterministic, no uuid).
    assert re.fullmatch(r"chr_[0-9a-f]{16}", a0)


def test_real_repo_architecture_stays_clean():
    """The real workspace architecture check reports zero violations."""
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
