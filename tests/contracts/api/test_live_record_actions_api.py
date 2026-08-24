"""Live Record prepared-action dispatch API tests (Phase 3/7).

Covers the constrained-executor HTTP surface:

- prepare: FROZEN gate, ACTION_NOT_IN_PLAN, CODE_PLAYBACK payload resolution
  from the plan's own bundle store,
- result: hash verification (before/after), tamper → ACTION_TAMPERED timeline
  event regardless of the desktop-claimed status,
- execute: RUN_COMMAND via SafeShellRunner; non-server types rejected,
- bootstrap director session: fail-closed 503 when a composed credential
  resolver finds no Google credential; remote mint used when one exists.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from windagent_api.routers.v3.live_record import router as live_record_router
from windagent_api.routers.v3.live_record.dependencies import get_live_record_service
from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.live_record_models  # noqa: F401
from windagent_storage.live_record.repositories import (
    create_sql_director_session_repository,
    create_sql_live_execution_plan_repository,
    create_sql_recording_event_repository,
    create_sql_recording_segment_repository,
    create_sql_recording_take_repository,
)

IDEMPOTENCY_HEADERS = {"X-Idempotency-Key": "actions-test-key"}

PAYLOAD_TEXT = 'print("prepared playback line")\n'
PAYLOAD_AFTER_HASH = hashlib.sha256(PAYLOAD_TEXT.encode("utf-8")).hexdigest()

SCENE = {
    "scene_id": "sc_1",
    "index": 0,
    "title": "Type prepared code",
    "cues": [
        {
            "cue_id": "cue_1",
            "scene_id": "sc_1",
            "index": 0,
            "expected_state": {"state_id": "st_typed"},
        }
    ],
}


def _code_action() -> dict:
    return {
        "action_id": "act_code_1",
        "type": "CODE_PLAYBACK",
        "scene_id": "sc_1",
        "cue_id": "cue_1",
        "payload_ref": "artifact://bundles/act_code_1.py",
        "idempotency_key": "idem_act_code_1",
        "target_file": "src/demo.py",
        "before_hash": hashlib.sha256(b"").hexdigest(),
        "after_hash": PAYLOAD_AFTER_HASH,
        "typing_mode": "TYPE",
        "chars_per_second": 22,
        "expected_after": {"state_id": "st_typed"},
    }


def _command_action() -> dict:
    return {
        "action_id": "act_cmd_1",
        "type": "RUN_COMMAND",
        "scene_id": "sc_1",
        "payload_ref": "artifact://bundles/act_cmd_1.cmd",
        "command_ref": "cmd-001",
        "idempotency_key": "idem_act_cmd_1",
    }


def _tool_action() -> dict:
    return {
        "action_id": "act_tool_1",
        "type": "TOOL_RUN",
        "scene_id": "sc_1",
        "payload_ref": "artifact://bundles/act_tool_1.cmd",
        "idempotency_key": "idem_act_tool_1",
    }


def _browser_nav_action() -> dict:
    return {
        "action_id": "act_nav_1",
        "type": "BROWSER_NAVIGATION",
        "scene_id": "sc_1",
        "payload_ref": "artifact://bundles/act_nav_1.url",
        "idempotency_key": "idem_act_nav_1",
        "expected_after": {"state_id": "st_landed", "url_contains": "/apikey"},
    }


def _browser_click_action() -> dict:
    return {
        "action_id": "act_click_1",
        "type": "BROWSER_ACTION",
        "scene_id": "sc_1",
        "payload_ref": "artifact://bundles/act_click_1.json",
        "idempotency_key": "idem_act_click_1",
        "browser_semantic_target": "API Keys",
        "expected_after": {"state_id": "st_clicked", "url_contains": "/settings"},
    }


def _plan_body(actions: list[dict]) -> dict:
    return {
        "episode_id": "ep_actions",
        "episode_revision_id": "rev_1",
        "scenes": [SCENE],
        "actions": actions,
        "payload_bundles": {
            "act_code_1": PAYLOAD_TEXT,
            "act_cmd_1": "echo live-record-command-ok",
            "act_tool_1": "echo live-record-tool-ok",
            "act_nav_1": "https://windagent.test/console/apikeys",
            "act_click_1": '{"operation": "CLICK", "target": "API Keys", "locator": "text"}',
        },
    }


@pytest_asyncio.fixture
async def db():
    manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    yield manager
    await manager.close()


def _make_service(db, credential_resolver=None) -> LiveRecordApplicationService:
    def repo_bundle_factory(session):

        return SimpleNamespace(
            plans=create_sql_live_execution_plan_repository(session),
            takes=create_sql_recording_take_repository(session),
            segments=create_sql_recording_segment_repository(session),
            events=create_sql_recording_event_repository(session),
            directors=create_sql_director_session_repository(session),
        )

    return LiveRecordApplicationService(
        session_factory=db.session_factory,
        repo_bundle_factory=repo_bundle_factory,
        credential_resolver=credential_resolver,
    )


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db)
    app.dependency_overrides[get_live_record_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def _create_frozen_plan_with_take(client: TestClient, actions: list[dict]) -> dict:
    created = client.post(
        "/live-record/plans", headers=IDEMPOTENCY_HEADERS, json=_plan_body(actions)
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    frozen = plan
    for step in ("prepare", "validate", "freeze"):
        stepped = client.post(
            f"/live-record/plans/{plan['plan_id']}/{step}",
            headers=IDEMPOTENCY_HEADERS,
        )
        assert stepped.status_code == 200, stepped.text
        frozen = stepped.json()  # plan_hash only exists from VALIDATED onwards
    take = client.post(
        f"/live-record/plans/{plan['plan_id']}/takes", headers=IDEMPOTENCY_HEADERS
    )
    assert take.status_code == 201, take.text
    return {**frozen, "take": take.json()}


# ---------------------------------------------------------------------------
# prepare — dispatch ticket
# ---------------------------------------------------------------------------


def test_prepare_returns_payload_for_code_playback(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    ticket = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_code_1/prepare"
    ).json()

    assert ticket["plan_hash"] == ctx["plan_hash"]
    assert ticket["action"]["action_id"] == "act_code_1"
    assert ticket["action"]["typing_mode"] == "TYPE"
    # The operator's prepared content rides to their own desktop.
    assert ticket["payload_text"] == PAYLOAD_TEXT
    assert ticket["expected_after"]["state_id"] == "st_typed"


def test_prepare_rejects_unknown_action_and_unfrozen_plan(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    missing = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_nope/prepare"
    )
    assert missing.status_code == 404
    assert missing.json()["code"].endswith("NOT_FOUND")

    draft = client.post(
        "/live-record/plans", headers=IDEMPOTENCY_HEADERS, json=_plan_body([_code_action()])
    ).json()
    early = client.post(f"/live-record/plans/{draft['plan_id']}/actions/act_code_1/prepare")
    assert early.status_code == 409


# ---------------------------------------------------------------------------
# result — hash verification / tamper detection
# ---------------------------------------------------------------------------


def test_result_success_with_matching_hashes(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/result",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "take_id": ctx["take"]["take_id"],
            "action_id": "act_code_1",
            "status": "SUCCESS",
            "execution_id": "exec_1",
            "t": 12.5,
            "before_hash_observed": hashlib.sha256(b"").hexdigest(),
            "after_hash_observed": PAYLOAD_AFTER_HASH,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verification"]["verified"] is True
    assert body["event"]["event_type"] == "ACTION_SUCCESS"

    listed = client.get(f"/live-record/takes/{ctx['take']['take_id']}/events").json()
    assert listed["items"][0]["event_type"] == "ACTION_SUCCESS"


def test_result_hash_mismatch_records_tamper_even_if_desktop_claims_success(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/result",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "take_id": ctx["take"]["take_id"],
            "action_id": "act_code_1",
            "status": "SUCCESS",
            "execution_id": "exec_2",
            "t": 13.0,
            "before_hash_observed": hashlib.sha256(b"").hexdigest(),
            "after_hash_observed": "f" * 64,  # file content drifted
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verification"]["verified"] is False
    assert body["event"]["event_type"] == "ACTION_TAMPERED"


def test_result_rejects_action_outside_plan(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/result",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "take_id": ctx["take"]["take_id"],
            "action_id": "act_smuggled",
            "status": "SUCCESS",
            "execution_id": "exec_x",
            "t": 1.0,
        },
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# execute — server-side RUN_COMMAND
# ---------------------------------------------------------------------------


def test_execute_runs_prepared_command_only(client, monkeypatch, tmp_path):
    # Confine the SafeShellRunner workspace to tmp_path so the executed
    # command's cwd stays inside it (the runner refuses escapes by design).
    monkeypatch.setenv("WINDAGENT_LIVE_RECORD_WORKSPACE", str(tmp_path))
    ctx = _create_frozen_plan_with_take(client, [_command_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_cmd_1/execute",
        headers=IDEMPOTENCY_HEADERS,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["exit_code"] == 0
    assert "live-record-command-ok" in body["stdout_tail"]


def test_execute_rejects_non_server_executable_types(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_code_1/execute",
        headers=IDEMPOTENCY_HEADERS,
        json={},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# bootstrap — credential fail-closed + remote mint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_fail_closed_when_credential_missing(db):
    async def no_credential(provider_name: str):
        return None

    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db, credential_resolver=no_credential)
    app.dependency_overrides[get_live_record_service] = lambda: service

    with TestClient(app) as test_client:
        ctx = _create_frozen_plan_with_take(test_client, [_code_action()])
        response = test_client.post(
            "/live-record/sessions/bootstrap",
            headers=IDEMPOTENCY_HEADERS,
            json={
                "episode_id": ctx["episode_id"],
                "execution_plan_id": ctx["plan_id"],
                "current_episode_revision_id": "rev_1",
            },
        )
    assert response.status_code == 503
    body = response.json()
    assert body["details"].get("code_hint") == "PROVIDER_CREDENTIAL_MISSING"


@pytest.mark.asyncio
async def test_bootstrap_mints_remote_token_when_credential_present(db, monkeypatch):
    captured = {}

    async def fake_mint_remote(self, *, api_key, session_id, execution_plan_hash, **kw):
        captured.update({"api_key": api_key, "session_id": session_id})
        from datetime import datetime, timezone, timedelta

        from windagent_providers.google.live.token_service import EphemeralToken

        now = datetime.now(timezone.utc)
        return EphemeralToken(
            token="tokens/remote-fake",
            provider_id="google",
            model_id=self.model_id,
            execution_plan_hash=execution_plan_hash,
            session_id=session_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=30),
        )

    from windagent_providers.google.live.token_service import EphemeralTokenService

    monkeypatch.setattr(EphemeralTokenService, "mint_remote", fake_mint_remote)

    async def google_credential(provider_name: str):
        return "test-google-api-key" if provider_name == "google" else None

    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db, credential_resolver=google_credential)
    app.dependency_overrides[get_live_record_service] = lambda: service

    with TestClient(app) as test_client:
        ctx = _create_frozen_plan_with_take(test_client, [_code_action()])
        response = test_client.post(
            "/live-record/sessions/bootstrap",
            headers=IDEMPOTENCY_HEADERS,
            json={
                "episode_id": ctx["episode_id"],
                "execution_plan_id": ctx["plan_id"],
                "current_episode_revision_id": "rev_1",
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token"] == "tokens/remote-fake"
    assert captured["api_key"] == "test-google-api-key"

    # GET must never echo the token back.
    follow_up = test_client.get(f"/live-record/sessions/{body['session_id']}")
    assert "token" not in follow_up.json()


# ---------------------------------------------------------------------------
# token-refresh — Section 24/§35 (long takes outlive the ~30 min token TTL)
# ---------------------------------------------------------------------------


def _bootstrap_session(test_client: TestClient, ctx: dict) -> dict:
    response = test_client.post(
        "/live-record/sessions/bootstrap",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "episode_id": ctx["episode_id"],
            "execution_plan_id": ctx["plan_id"],
            "current_episode_revision_id": "rev_1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_token_refresh_rebinds_same_plan_and_updates_expiry(db):
    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db)
    app.dependency_overrides[get_live_record_service] = lambda: service

    with TestClient(app) as test_client:
        ctx = _create_frozen_plan_with_take(test_client, [_code_action()])
        boot = _bootstrap_session(test_client, ctx)

        refreshed = test_client.post(
            f"/live-record/sessions/{boot['session_id']}/token-refresh",
            headers=IDEMPOTENCY_HEADERS,
        )
    assert refreshed.status_code == 201, refreshed.text
    body = refreshed.json()
    assert body["refreshed"] is True
    assert body["session_id"] == boot["session_id"]
    assert body["model_id"] == boot["model_id"]
    assert body["execution_plan_hash"] == boot["execution_plan_hash"]
    assert body["token"] and body["token"] != boot["token"]

    # GET must still never echo any token.
    follow_up = test_client.get(f"/live-record/sessions/{boot['session_id']}")
    assert "token" not in follow_up.json()

    # Refresh counter is tracked server-side without exposing secrets.
    session_view = test_client.get(f"/live-record/sessions/{boot['session_id']}").json()
    assert session_view["metadata"]["refresh_count"] == 1


@pytest.mark.asyncio
async def test_token_refresh_unknown_session_is_404(db):
    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db)
    app.dependency_overrides[get_live_record_service] = lambda: service

    with TestClient(app) as test_client:
        response = test_client.post(
            "/live-record/sessions/ldir_missing/token-refresh",
            headers=IDEMPOTENCY_HEADERS,
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_token_refresh_fail_closed_when_credential_missing(db, monkeypatch):
    async def fake_mint_remote(self, *, api_key, session_id, execution_plan_hash, **kw):
        from datetime import datetime, timezone, timedelta

        from windagent_providers.google.live.token_service import EphemeralToken

        now = datetime.now(timezone.utc)
        return EphemeralToken(
            token="tokens/remote-fake-bootstrap",
            provider_id="google",
            model_id=self.model_id,
            execution_plan_hash=execution_plan_hash,
            session_id=session_id,
            issued_at=now,
            expires_at=now + timedelta(minutes=30),
        )

    from windagent_providers.google.live.token_service import EphemeralTokenService

    monkeypatch.setattr(EphemeralTokenService, "mint_remote", fake_mint_remote)

    calls = {"n": 0}

    async def credential_only_for_bootstrap(provider_name: str):
        # First call (bootstrap) sees the credential; the refresh call does not.
        calls["n"] += 1
        return "test-google-api-key" if calls["n"] == 1 else None

    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db, credential_resolver=credential_only_for_bootstrap)
    app.dependency_overrides[get_live_record_service] = lambda: service

    with TestClient(app) as test_client:
        ctx = _create_frozen_plan_with_take(test_client, [_code_action()])
        boot = _bootstrap_session(test_client, ctx)

        # Bootstrap minted remotely; a resolver that now finds NO credential
        # must refuse to refresh (fail-closed).
        refreshed = test_client.post(
            f"/live-record/sessions/{boot['session_id']}/token-refresh",
            headers=IDEMPOTENCY_HEADERS,
        )
    assert refreshed.status_code == 503
    assert refreshed.json()["details"].get("code_hint") == "PROVIDER_CREDENTIAL_MISSING"


# ---------------------------------------------------------------------------
# execute-browser — Section 14 (reuse the browser execution layer)
# ---------------------------------------------------------------------------


class _FakeBrowserState:
    def __init__(self, url: str, title: str = "WindAgent Console"):
        self.url = url
        self.title = title
        self.error = None
        self.loading = False


class _FakeBrowserService:
    """Records frozen-parameter calls; returns deterministic states."""

    def __init__(self, url_after: str = "https://windagent.test/console/apikeys"):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._url_after = url_after

    def state(self) -> _FakeBrowserState:
        return _FakeBrowserState(self._url_after)

    async def navigate(self, session_id, url, *, options=None):
        self.calls.append(("navigate", (session_id, url), {"options": options}))
        return self.state()

    async def click_semantic(self, session_id, target, *, locator="text"):
        self.calls.append(("click_semantic", (session_id, target), {"locator": locator}))
        return self.state()

    async def type_text(self, session_id, selector, text):
        self.calls.append(("type_text", (session_id, selector, text), {}))
        return self.state()

    async def scroll(self, session_id, direction, pixels, *, require_user_control=True):
        self.calls.append(
            ("scroll", (session_id, direction, pixels), {"require_user_control": require_user_control})
        )
        return self.state()


def _install_fake_browser(client: TestClient) -> _FakeBrowserService:
    fake = _FakeBrowserService()
    client.app.state.browser_session_service = fake
    return fake


def test_execute_browser_navigation_verifies_expected_url(client):
    fake = _install_fake_browser(client)
    ctx = _create_frozen_plan_with_take(
        client, [_browser_nav_action(), _browser_click_action()]
    )

    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_nav_1/execute-browser",
        headers=IDEMPOTENCY_HEADERS,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["verification"]["verified"] is True
    # URL came from the frozen bundle — request carried none.
    called_session, called_url = fake.calls[0][1]
    assert called_url == "https://windagent.test/console/apikeys"
    assert called_session.startswith("live-record-")


def test_execute_browser_click_resolves_semantic_target_from_plan(client):
    fake = _install_fake_browser(client)
    ctx = _create_frozen_plan_with_take(
        client, [_browser_nav_action(), _browser_click_action()]
    )
    # Expected URL check fails against this fake's landing page → FAILURE.
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_click_1/execute-browser",
        headers=IDEMPOTENCY_HEADERS,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILURE"
    assert body["verification"]["checks"][0]["check"] == "url_contains"

    # The semantic target was resolved from the plan bundle, not the request.
    op, args, kwargs = fake.calls[0]
    assert op == "click_semantic"
    assert args[1] == "API Keys"
    assert kwargs["locator"] == "text"


def test_execute_browser_rejects_non_browser_types(client):
    _install_fake_browser(client)
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_code_1/execute-browser",
        headers=IDEMPOTENCY_HEADERS,
        json={},
    )
    assert response.status_code == 422


def test_tool_run_executes_prepared_command_server_side(client, monkeypatch, tmp_path):
    monkeypatch.setenv("WINDAGENT_LIVE_RECORD_WORKSPACE", str(tmp_path))
    ctx = _create_frozen_plan_with_take(client, [_tool_action()])
    response = client.post(
        f"/live-record/plans/{ctx['plan_id']}/actions/act_tool_1/execute",
        headers=IDEMPOTENCY_HEADERS,
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert "live-record-tool-ok" in body["stdout_tail"]


# ---------------------------------------------------------------------------
# privacy-scan — Section 23/33 preflight guard
# ---------------------------------------------------------------------------


def test_privacy_scan_passes_clean_plan(client):
    ctx = _create_frozen_plan_with_take(client, [_code_action()])
    response = client.post(f"/live-record/plans/{ctx['plan_id']}/privacy-scan")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "PASS"
    assert body["ok"] is True
    assert body["findings"] == []
    assert body["scanned_locations"] >= 1


def test_privacy_scan_blocks_embedded_google_api_key(client):
    secret_payload = 'client = Client(api_key="AIzaSyA1234567890abcdefghijklmnopqrstuv")\n'
    body_extra = _plan_body([_code_action()])
    body_extra["payload_bundles"]["act_code_1"] = secret_payload
    created = client.post("/live-record/plans", headers=IDEMPOTENCY_HEADERS, json=body_extra)
    assert created.status_code == 201, created.text
    plan_id = created.json()["plan_id"]

    response = client.post(f"/live-record/plans/{plan_id}/privacy-scan")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "BLOCKED"
    kinds = {f["kind"] for f in body["findings"]}
    assert "google_api_key" in kinds
    # Findings are masked — the raw key never round-trips.
    for finding in body["findings"]:
        assert secret_payload.strip() not in finding["masked_preview"]


@pytest.mark.asyncio
async def test_privacy_scan_matches_configured_credential_exact_value(db):
    async def google_credential(provider_name: str):
        return "super-secret-live-key-4242" if provider_name == "google" else None

    app = FastAPI()
    app.include_router(live_record_router)
    from windagent_core.contracts.live_record.errors import LiveRecordError
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    service = _make_service(db, credential_resolver=google_credential)
    app.dependency_overrides[get_live_record_service] = lambda: service

    with TestClient(app) as test_client:
        leaked = _plan_body([_code_action()])
        leaked["payload_bundles"]["act_code_1"] = (
            "# demo narration\nKEY = super-secret-live-key-4242\nprint('hi')\n"
        )
        created = test_client.post(
            "/live-record/plans", headers=IDEMPOTENCY_HEADERS, json=leaked
        )
        assert created.status_code == 201
        plan_id = created.json()["plan_id"]
        response = test_client.post(f"/live-record/plans/{plan_id}/privacy-scan")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BLOCKED"
    assert any(f["kind"] == "configured_credential" for f in body["findings"])
