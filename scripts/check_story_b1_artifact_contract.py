#!/usr/bin/env python
"""Plan B B1 guard: validate committed story artifact fixtures + registry.

Exit 0 = contract intact (13/13 types, no duplicate models, golden fixtures
validate, invalid fixtures fail closed, no envelope-field leaks in content).
Exit non-zero = violation. Read-only: never regenerates fixtures.

Usage: python scripts/check_story_b1_artifact_contract.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCER = REPO_ROOT / "scripts" / "verification" / "produce_b1_evidence.py"

if __name__ == "__main__":
    result = subprocess.run(
        [sys.executable, str(PRODUCER), "--check"],
        cwd=REPO_ROOT,
    )
    raise SystemExit(result.returncode)
