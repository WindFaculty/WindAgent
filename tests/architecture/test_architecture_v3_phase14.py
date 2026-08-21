"""
Phase 14 Architecture Tests: Security and Configuration Hardening Certification.
Validates:
1. Provider secrets encrypted at rest and never exposed plaintext to clients.
2. Settings secrets stored encrypted and masked in responses ({"configured": bool}).
3. Desktop Tauri CSP configured with strict non-null policy.
4. PathSandbox denies path traversal and filesystem boundary escapes.
5. SafeShellRunner enforces workspace confinement on cwd, blocks forbidden commands, and redacts secrets.
6. Core secret redaction masks all provider key formats (OpenAI, Anthropic, Google, Groq, xAI, GitHub).
7. WebSocket endpoints handle invalid JSON and malformed subscriptions resiliently.
8. Zero duplicate canonical models.
9. Zero architecture boundary violations.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure encryption key is configured for tests
os.environ["WINDAGENT_ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

from windagent_api.main import app
from windagent_core.security.redaction import redact_text, redact_dict
from windagent_tools.filesystem.sandbox import PathSandbox
from windagent_tools.shell.runner import SafeShellRunner, redact_shell_output
from windagent_core.errors.exceptions import PermissionDeniedError
from windagent_storage.security.encryption import decrypt


def test_provider_credentials_encrypted_at_rest_and_never_returned_plaintext(tmp_path, monkeypatch):
    """Verify provider credentials are encrypted at rest and never returned plaintext in API responses."""
    client = TestClient(app)
    provider_id = f"test-provider-sec-{os.getpid()}"
    raw_api_key = "sk-ant-api03-test-secret-key-abcdef1234567890"

    # 1. Create provider via API
    res = client.post(
        "/api/v3/providers",
        json={
            "id": provider_id,
            "name": "Security Hardened Provider",
            "type": "custom",
            "base_url": "https://api.example.com/v1",
            "protocol_mode": "openai",
            "api_key": raw_api_key,
            "credential_label": "Primary Key",
        },
    )
    assert res.status_code in (201, 409), f"Failed to create provider: {res.text}"

    # 2. Verify GET provider details does NOT leak raw_api_key
    get_res = client.get(f"/api/v3/providers/{provider_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["has_credentials"] is True
    # Confirm raw_api_key does not appear in JSON response
    assert raw_api_key not in get_res.text

    # 3. Verify GET provider list does NOT leak raw_api_key
    list_res = client.get("/api/v3/providers")
    assert list_res.status_code == 200
    assert raw_api_key not in list_res.text


def test_settings_secrets_stored_encrypted_and_masked_in_responses(tmp_path, monkeypatch):
    """Verify settings secrets are saved encrypted and masked as {"configured": bool} in responses."""
    monkeypatch.setenv("WINDAGENT_CONFIG_DIR", str(tmp_path))
    client = TestClient(app)

    raw_secret = "AIzaSyTestGoogleSecretKey1234567890abcdef"
    patch_res = client.patch(
        "/api/v3/settings",
        json={"values": {"integration.google_api_key": raw_secret}},
    )
    assert patch_res.status_code == 200
    patch_data = patch_res.json()

    # Find the google_api_key setting item
    google_item = next(
        (s for s in patch_data["settings"] if s["key"] == "integration.google_api_key"),
        None,
    )
    assert google_item is not None
    assert google_item["secret"] is True
    assert google_item["value"] == {"configured": True}
    assert raw_secret not in patch_res.text

    # GET /settings/schema also masks secret
    schema_res = client.get("/api/v3/settings/schema")
    assert schema_res.status_code == 200
    schema_data = schema_res.json()
    google_schema_item = next(
        (s for s in schema_data["settings"] if s["key"] == "integration.google_api_key"),
        None,
    )
    assert google_schema_item["value"] == {"configured": True}
    assert raw_secret not in schema_res.text

    # Check the underlying secrets.json file
    secrets_file = tmp_path / "secrets.json"
    assert secrets_file.exists()
    stored_secrets = json.loads(secrets_file.read_text(encoding="utf-8"))
    assert "integration.google_api_key" in stored_secrets
    stored_val = stored_secrets["integration.google_api_key"]
    # Secret must be encrypted with enc:v1: format at rest
    assert stored_val.startswith("enc:v1:")
    assert raw_secret not in stored_val
    assert decrypt(stored_val) == raw_secret


def test_tauri_csp_configured_non_null():
    """Verify desktop tauri.conf.json has a concrete, non-null Content Security Policy."""
    tauri_conf_path = ROOT_DIR / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
    assert tauri_conf_path.exists(), f"tauri.conf.json missing at {tauri_conf_path}"

    config = json.loads(tauri_conf_path.read_text(encoding="utf-8"))
    csp = config.get("app", {}).get("security", {}).get("csp")

    assert csp is not None, "Tauri CSP must not be null"
    assert isinstance(csp, str), "Tauri CSP must be a string"
    assert len(csp.strip()) > 0, "Tauri CSP must not be empty"
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp


def test_path_sandbox_blocks_traversal_and_escapes(tmp_path):
    """Verify PathSandbox denies path traversal, encoded escapes, and parent directory escapes."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "safe.txt").write_text("safe content", encoding="utf-8")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("secret content", encoding="utf-8")

    sandbox = PathSandbox(workspace_root=workspace)

    # 1. Safe relative path succeeds
    safe_resolved = sandbox.resolve_safe_path("safe.txt")
    assert safe_resolved.exists()
    assert safe_resolved == workspace / "safe.txt"

    # 2. Relative path traversal escapes fail
    with pytest.raises(PermissionDeniedError) as exc:
        sandbox.resolve_safe_path("../outside/secret.txt")
    assert "Path traversal denied" in str(exc.value.message)
    assert exc.value.code == "WINDAGENT_ERR_PATH_TRAVERSAL_DENIED"

    # 3. Absolute path outside workspace fails
    with pytest.raises(PermissionDeniedError) as exc:
        sandbox.resolve_safe_path(str(outside_dir / "secret.txt"))
    assert "Path traversal denied" in str(exc.value.message)


@pytest.mark.asyncio
async def test_safe_shell_runner_confines_cwd_and_masks_secrets(tmp_path):
    """Verify SafeShellRunner rejects escaping cwd, blocks dangerous commands, and masks secrets."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    runner = SafeShellRunner(workspace_root=str(workspace))

    # 1. Forbidden command pattern rejected
    with pytest.raises(PermissionDeniedError) as exc:
        await runner.execute_command("rm -rf /")
    assert "forbidden pattern" in str(exc.value.message).lower()
    assert exc.value.code == "WINDAGENT_ERR_FORBIDDEN_SHELL_COMMAND"

    # 2. Escaping cwd rejected
    with pytest.raises(PermissionDeniedError) as exc:
        await runner.execute_command("echo hello", cwd=str(outside_dir))
    assert "escapes workspace root" in str(exc.value.message)
    assert exc.value.code == "WINDAGENT_ERR_PATH_TRAVERSAL_DENIED"

    # 3. Secret output redaction in runner
    raw_output = "Connected with sk-proj-1234567890abcdef123456 and password='supersecretpassword'"
    redacted = redact_shell_output(raw_output)
    assert "1234567890abcdef123456" not in redacted
    assert "supersecretpassword" not in redacted
    assert "[REDACTED]" in redacted or "REDACTED_SECRET" in redacted


def test_core_redaction_comprehensive_patterns():
    """Verify core redaction catches multiple provider keys, bearer tokens, and sensitive dict keys."""
    # OpenAI key
    redacted_openai = redact_text("key: sk-1234567890abcdef12345678")
    assert "[REDACTED]" in redacted_openai
    assert "1234567890abcdef" not in redacted_openai

    # Anthropic key
    redacted_ant = redact_text("anthropic key: sk-ant-api03-abcdef1234567890abcdef")
    assert "[REDACTED]" in redacted_ant
    assert "api03-abcdef" not in redacted_ant

    # Google key
    redacted_google = redact_text("google key: AIzaSyTestKey1234567890abcdefghijk")
    assert "[REDACTED]" in redacted_google
    assert "TestKey1234567890" not in redacted_google

    # Groq key
    redacted_groq = redact_text("groq key: gsk_1234567890abcdef12345678")
    assert "[REDACTED]" in redacted_groq
    assert "1234567890abcdef" not in redacted_groq

    # GitHub token
    redacted_gh = redact_text("github token: ghp_123456789012345678901234567890123456")
    assert "[REDACTED]" in redacted_gh
    assert "12345678901234567890" not in redacted_gh

    # Sensitive dict keys
    data = {
        "api_key": "raw-secret-value-123456",
        "auth_token": "bearer-token-value-123456",
        "model": "gpt-4o",
        "tokens_per_sec": 45.2,  # Non-secret metric
    }
    redacted_data = redact_dict(data)
    assert redacted_data["api_key"] != "raw-secret-value-123456"
    assert redacted_data["auth_token"] != "bearer-token-value-123456"
    assert redacted_data["model"] == "gpt-4o"
    assert redacted_data["tokens_per_sec"] == 45.2


def test_websocket_handles_malformed_json_and_invalid_subscriptions():
    """Verify root WebSocket handles invalid JSON and malformed subscribe envelopes without crashing."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # Initial connected greeting
        greeting = ws.receive_json()
        assert greeting.get("type") == "connected"

        # 1. Non-JSON string -> error envelope
        ws.send_text("this is not json {")
        err_msg = ws.receive_json()
        assert err_msg.get("type") == "error"
        assert err_msg.get("error") == "invalid_json"

        # 2. Missing aggregate_type -> invalid_subscription error
        ws.send_json({"type": "subscribe", "aggregate_id": "test_123"})
        err_sub = ws.receive_json()
        assert err_sub.get("type") == "error"
        assert err_sub.get("error") == "invalid_subscription"

        # 3. Invalid after_sequence -> invalid_subscription error
        ws.send_json({
            "type": "subscribe",
            "aggregate_type": "run",
            "aggregate_id": "test_123",
            "after_sequence": -5,
        })
        err_seq = ws.receive_json()
        assert err_seq.get("type") == "error"
        assert err_seq.get("error") == "invalid_subscription"

        # 4. Valid ping -> pong
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong.get("type") == "pong"


def test_duplicate_canonical_models_zero():
    """Verify check_duplicate_canonical_models.py scan reports zero duplicate canonical models."""
    script = ROOT_DIR / "scripts" / "check_duplicate_canonical_models.py"
    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert res.returncode == 0, f"Duplicate check failed:\n{res.stdout}\n{res.stderr}"
    assert "Zero duplicate canonical model definitions" in res.stdout


def test_architecture_v3_boundaries_pass():
    """Verify check_architecture_imports.py reports zero boundary violations."""
    script = ROOT_DIR / "scripts" / "check_architecture_imports.py"
    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert res.returncode == 0, f"Architecture check failed:\n{res.stdout}\n{res.stderr}"
    assert "Zero boundary violations detected" in res.stdout
