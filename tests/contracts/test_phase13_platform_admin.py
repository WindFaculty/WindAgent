"""
Phase 13 — Platform & Administration Contract Tests.
Verifies:
- Browser Runtime Console: live session listing, truthful default state, realtime ws
- Workspace Files: sandboxed create/list/get/download/delete, traversal rejection
- Memory: scoped records, retrieval, search (Memory != Database)
- Logs: real runtime records, filters, /ws/v3/logs stream
- Settings: server-owned schema, validation, secret configured-status only
Verdict target: FRONTEND_V2_PHASE_13_PLATFORM_ADMIN_VERIFIED
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from windagent_api.main import app


@pytest.fixture
def client(monkeypatch):
    # Explicitly enable the demo profile (Phase 4: demo seeding is opt-in).
    monkeypatch.setenv("WINDAGENT_PROFILE", "demo")
    # Pre-build the fallback DB container OUTSIDE the TestClient event loop
    # (db upgrade needs a fresh loop; get_uow requests then reuse the cache).
    from windagent_api import dependencies

    if dependencies._container is None:
        dependencies._container = dependencies._build_container()
    return TestClient(app)


def _reset_workspace_root(tmp_path, client):
    app.state.workspace_root = tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13A — Browser Runtime Console
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserRuntimeConsole:
    def test_list_sessions_is_real_list(self, client):
        r = client.get("/api/v3/browser/sessions")
        assert r.status_code == 200
        sessions = r.json()
        assert isinstance(sessions, list)
        for s in sessions:
            assert "id" in s
            assert "url" in s

    def test_get_missing_session_returns_default_state_not_fabricated(self, client):
        # get_state on unknown id returns a truthful default (no mock session).
        r = client.get("/api/v3/browser/sessions/brs-does-not-exist")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "brs-does-not-exist"
        assert data["url"] == "about:blank"

    def test_click_before_navigation_conflicts(self, client):
        # No daemon spawned: click on an unknown session is rejected upfront.
        r = client.post("/api/v3/browser/sessions/brs-never-created/click", json={"x": 10, "y": 10})
        assert r.status_code == 409

    def test_realtime_ws_connects(self, client):
        with client.websocket_connect("/ws/v3/browser") as ws:
            data = ws.receive_json()
            assert data["event"] == "browser.stream.ready"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13B — Workspace Files (sandbox)
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkspaceFiles:
    def test_list_files_empty(self, tmp_path, client):
        _reset_workspace_root(tmp_path, client)
        r = client.get("/api/v3/files")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_file_and_get(self, tmp_path, client):
        _reset_workspace_root(tmp_path, client)
        payload = {"path": "notes/idea.md", "name": "idea.md", "content": "hello phase 13"}
        r = client.post("/api/v3/files", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["path"] == "notes/idea.md"
        assert data["name"] == "idea.md"
        assert data["checksum"] == __import__("hashlib").sha256(b"hello phase 13").hexdigest()

        r_get = client.get(f"/api/v3/files/{data['id']}")
        assert r_get.status_code == 200
        assert r_get.json()["path"] == "notes/idea.md"

    def test_absolute_path_rejected(self, tmp_path, client):
        _reset_workspace_root(tmp_path, client)
        r = client.post("/api/v3/files", json={"path": "C:/Windows/system32/evil.txt", "name": "evil.txt", "content": "x"})
        assert r.status_code == 400

    def test_traversal_rejected(self, tmp_path, client):
        _reset_workspace_root(tmp_path, client)
        r = client.post("/api/v3/files", json={"path": "../../outside.txt", "name": "outside.txt", "content": "x"})
        assert r.status_code == 400

    def test_download_and_delete(self, tmp_path, client):
        _reset_workspace_root(tmp_path, client)
        r = client.post("/api/v3/files", json={"path": "a.txt", "name": "a.txt", "content": "data"})
        fid = r.json()["id"]

        r_dl = client.get(f"/api/v3/files/{fid}/download")
        assert r_dl.status_code == 200
        assert r_dl.content == b"data"

        r_del = client.delete(f"/api/v3/files/{fid}")
        assert r_del.status_code == 204

        r_miss = client.get(f"/api/v3/files/{fid}")
        assert r_miss.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13C — Memory (records + retrieval)
# ─────────────────────────────────────────────────────────────────────────────

class TestMemory:
    def test_list_memory(self, client):
        r = client.get("/api/v3/memory")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_and_get_record(self, client):
        payload = {"scope": "global", "content": "phase 13 memory record", "type": "short_term"}
        r = client.post("/api/v3/memory", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["id"].startswith("mem-")
        assert data["scope"] == "global"
        assert data["content"] == "phase 13 memory record"

        r_get = client.get(f"/api/v3/memory/{data['id']}")
        assert r_get.status_code == 200
        assert r_get.json()["id"] == data["id"]

    def test_invalid_scope_rejected(self, client):
        r = client.post("/api/v3/memory", json={"scope": "galaxy", "content": "x"})
        assert r.status_code == 400

    def test_search_retrieval(self, client):
        client.post("/api/v3/memory", json={"scope": "project", "content": "unique-needle-token-7319"})
        r = client.post("/api/v3/memory/search", json={"query": "unique-needle-token-7319"})
        assert r.status_code == 200
        results = r.json()
        assert any("unique-needle-token-7319" in rec["content"] for rec in results)

    def test_search_no_match(self, client):
        r = client.post("/api/v3/memory/search", json={"query": "zzz-definitely-absent-9911"})
        assert r.status_code == 200
        assert all("zzz-definitely-absent-9911" not in rec["content"] for rec in r.json())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13D — Logs (real records + realtime)
# ─────────────────────────────────────────────────────────────────────────────

class TestLogs:
    def test_list_logs(self, client):
        r = client.get("/api/v3/logs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_log_sources(self, client):
        r = client.get("/api/v3/logs/sources")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_realtime_ws_connects(self, client):
        with client.websocket_connect("/ws/v3/logs") as ws:
            data = ws.receive_json()
            assert data["event"] == "log.stream.ready"

    def test_settings_patch_emits_correlated_log(self, client):
        client.patch("/api/v3/settings", json={"values": {"routing.failover_enabled": True}})
        r = client.get("/api/v3/logs", params={"source": "settings"})
        assert r.status_code == 200
        records = r.json()
        assert any(rec["message"] == "Settings updated" and rec["correlation_id"] for rec in records)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13E — Settings (server-owned schema + secure storage)
# ─────────────────────────────────────────────────────────────────────────────

class TestSettings:
    def test_schema_never_leaks_secrets(self, client):
        r = client.get("/api/v3/settings/schema")
        assert r.status_code == 200
        data = r.json()
        assert data["schema_version"] >= 1
        keys = {item["key"] for item in data["settings"]}
        assert "integration.google_api_key" in keys
        raw = json.dumps(data)
        assert "sk-" not in raw and "AIza" not in raw  # no raw secret bytes

    def test_secret_rendered_as_configured_status(self, client):
        r = client.get("/api/v3/settings/schema")
        items = {item["key"]: item for item in r.json()["settings"]}
        secret_item = items["integration.google_api_key"]
        assert secret_item["secret"] is True
        assert isinstance(secret_item["value"], dict)
        assert "configured" in secret_item["value"]

    def test_boolean_validation(self, client):
        r = client.patch("/api/v3/settings", json={"values": {"routing.failover_enabled": "yes"}})
        assert r.status_code == 400

    def test_number_range_validation(self, client):
        r = client.patch("/api/v3/settings", json={"values": {"agent.max_concurrent_instances": 999}})
        assert r.status_code == 400

    def test_patch_valid_setting(self, tmp_path, client, monkeypatch):
        monkeypatch.setenv("WINDAGENT_CONFIG_DIR", str(tmp_path))
        r = client.patch("/api/v3/settings", json={"values": {"agent.max_concurrent_instances": 6}})
        assert r.status_code == 200
        items = {item["key"]: item for item in r.json()["settings"]}
        assert items["agent.max_concurrent_instances"]["value"] == 6

    def test_secret_roundtrip_configured_flag(self, tmp_path, client, monkeypatch):
        monkeypatch.setenv("WINDAGENT_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv(
            "WINDAGENT_ENCRYPTION_KEY",
            "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        )
        r = client.patch("/api/v3/settings", json={"values": {"integration.openai_api_key": "sk-tes...-123"}})
        assert r.status_code == 200
        items = {item["key"]: item for item in r.json()["settings"]}
        assert items["integration.openai_api_key"]["value"] == {"configured": True}

        # persisted server-side encrypted at rest, never echoed back raw
        secrets_file = tmp_path / "secrets.json"
        assert secrets_file.exists()
        stored = json.loads(secrets_file.read_text(encoding="utf-8"))
        stored_value = stored.get("integration.openai_api_key")
        assert isinstance(stored_value, str) and stored_value.startswith("enc:v1:")
        assert "sk-tes...-123" not in json.dumps(r.json())
        assert "sk-tes...-123" not in json.dumps(stored)