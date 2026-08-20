#!/usr/bin/env python3
"""Architecture V3 policy checker entry point.

Wraps check_architecture_imports.py with the V3 policy config
(configs/architecture/scaffold_v3.yaml) and V3-specific report paths.

Usage:
    uv run python scripts/check_architecture_v3.py
    uv run python scripts/check_architecture_v3.py --json
    uv run python scripts/check_architecture_v3.py --root . --json

Exit codes:
    0  PASS   — zero violations under V3 policy
    1  FAIL   — one or more violations
    2  ERROR  — root or config not found
    4  ERROR  — checker internal error
"""

import sys
from pathlib import Path

# Ensure the workspace packages are importable (mirrors check_architecture_imports.py bootstrap)
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _pkg in ["core", "providers", "workflows", "apps/cli", "apps/desktop"]:
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Delegate to the canonical checker with V3 config and report paths
import check_architecture_imports  # noqa: E402  (same directory, resolved via sys.argv[0])


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    v3_config = _REPO_ROOT / "configs" / "architecture" / "scaffold_v3.yaml"
    v3_report = _REPO_ROOT / "artifacts" / "architecture_v3" / "phase_01" / "v3_boundary_report.json"
    v3_graph = _REPO_ROOT / "artifacts" / "architecture_v3" / "phase_01" / "v3_import_graph.json"

    # Inject V3 config and report paths unless the caller already specified them
    injected: list[str] = []
    argv_list = list(argv)
    if "--config" not in argv_list:
        injected += ["--config", str(v3_config)]
    if "--report" not in argv_list:
        injected += ["--report", str(v3_report)]
    if "--graph" not in argv_list:
        injected += ["--graph", str(v3_graph)]

    # V3 does not have a scaffold_v3.py yet — skip scaffold check until Phase 12
    if "--skip-scaffold-check" not in argv_list:
        injected.append("--skip-scaffold-check")

    combined = argv_list + injected
    return check_architecture_imports.main(combined)


if __name__ == "__main__":
    sys.exit(main())
