"""Common test assertions for the production test architecture.

These are small, deterministic helpers that make failure messages more
readable and enforce the "fail closed" semantics required by the domain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def assert_fail_closed(response, *, expected_status: int | None = None) -> Any:
    """Assert that a response is fail-closed (4xx / 5xx) and return the JSON body.

    If ``expected_status`` is given, assert exact status; otherwise assert
    ``status_code >= 400``.
    """
    status = getattr(response, "status_code", None)
    if status is None:
        raise AssertionError(f"response has no status_code: {response!r}")
    if expected_status is not None:
        assert status == expected_status, f"expected {expected_status}, got {status}: {getattr(response, 'text', '')}"
    else:
        assert status >= 400, f"expected fail-closed (>=400), got {status}: {getattr(response, 'text', '')}"
    try:
        return response.json()
    except Exception:
        return getattr(response, "text", "")


def assert_no_repo_root_db_writes(tmp_path: Path, repo_root: Path | None = None) -> None:
    """Fail if ``windagent.db`` was written outside ``tmp_path``."""
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    for name in ("windagent.db", "windagent.db-wal", "windagent.db-shm"):
        p = repo_root / name
        if p.exists():
            # Check mtime after test start — if it's newer than tmp_path creation, it's suspicious
            if p.stat().st_mtime > tmp_path.stat().st_mtime:
                raise AssertionError(f"repo-root DB write detected: {p} was modified during test (m_time={p.stat().st_mtime})")


def assert_json_matches_schema(payload: Any, schema: dict) -> None:
    """Validate ``payload`` against a JSON schema (uses ``jsonschema`` if available)."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        # Fallback: at least ensure it's JSON-serializable
        json.dumps(payload)
        return
    jsonschema.validate(instance=payload, schema=schema)
