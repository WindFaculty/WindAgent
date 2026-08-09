"""B2 architecture boundary: story model boundary stays provider/storage-free.

The story intelligence package (prompt catalog + structured invocation) may
consume ONLY the frozen provider-neutral seam (``video.ports`` /
``video.prompts`` PromptSpec primitive) and the extracted legacy PromptSpec
constants (the catalog registers them by reference so template/hash equality
with the live pipeline is enforced, not duplicated). It must never import
tolerant free-text parsers, the director, infrastructure, or A's runtime
contracts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STORY_INTEL_PKG = REPO_ROOT / "intelligence" / "windagent_intelligence" / "story"

FORBIDDEN_IMPORT_MARKERS = (
    "sqlalchemy",
    "fastapi",
    "flask",
    "aiohttp",
    "httpx",
    "requests",
    "storage",
    "orchestration",
    "worker",
    "queue",
    "providers",
    "contracts.studio",
    "video.parsing",  # tolerant free-text parsers: never canonical authority
    "video.director",
)

#: Legacy prompt-source modules the catalog MAY import (the extraction seam):
#: their PromptSpec constants are registered by reference so template/hash
#: equality with the live pipeline is enforced, not duplicated.
ALLOWED_LEGACY_PROMPT_SOURCES = (
    "video.ideation.brief_expander",
    "video.ideation.outliner",
    "video.screenplay.writer",
    "video.continuation.service",
)


def _story_files():
    return [p for p in STORY_INTEL_PKG.rglob("*.py") if "__pycache__" not in str(p)]


def _import_lines(path: Path):
    """Only actual import statements (docstrings may mention markers)."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]


def test_story_intel_package_has_no_forbidden_imports():
    offenders = []
    for path in _story_files():
        for line in _import_lines(path):
            for marker in FORBIDDEN_IMPORT_MARKERS:
                if marker in line:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} -> {marker}")
    assert not offenders, "forbidden imports in story intelligence package:\n" + "\n".join(
        offenders
    )


def test_legacy_video_imports_only_from_allowed_prompt_sources():
    """The only legacy video modules story code may touch are prompt sources."""
    for path in _story_files():
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "windagent_intelligence.video." not in line:
                continue
            if any(src in line for src in ALLOWED_LEGACY_PROMPT_SOURCES):
                continue
            if "windagent_intelligence.video.ports" in line or "windagent_intelligence.video.prompts" in line:
                continue  # the frozen provider-neutral seam + PromptSpec primitive
            raise AssertionError(
                f"{path.relative_to(REPO_ROOT)} imports unallowed legacy module: {line.strip()}"
            )


def test_story_intel_package_imports_clean_in_fresh_process():
    result = subprocess.run(
        [sys.executable, "-c", "import windagent_intelligence.story"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_story_intel_never_imports_tolerant_parsers():
    """Gate half: no canonical artifact path uses tolerant free-text parsing."""
    from scripts.verification.produce_b2_evidence import tolerant_parsing_violations

    assert tolerant_parsing_violations() == []
