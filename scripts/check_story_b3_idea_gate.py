#!/usr/bin/env python
"""Plan B B3 guard: validate committed ideation fixtures + handler surface.

Exit 0 = contract intact (corpus results match live behavior, golden set
matches live generation/evaluation, policy matrix matches, prompt manifest
current). Exit non-zero = violation. Read-only: never regenerates.

Usage: python scripts/check_story_b3_idea_gate.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCER = REPO_ROOT / "scripts" / "verification" / "produce_b3_evidence.py"

if __name__ == "__main__":
    result = subprocess.run(
        [sys.executable, str(PRODUCER), "--check"],
        cwd=REPO_ROOT,
    )
    raise SystemExit(result.returncode)
