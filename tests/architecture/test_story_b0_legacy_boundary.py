"""Tests for the Plan B B0 legacy story service boundary checker.

B0 migration guard: no MOVES yet, but new PRODUCTION callers of the legacy
Story services (ideation/screenplay/entity_extraction/style_design/
continuation/assembly/director) are forbidden outside the ``video`` package,
the future ``story`` package, core compatibility re-exports, tests, and
verification fixtures.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_story_b0_legacy_boundary.py"


def run_checker(root: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_checker_passes_clean_repository() -> None:
    result = run_checker()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_checker_flags_foreign_production_caller(tmp_path) -> None:
    # A fake production module outside the allowed roots importing a legacy
    # story service must be flagged.
    tree = tmp_path / "providers" / "windagent_providers" / "x"
    tree.mkdir(parents=True)
    module = tree / "rogue.py"
    module.write_text(
        "from windagent_intelligence.video.ideation.brief_expander import CreativeBriefExpander\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode != 0
    assert "video.ideation" in result.stdout
    assert "rogue.py" in result.stdout


def test_checker_allows_video_package_internal_reuse(tmp_path) -> None:
    tree = tmp_path / "intelligence" / "windagent_intelligence" / "video" / "assembly"
    tree.mkdir(parents=True)
    module = tree / "assembler.py"
    module.write_text(
        "from windagent_intelligence.video.asset_prompts.builder import AssetPromptSpecBuilder\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_allows_future_story_package_wrappers(tmp_path) -> None:
    tree = tmp_path / "intelligence" / "windagent_intelligence" / "story" / "ideation"
    tree.mkdir(parents=True)
    module = tree / "wrappers.py"
    module.write_text(
        "from windagent_intelligence.video.ideation.brief_expander import CreativeBriefExpander\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_ignores_tests_and_verification(tmp_path) -> None:
    for rel in ("tests/unit/x.py", "scripts/verification/historical/x.py"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True)
        path.write_text(
            "from windagent_intelligence.video.screenplay.writer import ScreenplayWriter\n",
            encoding="utf-8",
        )
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_ignores_docstring_prose(tmp_path) -> None:
    tree = tmp_path / "providers" / "windagent_providers" / "y"
    tree.mkdir(parents=True)
    module = tree / "doc.py"
    module.write_text(
        '"""Wraps windagent_intelligence.video.director per Plan B B0."""\n'
        "def run():\n"
        "    return None\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
