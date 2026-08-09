"""
Checks for contract drift between backend schemas and frontend generated contracts.
"""

from __future__ import annotations

import sys
from pathlib import Path

from generate_ts_contracts import CONTRACT_TS_OUTPUT_PATH, generate_contracts


def check_drift() -> bool:
    """Verify generated TypeScript contracts file matches the latest schema generator output."""
    if not CONTRACT_TS_OUTPUT_PATH.exists():
        print(f"ERROR: Contract file {CONTRACT_TS_OUTPUT_PATH} does not exist!")
        return False

    existing_content = CONTRACT_TS_OUTPUT_PATH.read_text(encoding="utf-8").strip()
    expected_content = generate_contracts().strip()

    if existing_content != expected_content:
        print("ERROR: Contract drift detected! Generated TypeScript contracts are out of sync.")
        return False

    print("SUCCESS: Contract TypeScript definitions are clean and up-to-date.")
    return True


if __name__ == "__main__":
    success = check_drift()
    sys.exit(0 if success else 1)
