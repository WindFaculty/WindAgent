"""B1 architecture boundary: story content never imports infrastructure.

Plan B content models stay provider/storage/API-free: no SQL, no HTTP, no
provider ports, no orchestration, no legacy engine imports. The A envelope is
the only A-owned surface consumed (for the ArtifactType discriminator).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STORY_PKG = REPO_ROOT / "core" / "windagent_core" / "domain" / "story"

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
    "windagent_intelligence.video.director",
    "windagent_intelligence.video.screenplay.writer",
)


def _story_files():
    return [p for p in STORY_PKG.rglob("*.py") if "__pycache__" not in str(p)]


def test_story_package_has_no_forbidden_imports():
    offenders = []
    for path in _story_files():
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)} -> {marker}")
    assert not offenders, "forbidden imports in story package:\n" + "\n".join(offenders)


def test_story_package_imports_clean_in_fresh_process():
    result = subprocess.run(
        [sys.executable, "-c", "import windagent_core.domain.story"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
