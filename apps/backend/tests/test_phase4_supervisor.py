"""Phase 4 gate (ban_ke_hoach §7): one orchestrator spawns >=3 sub-agents.

Uses in-process fake Hermes server (ASGITransport). Verifies:
  - supervisor persists one orchestrator instance per conversation
  - spawn_subagent creates independent AgentInstance + AgentRun each
  - >=3 independent runs created
  - stop_subagent cancels run + instance in DB
  - reattach repopulates in-memory maps from DB
"""
from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from db.database import Database
from db.models import AgentRunORM, AgentORM
from services.hermes.session_bridge import HermesSessionBridge
from services.hermes.supervisor import HermesSupervisor
from services.hermes.config import HermesConfig
from services.hermes.api_client import HermesApiClient
from tests.fake_hermes_server import fake_app


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite+aiosqlite:///{tmp_path/'phase4.db'}?timeout=30"


class FakeBus:
    def __init__(self):
        self.count = 0

    async def publish(self, *a, **k):
        self.count += 1
        return 0


class FakeHermesClient(HermesApiClient):
    """Route the real client methods at the in-process fake app."""

    def __init__(self, cfg, transport):
        super().__init__(cfg)
        self._http = httpx.AsyncClient(transport=transport)

    async def close(self):
        await self._http.aclose()

    async def start_run(self, **kw):
        url = f"{self.config.base_url}/v1/runs"
        payload = {"input": kw.get("user_message")}
        if kw.get("session_id"):
            payload["session_id"] = kw["session_id"]
        if kw.get("instructions"):
            payload["instructions"] = kw["instructions"]
        if kw.get("model"):
            payload["model"] = kw["model"]
        resp = await self._http.post(url, json=payload, headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()

    async def stop_run(self, run_id):
        url = f"{self.config.base_url}/v1/runs/{run_id}/stop"
        resp = await self._http.post(url, json={}, headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()

    async def create_hermes_session(self, session_id):
        url = f"{self.config.base_url}/api/sessions"
        resp = await self._http.post(url, json={"session_id": session_id}, headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()

    async def stream_run_events(self, run_id):
        url = f"{self.config.base_url}/v1/runs/{run_id}/events"
        async with self._http.stream("GET", url, headers=self._get_headers()) as response:
            response.raise_for_status()
            current_event = None
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                    try:
                        data = json.loads(data_str)
                        if current_event and "event" not in data:
                            data["event"] = current_event
                        yield data
                    except Exception:
                        pass
                    current_event = None


async def _seed_agents(db):
    async with db.session() as s:
        for aid, role in [
            ("orch", "Orchestrator"),
            ("coderA", "Coder"),
            ("coderB", "Coder"),
            ("coderC", "Coder"),
        ]:
            s.add(AgentORM(
                id=aid, name=aid, runtime_type="hermes",
                hermes_profile="default", router_role=role, status="offline",
            ))


async def test_supervisor_spawns_three_subagents(db_url):
    db = Database(db_url)
    await db.init_models()
    await _seed_agents(db)

    cfg = HermesConfig(
        enabled=True, base_url="http://test", api_key=None,
        auto_start=False, request_timeout_s=5, connect_timeout_s=2,
    )
    transport = httpx.ASGITransport(app=fake_app)
    client = FakeHermesClient(cfg, transport)
    bus = FakeBus()
    bridge = HermesSessionBridge(db, client, bus)
    sup = HermesSupervisor(db, bridge)

    orch_sid = await sup.ensure_orchestrator("conv1", "orch")
    assert orch_sid.startswith("sess_")

    results = []
    for aid in ["coderA", "coderB", "coderC"]:
        r = await sup.spawn_subagent(
            conversation_id="conv1", parent_task_id="pt1", task_id=aid,
            agent_id=aid, prompt=f"do {aid}", agent_type="coder",
        )
        results.append(r)
        assert r["run_id"].startswith("run_")

    # 3 independent runs.
    assert len({r["run_id"] for r in results}) == 3

    # Persisted: 1 orchestrator + 3 sub instances = 4, plus 3 runs.
    insts = await sup.list_instances("conv1")
    assert len(insts) == 4
    async with db.session() as s:
        runs = (await s.execute(select(AgentRunORM))).scalars().all()
        assert len(runs) == 3
        assert all(r.hermes_run_id for r in runs)

    # Stop one sub-agent -> run + instance cancelled.
    target = results[0]["run_id"]
    ok = await sup.stop_subagent(target)
    assert ok
    async with db.session() as s:
        run = (await s.execute(
            select(AgentRunORM).where(AgentRunORM.hermes_run_id == target)
        )).scalar_one()
        assert run.status == "cancelled"

    # Reattach from DB (Phase 7 prep).
    sup2 = HermesSupervisor(db, bridge)
    await sup2.reattach("conv1")
    assert "conv1" in sup2._orchestrators

    await client.close()
    await db.dispose()
