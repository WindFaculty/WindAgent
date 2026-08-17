"""
Contract and Unit Tests for Phase 2: Unified API V3 Foundation.
Verifies ApiProblem, Cursor Pagination, Resource Base, OCC Concurrency,
Idempotency Store, Correlation ID Middleware, EventEnvelope, and OpenAPI schema generation.
"""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from windagent_api.routers.v3.common.problems import (
    ApiProblem,
    ApiProblemException,
    api_problem_exception_handler,
)
from windagent_api.routers.v3.common.resource import ResourceBase
from windagent_api.routers.v3.common.pagination import PageInfo, CursorPage
from windagent_api.routers.v3.common.concurrency import (
    ExpectedVersionMutation,
    VersionConflictError,
    check_optimistic_concurrency,
)
from windagent_api.routers.v3.common.correlation import (
    CorrelationIdMiddleware,
    get_correlation_id,
)
from windagent_api.routers.v3.common.idempotency import (
    IdempotencyStore,
    IdempotencyConflictError,
)
from windagent_api.routers.v3.common.commands import CommandReceipt
from windagent_api.routers.v3.common.events import EventEnvelope
from windagent_api.main import app


def test_api_problem_model_and_rfc7807():
    problem = ApiProblem(
        type="https://windagent.dev/problems/revision-conflict",
        title="Revision Conflict",
        status=409,
        detail="Resource version mismatch",
        code="REVISION_CONFLICT",
        correlation_id="corr_test_123",
        retryable=False,
        details={"version": 12}
    )
    dumped = problem.model_dump()
    assert dumped["status"] == 409
    assert dumped["code"] == "REVISION_CONFLICT"
    assert dumped["type"] == "https://windagent.dev/problems/revision-conflict"
    assert dumped["correlation_id"] == "corr_test_123"


def test_resource_base_defaults():
    res = ResourceBase(id="proj_test_123")
    assert res.id == "proj_test_123"
    assert res.version == 1
    assert isinstance(res.created_at, datetime)
    assert isinstance(res.updated_at, datetime)


def test_cursor_pagination_schema():
    page_info = PageInfo(next_cursor="cur_xyz", has_more=True, total_count=100)
    page = CursorPage[ResourceBase](
        items=[ResourceBase(id="proj_1"), ResourceBase(id="proj_2")],
        page_info=page_info
    )
    assert len(page.items) == 2
    assert page.page_info.has_more is True
    assert page.page_info.next_cursor == "cur_xyz"


def test_optimistic_concurrency_check():
    # Matching version -> no exception
    check_optimistic_concurrency(resource_id="proj_1", current_version=5, expected_version=5)

    # Mismatched version -> raises VersionConflictError (409)
    with pytest.raises(VersionConflictError) as exc_info:
        check_optimistic_concurrency(resource_id="proj_1", current_version=6, expected_version=5)
    
    problem = exc_info.value.problem
    assert problem.status == 409
    assert problem.code == "VERSION_CONFLICT"
    assert problem.details["current_version"] == 6
    assert problem.details["expected_version"] == 5


def test_idempotency_store_replay_and_conflict():
    store = IdempotencyStore(ttl_seconds=60)
    key = "idem_key_123"
    route = "/api/v3/projects"
    body_initial = {"name": "Project Alpha"}
    body_modified = {"name": "Project Beta"}

    # First check: empty
    assert store.check(key, route, body_initial) is None

    # Save initial response
    store.save(key, route, body_initial, 201, {"id": "proj_01", "name": "Project Alpha"})

    # Replay check with identical payload -> returns cached response
    cached = store.check(key, route, body_initial)
    assert cached is not None
    assert cached[0] == 201
    assert cached[1]["id"] == "proj_01"

    # Conflicting payload with same idempotency key -> raises IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        store.check(key, route, body_modified)


def test_command_receipt_model():
    receipt = CommandReceipt(
        command_id="cmd_999",
        status="ACCEPTED",
        resource_id="proj_abc",
        correlation_id="corr_456"
    )
    assert receipt.status == "ACCEPTED"
    assert receipt.command_id == "cmd_999"


def test_event_envelope_model():
    from windagent_core.domain.types import EventId
    event = EventEnvelope(
        event_id=EventId.generate(),
        event_type="screenplay.generated",
        aggregate_type="episode",
        aggregate_id="ep_01",
        sequence=1,
        correlation_id="corr_789",
        payload={"scene_count": 12}
    )
    assert event.aggregate_type == "episode"
    assert event.sequence == 1
    assert event.payload["scene_count"] == 12


def test_correlation_id_middleware_and_openapi_generation():
    with TestClient(app) as client:
        # 1. Check Correlation ID echo on endpoint
        res = client.get("/internal/architecture", headers={"X-Correlation-ID": "custom_corr_id_999"})
        assert res.status_code == 200
        assert res.headers.get("X-Correlation-ID") == "custom_corr_id_999"

        # 2. Check automatic Correlation ID generation if absent
        res2 = client.get("/internal/architecture")
        assert res2.status_code == 200
        assert res2.headers.get("X-Correlation-ID") is not None
        assert res2.headers.get("X-Correlation-ID").startswith("corr_")

        # 3. Check OpenAPI schema generates successfully
        openapi_schema = app.openapi()
        assert openapi_schema is not None
        assert "/api/v3/studio/capabilities" in openapi_schema["paths"]
        assert "/internal/architecture" in openapi_schema["paths"]

        # 4. Check V2 deprecation headers accuracy
        res_v2_sessions = client.get("/api/v2/sessions")
        assert res_v2_sessions.headers.get("Deprecation") == "true"
        # Non-studio V2 endpoint should NOT claim X-WindAgent-V3-Studio
        assert "X-WindAgent-V3-Studio" not in res_v2_sessions.headers
