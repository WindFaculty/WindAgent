"""A4 — Studio orchestration stays out of legacy engines (Plan A fence).

The sole new Story authority is ``orchestration/windagent_orchestration/studio``.
No module in that package may import the legacy ``WorkflowEngine`` /
``ProductionWorkflowEngine`` or reach into legacy orchestration internals; the
architecture checker must stay green with the A4 additions present.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

LEGACY_ENGINE_MODULES = (
    "windagent_orchestration.workflow_engine.engine",
    "windagent_orchestration.production.engine",
)
FORBIDDEN_IMPORT_FRAGMENTS = (
    "workflow_engine",
    "production.engine",
    "windagent_orchestration.production",
)


def _studio_orchestration_modules() -> list[str]:
    package_dir = Path(
        importlib.util.find_spec("windagent_orchestration.studio").origin  # type: ignore[union-attr]
    ).parent
    names = []
    for info in pkgutil.iter_modules([str(package_dir)]):
        if info.name.startswith("_"):
            continue
        names.append(f"windagent_orchestration.studio.{info.name}")
    names.append("windagent_orchestration.studio")
    return names


def test_no_story_import_in_legacy_engines_reversed():
    """Studio orchestration modules never import a legacy engine (either direction)."""
    for module_name in _studio_orchestration_modules():
        module = importlib.import_module(module_name)
        source_path = Path(module.__file__)
        source = source_path.read_text(encoding="utf-8")
        for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
            for line in source.splitlines():
                stripped = line.lstrip()
                if not (stripped.startswith("import ") or stripped.startswith("from ")):
                    continue
                if fragment in stripped:
                    pytest.fail(
                        f"{module_name} imports legacy engine fragment {fragment!r}: {stripped}"
                    )


def test_legacy_engines_do_not_import_studio():
    """Legacy engines stay blind to the Studio package (no new Story dependency)."""
    for engine in LEGACY_ENGINE_MODULES:
        module = importlib.import_module(engine)
        source = Path(module.__file__).read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.lstrip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            if "studio" in stripped and "windagent_orchestration.studio" in stripped:
                pytest.fail(f"{engine} imports the Studio orchestration package: {stripped}")


def test_architecture_checker_still_green_with_a4():
    """The live architecture checker reports zero violations with A4 present."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    if result.returncode != 0:
        pytest.fail(f"architecture checker failed:\n{result.stdout}\n{result.stderr}")
