"""E2E-tier conftest — process lifecycle, ports, worker/API startup (T1)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.support.process import (
    build_workspace_pythonpath,
    ensure_schema,
    free_port,
    wait_exit,
    wait_url,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def e2e_tmp_db(tmp_path, monkeypatch):
    """Fresh DB shared by API + Worker sub-processes."""
    db_file = tmp_path / "e2e" / "windagent.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", db_url)
    ensure_schema(db_url, root=ROOT)
    return db_url, db_file


@pytest.fixture
def e2e_env(tmp_path, monkeypatch):
    """Environment dict for subprocesses (API + Worker)."""
    db_file = tmp_path / "e2e" / "windagent.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    env = {
        **os.environ,
        "WINDAGENT_DATABASE_URL": db_url,
        "WINDAGENT_ENV": "development",
        "WINDAGENT_FAKE_RUNTIME": "1",
        "WINDAGENT_STUDIO_RUNTIME": "1",
        "PYTHONPATH": build_workspace_pythonpath(ROOT),
    }
    return env


@pytest.fixture
def free_tcp_port():
    return free_port()


@pytest.fixture
def wait_http_ready():
    return wait_url


@pytest.fixture
def wait_proc_exit():
    return wait_exit
