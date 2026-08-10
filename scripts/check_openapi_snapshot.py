#!/usr/bin/env python3
"""OpenAPI snapshot boundary for Plan C /api/v3/studio.

Dumps the FastAPI OpenAPI document and compares it byte-for-byte against the
committed snapshot. The snapshot captures the current surface (V2 baseline at
C0) and grows when the V3 Studio routers land in C1; a drift means a contract
change was not reviewed and the snapshot was not refreshed deliberately.

Usage:
    python scripts/check_openapi_snapshot.py            # check (CI-local)
    python scripts/check_openapi_snapshot.py --update   # refresh snapshot
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# The V2 tombstone route registers one handler for many methods; Starlette stores
# methods in a hash-randomized set, so duplicate operation-ID suffixes order
# differently across processes. Re-invoke ourselves in a subprocess with a pinned
# hash seed so snapshots are deterministic. (os.execv would be simpler but does
# not propagate exit codes on Windows.)
if os.environ.get("PYTHONHASHSEED") is None:

    def _main() -> int:  # pragma: no cover - subprocess re-entry
        env = {**os.environ, "PYTHONHASHSEED": "0"}
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            env=env,
            cwd=Path(__file__).resolve().parent.parent,
        )
        return result.returncode

    if __name__ == "__main__":
        raise SystemExit(_main())

REPO_ROOT = Path(__file__).resolve().parent.parent
for _pkg in ["apps/api", "core", "apps/cli"]:
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "studio_contracts" / "openapi" / "openapi_snapshot.json"


def dump_openapi() -> str:
    from windagent_api.main import app  # noqa: PLC0415

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="refresh the committed snapshot")
    args = parser.parse_args()

    current = dump_openapi()

    if args.update:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(current, encoding="utf-8")
        sha = hashlib.sha256(current.encode("utf-8")).hexdigest()
        print(f"Updated OpenAPI snapshot: {SNAPSHOT_PATH}")
        print(f"SHA256: {sha}")
        return 0

    if not SNAPSHOT_PATH.exists():
        print(f"ERROR: snapshot missing at {SNAPSHOT_PATH}. Run with --update once.")
        return 1

    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if committed != current:
        sha_current = hashlib.sha256(current.encode("utf-8")).hexdigest()
        sha_committed = hashlib.sha256(committed.encode("utf-8")).hexdigest()
        print("OPENAPI DRIFT detected:")
        print(f"  committed: {sha_committed}")
        print(f"  current:   {sha_current}")
        print("Run `python scripts/check_openapi_snapshot.py --update` only after a reviewed contract change.")
        return 1

    sha = hashlib.sha256(current.encode("utf-8")).hexdigest()
    print(f"OK: OpenAPI snapshot matches ({sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
