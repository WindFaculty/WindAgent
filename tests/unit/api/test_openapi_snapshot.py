"""
C0 OpenAPI snapshot boundary. The FastAPI surface is dumped to a committed
snapshot and compared byte-for-byte; any drift fails. This guards both the V2
baseline and the additive /api/v3/studio surface that C1 introduces.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_snapshot_check() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/check_openapi_snapshot.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_openapi_snapshot_is_current():
    result = _run_snapshot_check()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: OpenAPI snapshot matches" in result.stdout


def test_openapi_snapshot_detects_drift():
    """Introducing a new route without refreshing the snapshot must fail."""
    snapshot = REPO_ROOT / "tests" / "fixtures" / "studio_contracts" / "openapi" / "openapi_snapshot.json"
    original = snapshot.read_text(encoding="utf-8")
    try:
        snapshot.write_text(original + "\n// tamper\n", encoding="utf-8")
        result = _run_snapshot_check()
        assert result.returncode == 1
        assert "OPENAPI DRIFT" in result.stdout
    finally:
        snapshot.write_text(original, encoding="utf-8")
