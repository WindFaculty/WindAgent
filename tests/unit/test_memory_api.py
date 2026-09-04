"""API and contract tests for the /api/v4/memory HTTP surface (Phase 14)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from windagent.modules.memory.manifest import build_memory_manifest
from windagent.platform.configuration.settings import Settings
from windagent.platform.persistence import metadata
from windagent_api.app import create_app

MEMORY_URL = "/api/v4/memory"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def memory_client(tmp_path: Path) -> TestClient:
    db_path = (tmp_path / "memory_test.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    _run(_create())

    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_manifest_structure() -> None:
    manifest = build_memory_manifest()
    assert manifest.id == "memory"
    assert manifest.version == "1.0.0"
    assert len(manifest.commands) == 7
    assert len(manifest.queries) == 13
    assert len(manifest.jobs) == 1
    assert "working_memory" in manifest.capabilities
    assert "policy_memory" in manifest.capabilities


def test_save_and_get_memory_api(memory_client: TestClient) -> None:
    payload = {
        "key": "user_pref:theme",
        "value": {"theme": "dark", "fontSize": 14},
        "scope": "user",
        "provenance_source": "user_settings",
        "tags": {"app": "desktop"},
    }
    res = memory_client.post(MEMORY_URL, json=payload)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["key"] == "user_pref:theme"
    assert data["scope"] == "user"
    assert data["value"] == {"theme": "dark", "fontSize": 14}
    mem_id = data["id"]

    # Get by ID
    get_res = memory_client.get(f"{MEMORY_URL}/{mem_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == mem_id

    # Lookup by scope and key
    lookup_res = memory_client.get(f"{MEMORY_URL}/lookup", params={"scope": "user", "key": "user_pref:theme"})
    assert lookup_res.status_code == 200
    assert lookup_res.json()["data"]["id"] == mem_id


def test_secret_exclusion_api_returns_403(memory_client: TestClient) -> None:
    payload = {
        "key": "api_key",
        "value": "sk-1234567890abcdefghijklmnopqrstuvwxyz",
        "scope": "working",
        "provenance_source": "test",
    }
    res = memory_client.post(MEMORY_URL, json=payload)
    # Write policy rejects secret credentials with 403 Forbidden
    assert res.status_code == 403
    assert "Storing API keys, tokens, or passwords" in res.text


def test_batch_save_and_list_queries(memory_client: TestClient) -> None:
    batch_payload = {
        "records": [
            {
                "key": "doc_1",
                "value": "Guide content",
                "scope": "project",
                "provenance_source": "docs",
                "project_id": "proj_x",
                "tags": {"type": "guide"},
            },
            {
                "key": "doc_2",
                "value": "API specification",
                "scope": "project",
                "provenance_source": "docs",
                "project_id": "proj_x",
                "tags": {"type": "spec"},
            },
            {
                "key": "trace_1",
                "value": "Step 1 passed",
                "scope": "episodic",
                "provenance_source": "session_runner",
                "session_id": "sess_x",
            },
        ]
    }
    res = memory_client.post(f"{MEMORY_URL}/batch", json=batch_payload)
    assert res.status_code == 200
    assert len(res.json()["data"]) == 3

    # List project records
    list_res = memory_client.get(MEMORY_URL, params={"project_id": "proj_x"})
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) == 2

    # List episodic
    ep_res = memory_client.get(f"{MEMORY_URL}/episodic", params={"session_id": "sess_x"})
    assert ep_res.status_code == 200
    assert len(ep_res.json()["data"]) == 1

    # Search tag
    tag_res = memory_client.get(f"{MEMORY_URL}/search-tag", params={"tag_key": "type", "tag_value": "spec"})
    assert tag_res.status_code == 200
    assert len(tag_res.json()["data"]) == 1
    assert tag_res.json()["data"][0]["key"] == "doc_2"

    # Stats
    stats_res = memory_client.get(f"{MEMORY_URL}/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()["data"]
    assert stats["total_records"] >= 3
    assert stats["by_scope"]["project"] == 2
    assert stats["by_scope"]["episodic"] == 1


def test_delete_and_forget_pattern_api(memory_client: TestClient) -> None:
    # Save 2 records
    memory_client.post(
        MEMORY_URL,
        json={"key": "sess:1", "value": "a", "scope": "session", "provenance_source": "test", "session_id": "s1"},
    )
    memory_client.post(
        MEMORY_URL,
        json={"key": "sess:2", "value": "b", "scope": "session", "provenance_source": "test", "session_id": "s1"},
    )

    # Forget pattern
    f_res = memory_client.post(
        f"{MEMORY_URL}/forget-pattern",
        json={"scope": "session", "key_prefix": "sess:", "session_id": "s1"},
    )
    assert f_res.status_code == 200
    assert f_res.json()["forgotten_count"] == 2

    # Verify deleted
    lookup = memory_client.get(f"{MEMORY_URL}/lookup", params={"scope": "session", "key": "sess:1", "session_id": "s1"})
    assert lookup.json()["data"] is None
