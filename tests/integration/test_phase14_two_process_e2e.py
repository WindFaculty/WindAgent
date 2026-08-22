"""
Phase 14 — API/Worker two-process durable runtime E2E (V3 surface).

The V2 generic task API was retired (410 Gone). The durable API->queue->Worker
lifecycle is now exercised through the canonical V3 Studio run path:

  1. POST /api/v3/studio/series            (durable aggregate)
  2. POST /api/v3/studio/series/{id}/episodes
  3. POST /api/v3/studio/episodes/{id}/runs  (202; durable queue rows committed
     atomically with TaskSubmitted outbox records)
  4. Independent Worker process claims, executes (studio runtime), finalizes
  5. API restart; run state still queryable (durability across process restart)

Worker restart/kill durability itself is covered by the phase16 failure
injections (test_fi_restart_persistence, test_fi_worker_killed_no_split_state)
and G25 recovery tests; this file keeps the REAL two-process HTTP+Worker proof.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
API_MODULE = "windagent_api.main:app"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_url(url: str, timeout: float, expect_status: int) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code == expect_status:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    raise RuntimeError(f"{url} not ready in {timeout}s")


def _wait_exit(proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.2)
    proc.kill()
    proc.wait(timeout=5)


@pytest.mark.asyncio
async def test_api_worker_durable_runtime_two_process(tmp_path):
    # 1. Fresh empty database in a temp dir shared by both processes.
    tmp = Path(tmp_path) / "phase14_e2e"
    tmp.mkdir(parents=True, exist_ok=True)
    db_file = tmp / "windagent.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    env = {
        **os.environ,
        "WINDAGENT_DATABASE_URL": db_url,
        "WINDAGENT_ENV": "development",
        "WINDAGENT_FAKE_RUNTIME": "1",
        "WINDAGENT_STUDIO_RUNTIME": "1",
    }
    package_roots = [
        ROOT / path
        for path in (
            "apps/api", "apps/cli", "apps/worker", "core", "orchestration",
            "intelligence", "providers", "tools", "workflows", "verification",
            "context", "memory", "execution", "storage", "observability",
            "evals", "plugins", "skills",
        )
    ]
    inherited = env.get("PYTHONPATH")
    if inherited:
        package_roots.append(Path(inherited))
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in package_roots)

    python = sys.executable
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    # 2. Pre-create canonical schema so the child processes don't race on DDL.
    import sqlite3

    ddl_script = tmp / "create_tables.py"
    ddl_script.write_text(
        "import asyncio, os\n"
        "from windagent_storage.database.connection import DatabaseManager\n"
        "from windagent_storage.orm.models import BaseORM\n"
        "asyncio.run(DatabaseManager(os.environ['WINDAGENT_DATABASE_URL']).create_tables(BaseORM.metadata))\n",
        encoding="utf-8",
    )
    subprocess.run([python, str(ddl_script)], env=env, cwd=str(ROOT), check=True)

    # 3. Start API process.
    api_proc = subprocess.Popen(
        [python, "-m", "uvicorn", API_MODULE, "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        env=env, cwd=str(ROOT),
    )
    # 4. Start Worker process (independent composition root).
    worker_log = tmp / "worker.log"
    worker_proc = subprocess.Popen(
        [python, "-m", "windagent_worker"],
        env=env, cwd=str(ROOT),
        stdout=open(worker_log, "w"), stderr=subprocess.STDOUT,
    )

    try:
        _wait_url(f"{base}/health/ready", timeout=40.0, expect_status=200)

        # 5-7. Durable run submit via canonical V3 studio path.
        headers = {"X-Idempotency-Key": str(uuid.uuid4())}
        s = httpx.post(f"{base}/api/v3/studio/series", json={"title": "phase14"}, headers=headers, timeout=10.0)
        assert s.status_code in (200, 201), s.text
        series_id = s.json()["series_id"]

        e = httpx.post(
            f"{base}/api/v3/studio/series/{series_id}/episodes",
            json={"series_id": series_id, "title": "e1", "episode_number": 1},
            headers={"X-Idempotency-Key": str(uuid.uuid4())}, timeout=10.0,
        )
        assert e.status_code in (200, 201), e.text
        episode_id = e.json()["episode_id"]

        r = httpx.post(
            f"{base}/api/v3/studio/episodes/{episode_id}/runs",
            headers={"X-Idempotency-Key": str(uuid.uuid4())}, timeout=10.0,
        )
        assert r.status_code == 202, r.text
        run_id = r.json()["run_id"]

        # 8. Durable queue rows exist (task_runs written atomically with outbox).
        import asyncio
        import aiosqlite

        async with aiosqlite.connect(str(db_file)) as db:
            cur = await db.execute("SELECT COUNT(*) FROM task_runs")
            (count,) = await cur.fetchone()
        assert count >= 1, "run submit must commit durable queue rows"

        # 9. Run state queryable while running.
        g = httpx.get(f"{base}/api/v3/studio/runs/{run_id}", timeout=5.0)
        assert g.status_code == 200
        assert g.json()["run_id"] == run_id

        # 10-13. Worker claims/executes in background; run advances past initial
        # dispatch (idea.generate node leaves PENDING). Poll for node progress.
        progressed = False
        for _ in range(40):
            async with aiosqlite.connect(str(db_file)) as db:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM studio_run_nodes WHERE run_id=:r AND status != 'PENDING'",
                    {"r": run_id},
                )
                (nonpending,) = await cur.fetchone()
            if nonpending >= 1:
                progressed = True
                break
            await asyncio.sleep(0.5)
        assert progressed, "worker made no DAG progress in 20s"

        # 16-18. API restart; worker keeps running (independent processes).
        api_proc.send_signal(signal.SIGTERM)
        _wait_exit(api_proc, timeout=15.0)
        assert worker_proc.poll() is None, "Worker died when API stopped"

        api_proc = subprocess.Popen(
            [python, "-m", "uvicorn", API_MODULE, "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "warning"],
            env=env, cwd=str(ROOT),
        )
        _wait_url(f"{base}/health/ready", timeout=40.0, expect_status=200)

        # 19. Run still queryable after API restart (durability).
        again = httpx.get(f"{base}/api/v3/studio/runs/{run_id}", timeout=5.0)
        assert again.status_code == 200
        assert again.json()["run_id"] == run_id
    finally:
        for proc in (api_proc, worker_proc):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        _wait_exit(api_proc, timeout=10.0)
        _wait_exit(worker_proc, timeout=10.0)
