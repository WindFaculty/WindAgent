"""Tests for the no-Story-in-legacy-engines architecture fence (Plan A A0).

Authority rule 5 of studio.contract/v0.1: ``WorkflowEngine`` and
``ProductionWorkflowEngine`` receive no new Story imports, task types, states,
or routes. This checker is the regression gate for that rule.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_no_story_in_legacy_engines.py"

LEGACY_TREE = ROOT / "orchestration" / "windagent_orchestration" / "workflow_engine"

FORBIDDEN_SAMPLES = [
    "from windagent_core.contracts.studio import StudioTaskEnvelope",
    "from windagent_core.domain.studio.episode import Episode",
    "import windagent_orchestration.studio",
    "from windagent_intelligence.story.handlers import handler",
    'task_type = "studio.story.idea.generate"',
    'event_type = "studio.episode.ready_for_production"',
]


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


def test_checker_flags_story_import(tmp_path) -> None:
    rel_tree = "orchestration/windagent_orchestration/workflow_engine"
    tree = tmp_path / rel_tree
    tree.mkdir(parents=True)
    engine = tree / "engine.py"
    engine.write_text(
        "from windagent_core.contracts.studio import StudioTaskEnvelope\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode != 0
    assert "windagent_core.contracts.studio" in result.stdout
    assert "engine.py" in result.stdout


def test_checker_flags_task_type_registration(tmp_path) -> None:
    rel_tree = "orchestration/windagent_orchestration/production"
    tree = tmp_path / rel_tree
    tree.mkdir(parents=True)
    engine = tree / "engine.py"
    engine.write_text(
        'task_registry.register("studio.story.review", handler)\n',
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode != 0
    assert "studio.story.review" in result.stdout


def test_checker_ignores_engine_tree_absence(tmp_path) -> None:
    result = run_checker(tmp_path)
    assert result.returncode == 0


def test_checker_exempts_fenced_guard_code(tmp_path) -> None:
    rel_tree = "orchestration/windagent_orchestration/workflow_engine"
    tree = tmp_path / rel_tree
    tree.mkdir(parents=True)
    engine = tree / "engine.py"
    engine.write_text(
        "# STORY-FENCE-START\n"
        'STORY_NAMESPACE_PREFIXES = ("studio.", "studio.story.")\n'
        'if "studio.story." in task_type:\n'
        "    raise ValueError(\"Story task rejected\")\n"
        "# STORY-FENCE-END\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_flags_story_reference_outside_fence(tmp_path) -> None:
    rel_tree = "orchestration/windagent_orchestration/workflow_engine"
    tree = tmp_path / rel_tree
    tree.mkdir(parents=True)
    engine = tree / "engine.py"
    engine.write_text(
        'task_type = "studio.story.idea.generate"\n',
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode != 0
    assert "studio.story.idea.generate" in result.stdout


def test_checker_exempts_docstring_prose(tmp_path) -> None:
    rel_tree = "orchestration/windagent_orchestration/workflow_engine"
    tree = tmp_path / rel_tree
    tree.mkdir(parents=True)
    engine = tree / "engine.py"
    engine.write_text(
        '"""Legacy engine. It rejects studio.story.* tasks per authority rule 5."""\n'
        "# a comment mentioning studio.story. is documentation\n"
        "def run():\n"
        "    return None\n",
        encoding="utf-8",
    )
    result = run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
