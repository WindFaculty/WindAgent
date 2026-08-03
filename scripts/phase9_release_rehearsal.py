"""Run the mandatory Phase 9 migration rehearsal on a SQLite production copy."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from windagent_storage.migrations.release_rehearsal import rehearse_sqlite_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="SQLite production copy")
    parser.add_argument("--backup-root", required=True, type=Path, help="release evidence directory")
    args = parser.parse_args()
    receipt = rehearse_sqlite_release(args.database, args.backup_root)
    print(json.dumps(asdict(receipt), default=str, indent=2, sort_keys=True))
    return 0 if receipt.application_rollback_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
