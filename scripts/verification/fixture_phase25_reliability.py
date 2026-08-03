#!/usr/bin/env python3
"""
Phase 25 fixture writer (plan 08 §6.2: fixture_* scripts separate from verify_*).

Writes deterministic test fixtures for the Phase 25 verifier CLI contract into
a TEMP directory only — never under artifacts/video_production.

Usage:
  python fixture_phase25_reliability.py --out-dir <tempdir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verification.verify_phase25_reliability import write_fixtures  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 25 verifier fixture writer")
    parser.add_argument("--out-dir", required=True, help="temp directory to write fixtures into")
    args = parser.parse_args()
    out = Path(args.out_dir).resolve()
    prod_root = (ROOT / "artifacts" / "video_production").resolve()
    try:
        out.relative_to(prod_root)
        parser.error(f"--out-dir refuses production artifacts path: {out}")
    except ValueError:
        pass
    write_fixtures(out)
    print(f"Phase 25 fixtures written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
