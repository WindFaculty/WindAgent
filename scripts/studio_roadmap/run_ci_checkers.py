"""Run the eight Plan A/C checkers, exit non-zero on any failure.

CI entry point for the studio-roadmap-gates job. Mirrors the checker block
of produce_a7_evidence.py without writing gate evidence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHECKERS = [
    "check_architecture_imports.py",
    "check_event_taxonomy.py",
    "check_version_consistency.py",
    "check_duplicate_canonical_models.py",
    "check_video_workspace_architecture.py",
    "check_no_legacy_orchestration.py",
    "check_no_story_in_legacy_engines.py",
    "check_secret_exposure.py",
]


def main() -> int:
    fails = []
    for name in CHECKERS:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        tail = (result.stdout or result.stderr).strip().splitlines()[-1:]
        print(f"{name}: exit={result.returncode} {tail[0] if tail else ''}")
        if result.returncode != 0:
            fails.append(name)
    if fails:
        print(f"FAILED checkers: {fails}")
        return 1
    print("ALL CHECKERS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
