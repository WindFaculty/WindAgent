#!/usr/bin/env python
"""Plan B B2 guard: validate committed prompt catalog fixtures + boundary.

Exit 0 = contract intact (manifest matches code, schema checksums match,
corpus results match live behavior, no tolerant free-text parsing on
canonical paths). Exit non-zero = violation. Read-only: never regenerates.

Usage: python scripts/check_story_b2_prompt_catalog.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCER = REPO_ROOT / "scripts" / "verification" / "produce_b2_evidence.py"

if __name__ == "__main__":
    result = subprocess.run(
        [sys.executable, str(PRODUCER), "--check"],
        cwd=REPO_ROOT,
    )
    raise SystemExit(result.returncode)
