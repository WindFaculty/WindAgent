"""API tests for the /api/v4/workspaces HTTP endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import windagent.modules.workspace.infrastructure.tables  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from windagent.modules.workspace.manifest import build_workspace_manifest
from windagent.platform.configuration.settings import Settings
from windagent.platform.persistence import metadata
from windagent_api.app import create_app

WORKSPACES_URL = "/api/v4/workspaces"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def workspace_client(tmp_path: Path) -> TestClient:
    db_path = (tmp_path / "ws_test.db").as_posix()
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


def test_workspace_manifest_structure() -> None:
    manifest = build_workspace_manifest()
    assert manifest.id == "workspace"
    assert manifest.version == "1.0.0"
    assert len(manifest.commands) == 15
    assert len(manifest.queries) == 8
    assert len(manifest.jobs) == 2
    assert "workspace" in manifest.capabilities
    assert "sandbox" in manifest.capabilities
    assert "quotas" in manifest.capabilities
    assert "locks" in manifest.capabilities


def test_workspace_api_crud_flow(workspace_client: TestClient, tmp_path: Path) -> None:
    # 1. Create workspace
    create_payload = {
        "name": "Integration Workspace",
        "slug": "integration-ws",
        "root_path": str(tmp_path),
        "owner_id": "test_owner",
        "description": "Integration testing workspace",
        "tier": "LOCAL",
    }
    resp = workspace_client.post(WORKSPACES_URL, json=create_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    ws_id = data["workspace_id"]
    assert data["name"] == "Integration Workspace"
    assert data["slug"] == "integration-ws"
    assert data["status"] == "ACTIVE"
    assert data["optimistic_version"] == 1

    # 2. Get by ID
    get_resp = workspace_client.get(f"{WORKSPACES_URL}/{ws_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["workspace_id"] == ws_id

    # 3. Get by slug
    slug_resp = workspace_client.get(f"{WORKSPACES_URL}/integration-ws")
    assert slug_resp.status_code == 200
    assert slug_resp.json()["workspace_id"] == ws_id

    # 4. Update
    patch_resp = workspace_client.patch(
        f"{WORKSPACES_URL}/{ws_id}",
        json={"expected_version": 1, "name": "Updated Workspace Title"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Updated Workspace Title"
    assert patch_resp.json()["optimistic_version"] == 2

    # 5. Members
    member_resp = workspace_client.post(
        f"{WORKSPACES_URL}/{ws_id}/members",
        json={"user_id": "collaborator_1", "role": "MEMBER", "actor_id": "test_owner"},
    )
    assert member_resp.status_code == 201
    assert member_resp.json()["user_id"] == "collaborator_1"

    list_members = workspace_client.get(f"{WORKSPACES_URL}/{ws_id}/members")
    assert list_members.status_code == 200
    assert len(list_members.json()) == 2

    # 6. Projects binding
    bind_resp = workspace_client.post(f"{WORKSPACES_URL}/{ws_id}/projects/proj_alpha")
    assert bind_resp.status_code == 200
    assert bind_resp.json()["projects_count"] == 1

    # 7. Locks
    lock_resp = workspace_client.post(
        f"{WORKSPACES_URL}/{ws_id}/locks",
        json={
            "resource_type": "scene",
            "resource_id": "scene_01",
            "holder_id": "agent_alpha",
            "ttl_seconds": 300,
        },
    )
    assert lock_resp.status_code == 201
    assert lock_resp.json()["resource_id"] == "scene_01"

    list_locks = workspace_client.get(f"{WORKSPACES_URL}/{ws_id}/locks")
    assert list_locks.status_code == 200
    assert len(list_locks.json()) == 1

    # 8. Snapshot
    snap_resp = workspace_client.get(f"{WORKSPACES_URL}/{ws_id}/snapshot")
    assert snap_resp.status_code == 200
    assert snap_resp.json()["workspace_id"] == ws_id

    # 9. Path validation
    val_resp = workspace_client.post(
        f"{WORKSPACES_URL}/{ws_id}/validate-path",
        json={"target_path": "subfolder/story.md"},
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True
    assert val_resp.json()["relative_path"] == "subfolder/story.md"

    # 10. Archive
    arch_resp = workspace_client.post(
        f"{WORKSPACES_URL}/{ws_id}/archive",
        json={"expected_version": snap_resp.json()["optimistic_version"]},
    )
    assert arch_resp.status_code == 200
    assert arch_resp.json()["status"] == "ARCHIVED"
