"""
Static Checker: No Story Dependency in Legacy Orchestration Engines.

Enforces frozen authority rule 5 from studio.contract/v0.1:
``WorkflowEngine`` and ``ProductionWorkflowEngine`` receive no new Story imports,
task types, states, or routes.

Scans the two legacy engine module trees (``workflow_engine`` and
``production`` under windagent_orchestration) for:

- imports of the canonical Studio namespaces
  (``windagent_core.contracts.studio``, ``windagent_core.domain.studio``,
  ``windagent_orchestration.studio``, ``windagent_intelligence.story``);
- any ``studio.story.*`` / ``studio.episode.*`` / ``studio.series.*`` /
  ``studio.artifact.*`` literal outside an explicit fence.

The fence: A-owned guard code inside the legacy engines names the Studio
namespace ONLY to reject Story tasks (authority rule 5). Such lines must be
wrapped in ``# STORY-FENCE-START`` / ``# STORY-FENCE-END`` comments. Docstrings
and comments are always exempt (they are documentation, not dependencies).

Must return exit code 0 when no Story reference enters either legacy engine.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

LEGACY_ENGINE_TREES = [
    "orchestration/windagent_orchestration/workflow_engine",
    "orchestration/windagent_orchestration/production",
]

FENCE_START = "# STORY-FENCE-START"
FENCE_END = "# STORY-FENCE-END"

IMPORT_PATTERNS = [
    re.compile(r"\bwindagent_core\.contracts\.studio\b"),
    re.compile(r"\bwindagent_core\.domain\.studio\b"),
    re.compile(r"\bwindagent_core\.studio\b"),
    re.compile(r"\bwindagent_orchestration\.studio\b"),
    re.compile(r"\bwindagent_intelligence\.story\b"),
]

REFERENCE_PATTERNS = [
    re.compile(r"\bstudio\.story\."),
    re.compile(r"\bstudio\.series\."),
    re.compile(r"\bstudio\.episode\."),
    re.compile(r"\bstudio\.artifact\."),
]

IMPORT_LINE_RE = re.compile(r"^\s*(from|import)\b")

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", "artifacts", "reports", "audit_report"}


def check_no_story_in_legacy_engines(root_dir: Path) -> List[Tuple[Path, int, str]]:
    violations: List[Tuple[Path, int, str]] = []

    for rel_tree in LEGACY_ENGINE_TREES:
        tree = root_dir / rel_tree
        if not tree.is_dir():
            continue
        for file_path in tree.rglob("*.py"):
            if any(part in EXCLUDED_DIRS for part in file_path.parts):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as err:  # pragma: no cover - defensive
                print(f"Error reading {file_path}: {err}", file=sys.stderr)
                continue

            in_fence = False
            in_docstring = None  # None | '"""' | "'''"
            for line_no, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()

                if stripped.startswith(FENCE_START):
                    in_fence = True
                    continue
                if stripped.startswith(FENCE_END):
                    in_fence = False
                    continue

                # Track docstring bodies; their prose is documentation, not a dependency.
                if in_docstring:
                    if in_docstring in stripped:
                        in_docstring = None
                    continue
                if stripped.startswith(('"""', "'''")):
                    marker = stripped[:3]
                    if stripped.count(marker) >= 2:
                        pass  # single-line docstring, nothing to track
                    else:
                        in_docstring = marker
                    continue

                if stripped.startswith("#"):
                    continue

                is_import_line = bool(IMPORT_LINE_RE.match(line))
                if is_import_line:
                    for pattern in IMPORT_PATTERNS:
                        if pattern.search(line):
                            violations.append((file_path, line_no, line.strip()))
                            break
                    # Imports are always a dependency edge; fence cannot excuse one.
                    continue

                if in_fence:
                    continue

                for pattern in REFERENCE_PATTERNS:
                    if pattern.search(line):
                        violations.append((file_path, line_no, line.strip()))
                        break

    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root (defaults to the repo containing this script)")
    args = parser.parse_args(argv)
    root_dir = args.root or Path(__file__).resolve().parent.parent
    violations = check_no_story_in_legacy_engines(root_dir)

    if violations:
        print("FAIL: Story dependency detected inside legacy orchestration engines:")
        for path, line_no, line_content in violations:
            print(f"  {path}:{line_no} -> {line_content}")
        print(
            "Legacy engines may serve existing paths but must reject new "
            "studio.story.* registration (authority rule 5)."
        )
        return 1

    print("PASS: Zero Story imports/task/event references inside legacy orchestration engines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
