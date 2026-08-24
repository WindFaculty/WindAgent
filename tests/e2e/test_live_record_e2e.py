"""Live Record end-to-end — Gemini director loop over the real V3 API
(ban_ke_hoach_v1.md Section 18, Phase F).

Topology under test (all in-process, hermetic SQLite):

    FakeGeminiLiveServer ──WebSocket──► DirectorLoopHarness (TS stand-in)
                                              │ HTTP (TestClient)
                                              ▼
                              windagent_api full app + live_record routers
                                              │
                                              ▼
                            frozen LiveExecutionPlan (episode ep-cb-001)

The fake server speaks exactly the BidiGenerateContent wire shapes the TS
client consumes: ``setup``/``setupComplete``, ``sessionResumptionUpdate``,
``toolCall.functionCalls[]`` and accepts ``toolResponse.functionResponses[]``.
The harness plays the desktop side of the TS LiveDirectorClient: it validates
every call through the domain gate (``validate_tool_call``), resolves dispatch
tickets from the frozen plan and reports hash-verified results — a mini
3-scene episode, asserted on:

- zero unapproved actions ever reach the API or the timeline,
- CODE_PLAYBACK hashes verified against the frozen plan,
- every command/browser parameter originates from the plan's own bundles,
- the timeline is complete with monotonic per-take seq,
- Episode → Plan → Take lineage is intact.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading

import pytest
from fastapi.testclient import TestClient
from websockets.asyncio.server import serve as ws_serve
from websockets.sync.client import connect as ws_connect

from windagent_core.domain.live_record.executor import (
    ALLOWED_DIRECTOR_TOOLS,
    DirectorToolCall,
    validate_tool_call,
)
from tests.support.waiting import deterministic_sleep

API = "/api/v3/live-record"
IDEM = lambda: f"idem_e2e_{uuid_hex()}"  # noqa: E731


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures & plan content — mini episode, 3 scenes
# ---------------------------------------------------------------------------

ORIGINAL_FILE_CONTENT = "# placeholder — operator prepared this file\n"

PAYLOAD_CONFIG = 'WINDAGENT_MODE=live_record\nDIRECTOR_ROLE=LIVE_DIRECTOR\n'
PAYLOAD_DEPS = "pip install -r requirements.txt\n"


@pytest.fixture
def api(monkeypatch, tmp_path) -> TestClient:
    """Full app with demo seed (ep-cb-001 @ rev-cb-001-v3) on a fresh DB."""
    from tests.support.api import isolated_api_client

    yield from isolated_api_client(monkeypatch, tmp_path, profile="demo")


def _plan_request() -> dict:
    return {
        "episode_id": "ep-cb-001",
        "episode_revision_id": "rev-cb-001-v3",
        "scenes": [
            {
                "scene_id": "sc_1",
                "index": 0,
                "title": "Prepare workspace",
                "cues": [
                    {
                        "cue_id": "cue_1",
                        "scene_id": "sc_1",
                        "index": 0,
                        "expected_state": {"state_id": "st_workspace_ready"},
                    }
                ],
                "action_ids": ["act_write_config"],
            },
            {
                "scene_id": "sc_2",
                "index": 1,
                "title": "Install dependencies",
                "cues": [
                    {
                        "cue_id": "cue_2",
                        "scene_id": "sc_2",
                        "index": 0,
                        "expected_state": {"state_id": "st_deps_installed"},
                    }
                ],
                "action_ids": ["act_install_deps"],
            },
            {
                "scene_id": "sc_3",
                "index": 2,
                "title": "Open reference docs",
                "cues": [
                    {
                        "cue_id": "cue_3",
                        "scene_id": "sc_3",
                        "index": 0,
                        "expected_state": {"state_id": "st_docs_open"},
                    }
                ],
                "action_ids": ["act_open_docs"],
            },
        ],
        "actions": [
            {
                "action_id": "act_write_config",
                "type": "CODE_PLAYBACK",
                "scene_id": "sc_1",
                "cue_id": "cue_1",
                "payload_ref": "artifact://bundles/act_write_config.env",
                "target_file": "config/app.env",
                "before_hash": sha256_text(ORIGINAL_FILE_CONTENT),
                "after_hash": sha256_text(PAYLOAD_CONFIG),
                "typing_mode": "TYPE",
                "chars_per_second": 22,
                "expected_after": {"state_id": "st_workspace_ready"},
                "idempotency_key": "idem_act_write_config",
            },
            {
                "action_id": "act_install_deps",
                "type": "CODE_PLAYBACK",
                "scene_id": "sc_2",
                "cue_id": "cue_2",
                "payload_ref": "artifact://bundles/act_install_deps.txt",
                "target_file": "scripts/install.sh",
                "before_hash": sha256_text(ORIGINAL_FILE_CONTENT),
                "after_hash": sha256_text(PAYLOAD_DEPS),
                "typing_mode": "PASTE",
                "chars_per_second": 22,
                "expected_after": {"state_id": "st_deps_installed"},
                "idempotency_key": "idem_act_install_deps",
            },
            {
                "action_id": "act_open_docs",
                "type": "BROWSER_NAVIGATION",
                "scene_id": "sc_3",
                "cue_id": "cue_3",
                "payload_ref": "artifact://bundles/act_open_docs.ref",
                "browser_semantic_target": "Gemini Live API documentation",
                "expected_after": {
                    "state_id": "st_docs_open",
                    "url_contains": "ai.google.dev",
                },
                "idempotency_key": "idem_act_open_docs",
            },
        ],
        "payload_bundles": {
            "act_write_config": PAYLOAD_CONFIG,
            "act_install_deps": PAYLOAD_DEPS,
            "act_open_docs": "artifact://docs/gemini_live",
        },
    }


def _freeze_and_take(api: TestClient):
    """Create → prepare → validate → freeze → open take. Returns both views."""
    created = api.post(
        f"{API}/plans", headers={"X-Idempotency-Key": IDEM()}, json=_plan_request()
    )
    assert created.status_code == 201, created.text
    plan = created.json()

    for transition in ("prepare", "validate", "freeze"):
        step = api.post(
            f"{API}/plans/{plan['plan_id']}/{transition}",
            headers={"X-Idempotency-Key": IDEM()},
        )
        assert step.status_code == 200, step.text
    frozen = step.json()

    take = api.post(
        f"{API}/plans/{plan['plan_id']}/takes",
        headers={"X-Idempotency-Key": IDEM()},
    )
    assert take.status_code == 201, take.text
    return frozen, take.json()


# ---------------------------------------------------------------------------
# FakeGeminiLiveServer — in-process BidiGenerateContent double
# ---------------------------------------------------------------------------


class FakeGeminiLiveServer:
    """Thread-hosted WebSocket server emitting real protocol frames.

    Speaks only what the frozen contract allows: setup handshake,
    sessionResumptionUpdate handles, toolCall pushes; collects whatever the
    director answers with so the test can audit the toolResponse stream.
    """

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.setup_received: dict | None = None
        self.handles_issued: list[str] = []
        self.port: int = 0
        self._ready = threading.Event()
        self._connection = None
        self._stop_evt: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> str:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(10), "fake Gemini server did not start"
        return self.url()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_evt = asyncio.Event()

        async def main() -> None:
            async with ws_serve(
                self._handler, host="127.0.0.1", port=0, max_size=None
            ) as server:
                self.port = server.sockets[0].getsockname()[1]
                self._ready.set()
                await self._stop_evt.wait()

        try:
            self._loop.run_until_complete(main())
        finally:
            self._loop.close()

    async def _handler(self, connection) -> None:
        self._connection = connection
        async for raw in connection:
            message = json.loads(raw)
            self.received.append(message)
            if "setup" in message:
                self.setup_received = message["setup"]
                await connection.send(json.dumps({"setupComplete": {}}))
                handle = f"fake-resume-handle-{len(self.handles_issued) + 1:03d}"
                self.handles_issued.append(handle)
                await connection.send(
                    json.dumps(
                        {
                            "sessionResumptionUpdate": {
                                "newHandle": handle,
                                "resumable": True,
                            }
                        }
                    )
                )

    # -- driven from the test thread -----------------------------------------

    def url(self) -> str:
        return (
            f"ws://127.0.0.1:{self.port}/ws/google.ai.generativelanguage.v1beta."
            "GenerativeService.BidiGenerateContent"
        )

    def push_tool_call(self, function_calls: list[dict], timeout: float = 5.0) -> None:
        frame = json.dumps({"toolCall": {"functionCalls": function_calls}})
        future = asyncio.run_coroutine_threadsafe(
            self._connection.send(frame), self._loop
        )
        future.result(timeout)

    def wait_tool_responses(self, count: int, timeout: float = 5.0) -> None:
        """Block until the handler has drained ``count`` toolResponse frames."""
        import time

        def answered() -> int:
            return sum(1 for m in self.received if "toolResponse" in m)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if answered() >= count:
                return
            deterministic_sleep(0.02)
        raise AssertionError(
            f"expected {count} toolResponses, saw {answered()} within {timeout}s"
        )

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._stop_evt.set)
        self._thread.join(10)


@pytest.fixture
def gemini_server():
    server = FakeGeminiLiveServer()
    url = server.start()
    try:
        yield server, url
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# DirectorLoopHarness — the desktop half of the TS LiveDirectorClient
# ---------------------------------------------------------------------------


class DirectorLoopHarness:
    """Validates + executes tool calls exactly like the TS director does."""

    def __init__(self, api: TestClient, plan: dict, take: dict) -> None:
        self.api = api
        self.plan = plan
        self.take = take
        self.plan_hash = plan["plan_hash"]
        self.allowed_action_ids = frozenset(a["action_id"] for a in plan["actions"])
        state_ids: set[str] = set()
        for scene in plan["scenes"]:
            for cue in scene.get("cues", []):
                expected = cue.get("expected_state") or {}
                if expected.get("state_id"):
                    state_ids.add(expected["state_id"])
        self.allowed_state_ids = frozenset(state_ids)
        self.resumption_handle: str | None = None
        self.t = 0.0
        self.current_cue: str | None = None
        self.executed_action_ids: list[str] = []

    # -- wire helpers --------------------------------------------------------

    def connect(self, url: str):
        conn = ws_connect(url, max_size=None)
        setup = {
            "model": "models/gemini-live-director-p0",
            "systemInstruction": {"parts": [{"text": "You direct a frozen recording."}]},
            "tools": {
                "functionDeclarations": [
                    {"name": name} for name in sorted(ALLOWED_DIRECTOR_TOOLS)
                ]
            },
        }
        conn.send(json.dumps({"setup": setup}))
        while True:
            message = json.loads(conn.recv(timeout=5))
            if "setupComplete" in message:
                continue
            if "sessionResumptionUpdate" in message:
                self.resumption_handle = message["sessionResumptionUpdate"]["newHandle"]
                break
        return conn

    def recv_tool_calls(self, conn, timeout: float = 5.0) -> list[dict]:
        while True:
            message = json.loads(conn.recv(timeout=timeout))
            if "toolCall" in message:
                return message["toolCall"]["functionCalls"]

    def send_tool_response(self, conn, entries: list[dict]) -> None:
        conn.send(json.dumps({"toolResponse": {"functionResponses": entries}}))

    # -- dispatcher ----------------------------------------------------------

    def handle(self, fc: dict) -> dict:
        """Gate → dispatch → report; mirrors ToolCallDispatcher semantics."""
        name = fc.get("name", "")
        args = {k: str(v) for k, v in (fc.get("args") or {}).items()}
        execution_id = f"exec_{fc.get('id', uuid_hex())}"

        verdict = validate_tool_call(
            DirectorToolCall(
                tool=name,
                args=args,
                idempotency_key=f"idem_{execution_id}",
                execution_id=execution_id,
            ),
            allowed_action_ids=self.allowed_action_ids,
            allowed_state_ids=self.allowed_state_ids,
        )
        output = {"status": "SUCCESS", "detail": ""}
        if not verdict.ok:
            output = {"status": "FAILURE", "detail": verdict.reason or "GATE_REJECTED"}
            return output

        if name == "advance_cue":
            self.current_cue = args.get("cue_id")
            self._append_event("CUE_ENTERED", cue_id=self.current_cue)
        elif name == "execute_prepared_action":
            output = self._execute_prepared(args["action_id"], execution_id)
        elif name == "verify_visual_state":
            state_id = args.get("state_id")
            if state_id not in self.allowed_state_ids:
                output = {"status": "FAILURE", "detail": "STATE_NOT_IN_PLAN"}
            else:
                self._append_event("STATE_VERIFIED", detail=state_id)
        # pause/resume/marker/operator need no API round trip in this harness.
        return output

    def _execute_prepared(self, action_id: str, execution_id: str) -> dict:
        ticket_resp = self.api.post(
            f"{API}/plans/{self.plan['plan_id']}/actions/{action_id}/prepare"
        )
        if ticket_resp.status_code != 200:
            return {"status": "FAILURE", "detail": f"TICKET_HTTP_{ticket_resp.status_code}"}
        ticket = ticket_resp.json()
        assert ticket["plan_hash"] == self.plan_hash  # frozen plan binding
        action = ticket["action"]
        assert action["action_id"] == action_id
        assert action["idempotency_key"] in {  # plan-owned idempotency, never model-supplied
            a["idempotency_key"] for a in self.plan["actions"]
        }

        observed: dict = {}
        if action["type"] == "CODE_PLAYBACK":
            payload = ticket.get("payload_text") or ""
            if not payload:
                return {"status": "FAILURE", "detail": "PAYLOAD_BUNDLE_MISSING"}
            # Payload must be byte-identical to the frozen bundle — nothing here
            # can originate from the model (Principle C).
            assert payload == self.plan["payload_bundles"][action_id]
            # Mock desktop playback: file read → type payload → save.
            before_observed = sha256_text(ORIGINAL_FILE_CONTENT)
            after_observed = sha256_text(payload)
        elif action["type"] in ("BROWSER_NAVIGATION", "BROWSER_ACTION"):
            before_observed = after_observed = None
            url_contains = (ticket.get("expected_after") or {}).get("url_contains")
            if not url_contains:
                return {"status": "FAILURE", "detail": "BROWSER_TARGET_MISSING"}
            observed["final_url"] = f"https://{url_contains}/gemini-live"
        else:
            return {"status": "FAILURE", "detail": "ACTION_TYPE_NOT_DESKTOP_EXECUTABLE"}

        self.t += 1.0
        reported = self.api.post(
            f"{API}/plans/{self.plan['plan_id']}/actions/result",
            headers={"X-Idempotency-Key": action["idempotency_key"]},
            json={
                "take_id": self.take["take_id"],
                "action_id": action_id,
                "status": "SUCCESS",
                "execution_id": execution_id,
                "t": self.t,
                "before_hash_observed": before_observed,
                "after_hash_observed": after_observed,
                "observed": observed,
            },
        )
        assert reported.status_code == 200, reported.text
        verification = reported.json()["verification"]
        assert verification["verified"] is True, verification
        self.executed_action_ids.append(action_id)
        return {"status": "SUCCESS", "detail": ""}

    def _append_event(self, event_type: str, **extra) -> None:
        self.t += 0.5
        appended = self.api.post(
            f"{API}/takes/{self.take['take_id']}/events",
            headers={"X-Idempotency-Key": IDEM()},
            json={
                "event_type": event_type,
                "t": self.t,
                "scene_id": self.current_cue and self.current_cue.replace("cue_", "sc_"),
                "cue_id": self.current_cue,
                **extra,
            },
        )
        assert appended.status_code == 201, appended.text


# ---------------------------------------------------------------------------
# Golden path E2E
# ---------------------------------------------------------------------------


def test_director_loop_end_to_end_golden(api, gemini_server):
    server, url = gemini_server
    frozen, take = _freeze_and_take(api)
    harness = DirectorLoopHarness(api, frozen, take)

    started = api.post(
        f"{API}/takes/{take['take_id']}/events",
        headers={"X-Idempotency-Key": IDEM()},
        json={"event_type": "TAKE_STARTED", "t": 0.0},
    )
    assert started.status_code == 201

    conn = harness.connect(url)
    try:
        assert harness.resumption_handle == "fake-resume-handle-001"
        # The setup the server actually received carries the frozen manifest:
        assert server.setup_received is not None
        declared_tools = {
            d["name"] for d in server.setup_received["tools"]["functionDeclarations"]
        }
        assert declared_tools == ALLOWED_DIRECTOR_TOOLS

        script = [
            [{"id": "fc_a1", "name": "advance_cue", "args": {"cue_id": "cue_1"}}],
            [{"id": "fc_x1", "name": "execute_prepared_action", "args": {"action_id": "act_write_config"}}],
            [{"id": "fc_v1", "name": "verify_visual_state", "args": {"state_id": "st_workspace_ready"}}],
            [{"id": "fc_a2", "name": "advance_cue", "args": {"cue_id": "cue_2"}}],
            [{"id": "fc_x2", "name": "execute_prepared_action", "args": {"action_id": "act_install_deps"}}],
            [{"id": "fc_v2", "name": "verify_visual_state", "args": {"state_id": "st_deps_installed"}}],
            [{"id": "fc_a3", "name": "advance_cue", "args": {"cue_id": "cue_3"}}],
            [{"id": "fc_x3", "name": "execute_prepared_action", "args": {"action_id": "act_open_docs"}}],
            [{"id": "fc_v3", "name": "verify_visual_state", "args": {"state_id": "st_docs_open"}}],
        ]
        for step in script:
            server.push_tool_call(step)
            calls = harness.recv_tool_calls(conn)
            responses = [
                {
                    "id": fc["id"],
                    "response": {"output": harness.handle(fc)},
                }
                for fc in calls
            ]
            harness.send_tool_response(conn, responses)

        # Every answer reached the fake Gemini as a well-formed toolResponse.
        server.wait_tool_responses(len(script))
        answered = [m for m in server.received if "toolResponse" in m]
        assert len(answered) == len(script)
        for frame in answered:
            for entry in frame["toolResponse"]["functionResponses"]:
                assert entry["response"]["output"]["status"] == "SUCCESS"
    finally:
        conn.close()

    stopped = api.post(
        f"{API}/takes/{take['take_id']}/events",
        headers={"X-Idempotency-Key": IDEM()},
        json={"event_type": "TAKE_STOPPED", "t": 99.0},
    )
    assert stopped.status_code == 201

    # -- timeline completeness ----------------------------------------------
    events = api.get(f"{API}/takes/{take['take_id']}/events").json()["items"]
    types = [e["event_type"] for e in events]
    assert types.count("TAKE_STARTED") == 1
    assert types.count("TAKE_STOPPED") == 1
    assert types.count("CUE_ENTERED") == 3
    assert types.count("ACTION_SUCCESS") == 3
    assert types.count("STATE_VERIFIED") == 3
    assert "ACTION_TAMPERED" not in types and "ACTION_FAILURE" not in types

    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # monotonic unique

    action_events = [e for e in events if e.get("action_id")]
    planned_ids = {a["action_id"] for a in frozen["actions"]}
    assert {e["action_id"] for e in action_events} <= planned_ids  # zero unapproved

    # -- lineage Episode → Plan → Take ---------------------------------------
    plan_view = api.get(f"{API}/plans/{frozen['plan_id']}").json()
    assert plan_view["episode_id"] == "ep-cb-001"
    assert plan_view["episode_revision_id"] == "rev-cb-001-v3"
    assert plan_view["status"] == "FROZEN"
    take_view = api.get(f"{API}/takes/{take['take_id']}").json()
    assert take_view["execution_plan_id"] == frozen["plan_id"]
    assert take_view["execution_plan_hash"] == frozen["plan_hash"]


# ---------------------------------------------------------------------------
# Gate & tamper E2E
# ---------------------------------------------------------------------------


def test_unapproved_action_gated_and_tamper_detected(api, gemini_server):
    server, url = gemini_server
    frozen, take = _freeze_and_take(api)
    harness = DirectorLoopHarness(api, frozen, take)
    conn = harness.connect(url)
    try:
        # 1. Model hallucinates an action outside the frozen plan.
        server.push_tool_call(
            [{"id": "fc_evil", "name": "execute_prepared_action", "args": {"action_id": "act_exfiltrate_secrets"}}]
        )
        calls = harness.recv_tool_calls(conn)
        outputs = [harness.handle(fc) for fc in calls]
        assert outputs[0]["status"] == "FAILURE"
        assert outputs[0]["detail"] == "ACTION_NOT_IN_PLAN"
        harness.send_tool_response(
            conn,
            [{"id": calls[0]["id"], "response": {"output": outputs[0]}}],
        )

        # Defense-in-depth: even a direct API probe stays closed.
        probe = api.post(f"{API}/plans/{frozen['plan_id']}/actions/act_exfiltrate_secrets/prepare")
        assert probe.status_code == 404
        assert "ACTION_NOT_IN_PLAN" in probe.json()["detail"]

        # 2. Desktop reports a tampered CODE_PLAYBACK result.
        tampered = api.post(
            f"{API}/plans/{frozen['plan_id']}/actions/result",
            headers={"X-Idempotency-Key": IDEM()},
            json={
                "take_id": take["take_id"],
                "action_id": "act_write_config",
                "status": "SUCCESS",
                "execution_id": "exec_tamper_probe",
                "t": 1.0,
                "before_hash_observed": sha256_text(ORIGINAL_FILE_CONTENT),
                "after_hash_observed": "f" * 64,  # file content ≠ frozen payload
                "observed": {},
            },
        )
        assert tampered.status_code == 200
        assert tampered.json()["verification"]["verified"] is False
    finally:
        conn.close()

    events = api.get(f"{API}/takes/{take['take_id']}/events").json()["items"]
    tampered_events = [e for e in events if e["event_type"] == "ACTION_TAMPERED"]
    assert len(tampered_events) == 1
    assert tampered_events[0]["action_id"] == "act_write_config"
    assert any(
        not check["ok"]
        for e in tampered_events
        for check in e["payload"]["verification"]["checks"]
    )
    # No unapproved action ever produced evidence.
    assert all(e.get("action_id") != "act_exfiltrate_secrets" for e in events)