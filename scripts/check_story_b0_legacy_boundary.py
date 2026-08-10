"""
Static Checker: Plan B B0 legacy story service boundary.

B0 migration rule (docs/plans/studio_roadmap_01/20_PLAN_B_STORY_SCREENPLAY_PIPELINE.md):
- No moves yet; the existing story services under
  ``intelligence/windagent_intelligence/video/**`` stay public and green.
- New production callers of the soon-to-be-wrapped legacy Story services are
  FORBIDDEN outside the ``video`` package itself, the future ``story`` package,
  tests, and verification/script fixtures.

Legacy Story services captured by this guard (Plan B will wrap or replace them):

- ``windagent_intelligence.video.ideation``    (brief_expander, outliner)
- ``windagent_intelligence.video.screenplay``  (writer, narration)
- ``windagent_intelligence.video.entity_extraction``
- ``windagent_intelligence.video.style_design``
- ``windagent_intelligence.video.continuation``
- ``windagent_intelligence.video.assembly``
- ``windagent_intelligence.video.director``

Allowed consumers (allow-listed roots):

- ``intelligence/windagent_intelligence/video`` (the package itself)
- ``intelligence/windagent_intelligence/story`` (planned B package)
- ``core/windagent_core/domain/video_production`` (narrow compatibility re-exports only)
- ``tests/**`` and ``scripts/verification/**`` (fixtures and evidence harnesses)

Any other production module importing these services is a violation: a new
caller would silently lock in the old single-concept / tolerant-text behavior
that Roadmap 1 replaces. New Story behavior must live behind the frozen task
handlers in the ``story`` package.

Must return exit code 0 when no new production caller is introduced.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

LEGACY_STORY_MODULES = [
    "windagent_intelligence.video.ideation",
    "windagent_intelligence.video.screenplay",
    "windagent_intelligence.video.entity_extraction",
    "windagent_intelligence.video.style_design",
    "windagent_intelligence.video.continuation",
    "windagent_intelligence.video.assembly",
    "windagent_intelligence.video.director",
    "windagent_intelligence.video.parsing",
    "windagent_intelligence.video.prompts",
]

ALLOWED_ROOT_PARTS = ("intelligence/windagent_intelligence/video",)
ALLOWED_STORY_ROOT_PARTS = ("intelligence/windagent_intelligence/story",)

ALLOWED_EXACT_PARTS = ("core/windagent_core/domain/video_production",)

PROD_TREES = [
    "apps",
    "core",
    "execution",
    "intelligence",
    "orchestration",
    "plugins",
    "providers",
    "scripts",
    "storage",
    "tools",
]

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", "artifacts", "reports", "audit_report"}

IMPORT_LINE_RE = __import__("re").compile(r"^\s*(from|import)\b")


def _is_allowed_consumer(relative: Path) -> bool:
    parts = relative.as_posix()
    if parts.startswith("tests/") or parts.startswith("scripts/verification/"):
        return True
    for allowed in ALLOWED_ROOT_PARTS:
        if parts.startswith(allowed + "/") or parts == allowed:
            return True
    for allowed in ALLOWED_STORY_ROOT_PARTS:
        if parts.startswith(allowed + "/") or parts == allowed:
            return True
    for allowed in ALLOWED_EXACT_PARTS:
        if parts.startswith(allowed + "/") or parts == allowed:
            return True
    return False


def _references_legacy(line: str) -> str:
    for module in LEGACY_STORY_MODULES:
        if module in line:
            return module
    return ""


def check_story_b0_legacy_boundary(root_dir: Path) -> List[Tuple[Path, int, str, str]]:
    violations: List[Tuple[Path, int, str, str]] = []

    for rel_tree in PROD_TREES:
        tree = root_dir / rel_tree
        if not tree.is_dir():
            continue
        for file_path in tree.rglob("*.py"):
            if any(part in EXCLUDED_DIRS for part in file_path.parts):
                continue
            relative = file_path.relative_to(root_dir)
            if _is_allowed_consumer(relative):
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as err:  # pragma: no cover - defensive
                print(f"Error reading {file_path}: {err}", file=sys.stderr)
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not IMPORT_LINE_RE.match(line):
                    continue
                module = _references_legacy(line)
                if module:
                    violations.append((relative, line_no, module, line.strip()))

    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root (defaults to the repo containing this script)")
    args = parser.parse_args(argv)
    root_dir = args.root or Path(__file__).resolve().parent.parent
    violations = check_story_b0_legacy_boundary(root_dir)

    if violations:
        print("FAIL: new production caller of a legacy story service detected:")
        for path, line_no, module, line_content in violations:
            print(f"  {path}:{line_no} -> {module} ({line_content})")
        print(
            "B0 forbids new callers of soon-to-be-wrapped story services outside "
            "the video/story packages, tests, and verification fixtures."
        )
        return 1

    print("PASS: zero new production callers of legacy story services.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
