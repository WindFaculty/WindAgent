#!/usr/bin/env python3
"""
Fixture-only writer for Phase 22 (remediation plan 08, §6.2).

Separated from verify_phase22_postproduction.py: writes CONTRACT fixtures ONLY
under a caller-supplied temporary test directory; refuses production artifacts.

Usage:
  python fixture_phase22_postproduction.py --out-dir <tempdir>
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification.verify_phase22_postproduction import write_fixtures  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    if "--out-dir" not in argv:
        print("usage: fixture_phase22_postproduction.py --out-dir <tempdir>")
        return 2
    out = Path(argv[argv.index("--out-dir") + 1]).resolve()
    prod = Path("artifacts/video_production").resolve()
    try:
        out.relative_to(prod)
    except ValueError:
        pass
    else:
        print(f"error: fixture writer refuses production artifacts path: {out}")
        return 2
    write_fixtures(out)
    print(f"CONTRACT_TESTED fixtures written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
