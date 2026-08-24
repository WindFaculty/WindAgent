"""
Phase 14 — API/Worker two-process durable runtime E2E (V3 surface).

The V2 generic task API was retired (410 Gone). The durable API->queue->Worker
lifecycle is now exercised through the canonical V3 Studio run path:

  1. POST /api/v3/studio/series            (durable aggregate)
  2. POST /api/v3/studio/series/{id}/episodes   (with a valid creative brief)
  3. POST /api/v3/providers (+ sync-models)     (real SQL provider catalog)
  4. POST /api/v3/studio/episodes/{id}/runs  (202; durable queue rows committed
     atomically with TaskSubmitted outbox records; the P0.4.1 START_BLOCKED
     preflight must PASS first — including the worker's fresh runtime
     attestation, so submission waits for the Worker heartbeat)
  5. Independent Worker process claims, executes (studio runtime over the
     RouteLockedModelPort against a local deterministic provider stand-in),
     finalizes
  6. API restart; run state still queryable (durability across process restart)

Worker restart/kill durability itself is covered by the phase16 failure
injections (test_fi_restart_persistence, test_fi_worker_killed_no_split_state)
and G25 recovery tests; this file keeps the REAL two-process HTTP+Worker proof.

Only the EXTERNAL provider HTTP transport is controlled (a local deterministic
server returning golden fixtures — same policy as the vertical lifecycle
contract). Provider catalog SQL persistence, credentials encryption, routing,
the P0.4.1 preflight, worker attestation, queue claims and story handlers are
all REAL.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from tests.support.waiting import async_deterministic_sleep, deterministic_sleep

# Golden story fixtures (deterministic content per schema title).
from produce_b3_evidence import GOLDEN_GENERATION_RESPONSE
from produce_b4_evidence import GOLDEN_BIBLE_RESPONSE
from produce_b5_evidence import GOLDEN_BEAT_SHEET, GOLDEN_EPISODE_OUTLINE
from produce_b6_evidence import GOLDEN_SCREENPLAY_DRAFT
from produce_b7_evidence import GOLDEN_REVIEW_CLEAN

ROOT = Path(__file__).resolve().parents[3]
API_MODULE = "windagent_api.main:app"
CANONICAL_MODEL = "story-e2e-v1"
PROVIDER_ID = "e2e-story-provider"

_GOLDEN_BY_SCHEMA_TITLE = {
    "IdeaGenerationOutput": GOLDEN_GENERATION_RESPONSE,
    "BibleGenerationOutput": GOLDEN_BIBLE_RESPONSE,
    "BeatGenerationOutput": GOLDEN_BEAT_SHEET,
    "OutlineGenerationOutput": GOLDEN_EPISODE_OUTLINE,
    "ScreenplayGenerationOutput": GOLDEN_SCREENPLAY_DRAFT,
    "ReviewOutput": GOLDEN_REVIEW_CLEAN,
    "ScreenplayRevisionOutput": {**GOLDEN_SCREENPLAY_DRAFT, "draft_id": "draft_e2e_r2"},
}


class _DeterministicProviderHandler(BaseHTTPRequestHandler):
    """Local stand-in for the EXTERNAL provider backend only.

    Serves GET .../models for catalog discovery and POST .../chat/completions
    with the golden fixture matching the requested structured-output schema.
    """

    def log_message(self, *_args) -> None:  # silence stderr noise
        return

    def _send(self, status_code: int, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": CANONICAL_MODEL}]}).encode()
            self._send(200, body)
            return
        self._send(404, json.dumps({"error": {"message": f"no route: {self.path}"}}).encode())

    def do_POST(self) -> None:
        if not self.path.endswith("/chat/completions"):
            self._send(404, json.dumps({"error": {"message": f"no route: {self.path}"}}).encode())
            return
        length = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        schema_title = str(
            ((payload.get("response_format") or {}).get("json_schema") or {})
            .get("schema", {})
            .get("title", "")
        )
        fixture = _GOLDEN_BY_SCHEMA_TITLE.get(schema_title)
        if fixture is None:
            message = f"unexpected structured-output schema title: {schema_title!r}"
            self._send(400, json.dumps({"error": {"message": message}}).encode())
            return
        body = {
            "id": "chatcmpl-e2e-deterministic",
            "model": CANONICAL_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(fixture, ensure_ascii=False),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 17, "completion_tokens": 31},
        }
        self._send(200, json.dumps(body).encode())


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
        deterministic_sleep(0.3)
    raise RuntimeError(f"{url} not ready in {timeout}s")


def _wait_exit(proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        deterministic_sleep(0.2)
    proc.kill()
    proc.wait(timeout=5)


@pytest.mark.asyncio
async def test_api_worker_durable_runtime_two_process(tmp_path):
    # 0. Local deterministic stand-in for the external provider backend.
    provider_srv = ThreadingHTTPServer(("127.0.0.1", 0), _DeterministicProviderHandler)
    provider_srv.daemon_threads = True
    threading.Thread(target=provider_srv.serve_forever, daemon=True).start()
    provider_base_url = f"http://127.0.0.1:{provider_srv.server_address[1]}/v1"

    # 1. Fresh empty database in a temp dir shared by both processes.
    tmp = Path(tmp_path) / "phase14_e2e"
    tmp.mkdir(parents=True, exist_ok=True)
    db_file = tmp / "windagent.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    env = {
        **os.environ,
        "WINDAGENT_DATABASE_URL": db_url,
        "WINDAGENT_ENV": "development",
        # Full studio composition on the Worker: no fake runtime anywhere, so
        # its durable attestation is story-eligible. The canonical model id is
        # injected into the Worker env only AFTER catalog discovery below,
        # because the durable registry assigns its own canonical id.
        "WINDAGENT_STUDIO_RUNTIME": "1",
        "WINDAGENT_STUDIO_MODEL_ROUTE": "1",
        # Deterministic encryption key shared by API (encrypt at seed time) and
        # Worker (decrypt at execution time) — same pattern as the vertical
        # lifecycle contract.
        "WINDAGENT_ENCRYPTION_KEY": base64.b64encode(b"v" * 32).decode(),
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

    # 2. Pre-create the canonical schema via Alembic so the child processes
    #    don't race on DDL and /health/ready's required schema_migration
    #    check (alembic_version at the canonical head) passes.
    schema_script = tmp / "create_schema.py"
    schema_script.write_text(
        "import os\n"
        "from windagent_storage.migrations.runner import alembic_upgrade_head\n"
        "alembic_upgrade_head(os.environ['WINDAGENT_DATABASE_URL'])\n",
        encoding="utf-8",
    )
    subprocess.run([python, str(schema_script)], env=env, cwd=str(ROOT), check=True)

    # 3. Start API process.
    api_proc = subprocess.Popen(
        [python, "-m", "uvicorn", API_MODULE, "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        env=env, cwd=str(ROOT),
    )

    worker_proc = None
    worker_log = tmp / "worker.log"

    try:
        _wait_url(f"{base}/health/ready", timeout=40.0, expect_status=200)

        # 4. Seed a real provider row through the public V3 API BEFORE starting
        #    the Worker: its route composition snapshots enabled endpoint
        #    bindings once at boot, so the catalog row must already exist. The
        #    row, endpoint and encrypted credential are real SQL state that
        #    both the API preflight and the Worker's route bindings consume;
        #     only its base_url points at the local deterministic backend.
        p = httpx.post(
            f"{base}/api/v3/providers",
            json={
                "id": PROVIDER_ID,
                "name": "E2E Story Provider",
                "type": "cloud",
                "base_url": provider_base_url,
                "protocol_mode": "openai",
                "api_key": "synthetic-e2e-key",
                "endpoint_id": "ep-e2e-story",
            },
            timeout=10.0,
        )
        assert p.status_code in (200, 201), p.text
        sm = httpx.post(f"{base}/api/v3/providers/{PROVIDER_ID}/sync-models", timeout=15.0)
        assert sm.status_code in (200, 201), sm.text
        assert CANONICAL_MODEL in (sm.json().get("added") or []), sm.text

        # 4c. Resolve the DURABLE canonical model id from the registry itself
        #     (the vertical lifecycle contract does the same: never guess the
        #     id the sync pipeline assigned).
        catalog = httpx.get(f"{base}/api/v3/models", timeout=10.0).json()
        bound = [
            m for m in catalog
            if any(b.get("endpoint_id") == "ep-e2e-story" for b in m.get("bindings", []))
        ]
        assert len(bound) == 1, f"expected exactly one bound model, got {catalog!r}"
        canonical_id = bound[0]["id"]

        # 5. Start Worker process (independent composition root) AFTER the
        #    provider catalog exists so its durable route bindings resolve.
        worker_env = {**env, "WINDAGENT_STUDIO_CANONICAL_MODEL": canonical_id}
        worker_proc = subprocess.Popen(
            [python, "-m", "windagent_worker"],
            env=worker_env, cwd=str(ROOT),
            stdout=open(worker_log, "w"), stderr=subprocess.STDOUT,
        )

        # 5b-6. Durable run submit via canonical V3 studio path.
        headers = {"X-Idempotency-Key": str(uuid.uuid4())}
        s = httpx.post(f"{base}/api/v3/studio/series", json={"title": "phase14"}, headers=headers, timeout=10.0)
        assert s.status_code in (200, 201), s.text
        series_id = s.json()["series_id"]

        brief = {
            "brief_id": "brf_phase14",
            "title": "phase14 episode",
            "genre": "fantasy",
            "logline": "A worker crosses the durable queue",
            "tone": "warm",
            "audience": "kids",
            "language": "vi",
            "theme": "persistence",
            "target_duration_seconds": 240,
            "aspect_ratio": "16:9",
        }
        e = httpx.post(
            f"{base}/api/v3/studio/series/{series_id}/episodes",
            json={
                "series_id": series_id, "title": "e1", "episode_number": 1,
                "metadata": {"creative_brief": brief},
            },
            headers={"X-Idempotency-Key": str(uuid.uuid4())}, timeout=10.0,
        )
        assert e.status_code in (200, 201), e.text
        episode_id = e.json()["episode_id"]

        # 7. Start gate (P0.4.1): submit once the Worker's fresh runtime
        #    attestation lands in the heartbeat table. A 409 START_BLOCKED
        #    before that is honest gating, not an error — retry until ready.
        run_id = None
        last_blocked = ""
        deadline = time.time() + 45.0
        while time.time() < deadline:
            r = httpx.post(
                f"{base}/api/v3/studio/episodes/{episode_id}/runs",
                headers={"X-Idempotency-Key": str(uuid.uuid4())}, timeout=10.0,
            )
            if r.status_code == 202:
                run_id = r.json()["run_id"]
                break
            if r.status_code == 409:
                last_blocked = r.text
                await async_deterministic_sleep(1.0)
                continue
            assert False, f"unexpected run submit response: {r.status_code} {r.text}"
        assert run_id, f"run never started within 45s; last reasons: {last_blocked}"

        # 8. Durable queue rows exist (task_runs written atomically with outbox).
        import aiosqlite

        async with aiosqlite.connect(str(db_file)) as db:
            cur = await db.execute("SELECT COUNT(*) FROM task_runs")
            (count,) = await cur.fetchone()
        assert count >= 1, "run submit must commit durable queue rows"

        # 9. Run state queryable while running.
        g = httpx.get(f"{base}/api/v3/studio/runs/{run_id}", timeout=5.0)
        assert g.status_code == 200
        assert g.json()["run_id"] == run_id

        # 10-13. Worker claims/executes in background over the real model
        # route; poll for DAG node progress past initial dispatch.
        progressed = False
        for _ in range(60):
            async with aiosqlite.connect(str(db_file)) as db:
                cur = await db.execute(
                    "SELECT COUNT(*) FROM studio_run_nodes WHERE run_id=:r AND status != 'PENDING'",
                    {"r": run_id},
                )
                (nonpending,) = await cur.fetchone()
            if nonpending >= 1:
                progressed = True
                break
            await async_deterministic_sleep(0.5)
        assert progressed, (
            "worker made no DAG progress in 30s; "
            f"worker log tail:\n{Path(worker_log).read_text(errors='replace')[-1500:]}"
        )

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
            if proc is not None and proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        _wait_exit(api_proc, timeout=10.0)
        if worker_proc is not None:
            _wait_exit(worker_proc, timeout=10.0)
        provider_srv.shutdown()
