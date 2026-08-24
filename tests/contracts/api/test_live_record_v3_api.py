"""Live Record V3 API tests (ban_ke_hoach_v1.md Phase 1).

Drives the real routers over an in-memory SQLite database with the SQL
repository bundle composed exactly as the container does:

- full lifecycle: create -> validate -> freeze -> immutable after freeze,
- fail-closed gates: take requires FROZEN plan, missing idempotency key
  rejected, unknown plan -> 404 problem+json,
- staleness assertion against the episode's current revision,
- append-only timeline with repository-assigned monotonic seq.
"""

from __future__ import annotations

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

IDEMPOTENCY_HEADERS = {"X-Idempotency-Key": "test-idem-key"}

SCENE = {
    "scene_id": "sc_1",
    "index": 0,
    "title": "Install dependencies",
    "cues": [
        {
            "cue_id": "cue_1",
            "scene_id": "sc_1",
            "index": 0,
            "expected_state": {"state_id": "st_deps_installed"},
        }
    ],
}

ACTION = {
    "action_id": "act_1",
    "type": "CODE_PLAYBACK",
    "scene_id": "sc_1",
    "cue_id": "cue_1",
    "payload_ref": "artifact://bundles/act_1.py",
    "idempotency_key": "idem_act_1",
    "expected_after": {"state_id": "st_deps_installed"},
}


@pytest_asyncio.fixture
async def db():
    manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def client(db):
    from types import SimpleNamespace

    def repo_bundle_factory(session):
        return SimpleNamespace(
            plans=create_sql_live_execution_plan_repository(session),
            takes=create_sql_recording_take_repository(session),
            segments=create_sql_recording_segment_repository(session),
            events=create_sql_recording_event_repository(session),
            directors=create_sql_director_session_repository(session),
        )

    service = LiveRecordApplicationService(
        session_factory=db.session_factory,
        repo_bundle_factory=repo_bundle_factory,
    )
    app = FastAPI()
    app.include_router(live_record_router)
    # Mirror main.py's problem+json mapping for the Live Record family.
    from windagent_api.routers.v3.live_record.errors import live_record_error_handler
    from windagent_core.contracts.live_record.errors import LiveRecordError

    app.add_exception_handler(LiveRecordError, live_record_error_handler)
    app.dependency_overrides[get_live_record_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def _create_plan(client: TestClient, revision: str = "rev_ep_7") -> dict:
    response = client.post(
        "/live-record/plans",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "episode_id": "ep_alpha",
            "episode_revision_id": revision,
            "scenes": [SCENE],
            "actions": [ACTION],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _freeze(client: TestClient, plan_id: str) -> dict:
    for action in ("prepare", "validate", "freeze"):
        response = client.post(
            f"/live-record/plans/{plan_id}/{action}", headers=IDEMPOTENCY_HEADERS
        )
        assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_plan_full_lifecycle_to_frozen(client):
    plan = _create_plan(client)
    assert plan["status"] == "DRAFT"
    assert plan["preparation_revision"] == 1
    assert plan["recordable"] is False

    # DRAFT cannot skip straight to VALIDATED.
    skipped = client.post(
        f"/live-record/plans/{plan['plan_id']}/validate", headers=IDEMPOTENCY_HEADERS
    )
    assert skipped.status_code == 409

    prepared = client.post(
        f"/live-record/plans/{plan['plan_id']}/prepare", headers=IDEMPOTENCY_HEADERS
    ).json()
    assert prepared["status"] == "PREPARED"

    validated = client.post(
        f"/live-record/plans/{plan['plan_id']}/validate", headers=IDEMPOTENCY_HEADERS
    ).json()
    assert validated["status"] == "VALIDATED"
    assert len(validated["plan_hash"]) == 64

    frozen = client.post(
        f"/live-record/plans/{plan['plan_id']}/freeze", headers=IDEMPOTENCY_HEADERS
    ).json()
    assert frozen["status"] == "FROZEN"
    assert len(frozen["plan_hash"]) == 64
    assert frozen["recordable"] is True
    assert frozen["frozen_at"] is not None


def test_frozen_plan_content_is_immutable(client):
    plan = _create_plan(client)
    _freeze(client, plan["plan_id"])

    rejected = client.patch(
        f"/live-record/plans/{plan['plan_id']}/content",
        headers=IDEMPOTENCY_HEADERS,
        json={"actions": [ACTION]},
    )
    assert rejected.status_code == 409
    body = rejected.json()
    assert body["code"].startswith("LIVE_RECORD_PLAN_FROZEN") or "FROZEN" in body["title"].upper()


def test_freeze_requires_validated_lineage(client):
    bad = client.post(
        "/live-record/plans",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "episode_id": "ep_alpha",
            "episode_revision_id": "rev_ep_7",
            "scenes": [],
            "actions": [ACTION],  # references scene sc_1 which does not exist
        },
    )
    assert bad.status_code == 422  # lineage validation fails at creation

    orphan = client.post(
        "/live-record/plans",
        headers=IDEMPOTENCY_HEADERS,
        json={
            "episode_id": "ep_alpha",
            "episode_revision_id": "rev_ep_7",
            "scenes": [{"scene_id": "sc_other", "index": 0}],
            "actions": [],
        },
    )
    assert orphan.status_code == 201
    frozen = client.post(
        f"/live-record/plans/{orphan.json()['plan_id']}/freeze",
        headers=IDEMPOTENCY_HEADERS,
    )
    assert frozen.status_code == 409  # DRAFT cannot freeze directly


# ---------------------------------------------------------------------------
# Fail-closed gates
# ---------------------------------------------------------------------------


def test_take_requires_frozen_plan_and_stamps_hash(client):
    plan = _create_plan(client)

    early = client.post(
        f"/live-record/plans/{plan['plan_id']}/takes", headers=IDEMPOTENCY_HEADERS
    )
    assert early.status_code == 409  # not frozen yet

    frozen = _freeze(client, plan["plan_id"])
    take = client.post(
        f"/live-record/plans/{plan['plan_id']}/takes", headers=IDEMPOTENCY_HEADERS
    )
    assert take.status_code == 201, take.text
    body = take.json()
    assert body["execution_plan_hash"] == frozen["plan_hash"]
    assert body["session_status"] == "IDLE"


def test_missing_idempotency_key_rejected(client):
    response = client.post(
        "/live-record/plans",
        json={"episode_id": "ep_alpha", "episode_revision_id": "rev", "scenes": [], "actions": []},
    )
    assert response.status_code == 422


def test_unknown_plan_returns_problem_json(client):
    response = client.get("/live-record/plans/plan_missing")
    assert response.status_code == 404
    body = response.json()
    assert body["status"] == 404
    assert "detail" in body and "code" in body


# ---------------------------------------------------------------------------
# Staleness (Principle A)
# ---------------------------------------------------------------------------


def test_staleness_check_detects_moved_episode_revision(client):
    plan = _create_plan(client, revision="rev_ep_7")

    ok = client.post(
        f"/live-record/plans/{plan['plan_id']}/staleness-check",
        json={"current_episode_revision_id": "rev_ep_7"},
    )
    assert ok.status_code == 200

    stale = client.post(
        f"/live-record/plans/{plan['plan_id']}/staleness-check",
        json={"current_episode_revision_id": "rev_ep_8"},
    )
    assert stale.status_code == 422
    assert "RECORDING_PLAN_STALE" in stale.json()["detail"]


def test_mark_stale_from_frozen_then_terminal(client):
    plan = _create_plan(client)
    _freeze(client, plan["plan_id"])

    stale = client.post(
        f"/live-record/plans/{plan['plan_id']}/mark-stale", headers=IDEMPOTENCY_HEADERS
    )
    assert stale.status_code == 200
    assert stale.json()["status"] == "STALE"
    assert stale.json()["recordable"] is False

    resurrect = client.post(
        f"/live-record/plans/{plan['plan_id']}/mark-invalid", headers=IDEMPOTENCY_HEADERS
    )
    assert resurrect.status_code == 409  # STALE is terminal


# ---------------------------------------------------------------------------
# Timeline events
# ---------------------------------------------------------------------------


def test_timeline_events_append_with_monotonic_seq(client):
    plan = _create_plan(client)
    _freeze(client, plan["plan_id"])
    take = client.post(
        f"/live-record/plans/{plan['plan_id']}/takes", headers=IDEMPOTENCY_HEADERS
    ).json()

    seqs = []
    for payload in (
        {"event_type": "TAKE_STARTED", "t": 0.0},
        {"event_type": "CUE_ENTERED", "t": 1.5, "cue_id": "cue_1"},
        {"event_type": "ACTION_EXECUTED", "t": 2.25, "action_id": "act_1"},
    ):
        appended = client.post(
            f"/live-record/takes/{take['take_id']}/events",
            headers=IDEMPOTENCY_HEADERS,
            json=payload,
        )
        assert appended.status_code == 201, appended.text
        seqs.append(appended.json()["seq"])
    assert seqs == [1, 2, 3]

    listed = client.get(f"/live-record/takes/{take['take_id']}/events").json()
    assert [e["event_type"] for e in listed["items"]] == [
        "TAKE_STARTED",
        "CUE_ENTERED",
        "ACTION_EXECUTED",
    ]
