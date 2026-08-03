"""Phase 8 - Director layer canonical isolation tests (plan 03 §4, §7).

Proves the Director layer (`intelligence/windagent_intelligence/video/director/`)
meets the Phase 8 architecture rules:
- no upstream import / sys.path mutation / subprocess (clean-room, plan §4);
- provider-neutral: imports only `windagent_core` + `windagent_intelligence`;
  never imports `windagent_tools` / `windagent_providers` / browser modules;
- the model-backed capability ships a versioned, hashed PromptSpec;
- core domain objects (DirectorialIssue / ScriptRevisionProposal) live in core
  and stay intelligence/tools-neutral;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRECTOR_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video" / "director"
CORE_DIRECTOR = ROOT / "core" / "windagent_core" / "domain" / "video_production" / "director.py"

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


def _director_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(DIRECTOR_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_director_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _director_py_files():
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"director launches/imports upstream: {hits}"


def test_director_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _director_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"director imports forbidden deps: {offenders}"


def test_director_prompt_spec_is_versioned_and_hashed():
    from windagent_intelligence.video.director.prompts import (
        DIRECTOR_PLANNING_PROMPT_V1,
    )

    parts = DIRECTOR_PLANNING_PROMPT_V1.version.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)
    assert re.fullmatch(r"[0-9a-f]{64}", DIRECTOR_PLANNING_PROMPT_V1.content_hash)
    assert DIRECTOR_PLANNING_PROMPT_V1.capability == "cinematic_planning"
    assert DIRECTOR_PLANNING_PROMPT_V1.template


def test_core_director_models_are_tools_neutral():
    text = CORE_DIRECTOR.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text
    assert "windagent_intelligence" not in text
    assert "windagent_providers" not in text


def test_core_exports_director_models():
    import windagent_core.domain.video_production as vp

    assert hasattr(vp, "DirectorialIssue")
    assert hasattr(vp, "ScriptRevisionProposal")
    assert hasattr(vp, "SceneObjective")
    assert hasattr(vp, "compute_plan_hash")
    import windagent_core as core

    assert hasattr(core, "DirectorialIssue")


def test_intelligence_exports_director_service():
    import windagent_intelligence.video as video

    assert hasattr(video, "VideoDirectorService")
    assert hasattr(video, "DirectorPlanValidator")
    assert hasattr(video, "DurationBudgetPolicy")


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
