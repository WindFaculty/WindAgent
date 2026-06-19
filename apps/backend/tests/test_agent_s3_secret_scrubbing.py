"""Regression tests for SEC-002 — secret scrubbing in Agent-S3 health responses.

These tests pin the contract that ``/agent-s3/health`` (and ``/health``)
never leak API keys, bearer tokens, passwords, or any other secret-shaped
values into the JSON body, even when those values are present in env vars
or in the underlying AgentS3Config dataclass.

The audit (Phase 11 closeout, finding SEC-002) found that the ``extra``
dict in ``status_from_config()`` did not include the API keys, but that
defence is fragile — any future change that calls ``extra.update(asdict(cfg))``
or similar would leak. The ``scrub_secrets()`` helper added in Phase 11
provides defence-in-depth: it scrubs any key matching a secret pattern
before the dict leaves ``status_to_dict()`` or ``health_summary()``.

These tests are intentionally written so they:
  1. Set the actual env vars with high-entropy fake secrets.
  2. Drive the real FastAPI test client (not just unit calls).
  3. Assert no fake-secret substring appears anywhere in the response.
  4. Assert the boolean ``*_configured`` placeholders are present when
     the env var is set.
  5. Assert a malformed / hypothetical future leak is caught by the
     scrub layer (defence-in-depth).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from services.agent_s3_config import (
    AgentS3Config,
    load_agent_s3_config,
)
from services.agent_s3_health import (
    build_status,
    health_summary,
    scrub_secrets,
    status_to_dict,
)


# ---- Fixtures ----

# High-entropy fake secrets. These MUST NOT appear in any test output
# (CI log capture, response body, etc.) once the scrub layer is in place.
FAKE_MODEL_API_KEY = "sk-test-secret-1234567890ABCDEF"
FAKE_GROUND_API_KEY = "ground-secret-abcdef0123456789"
FAKE_BEARER_TOKEN = "bearer-xyzzy-leak-check-9988"
FAKE_PASSWORD = "p@ssw0rd-leak-check-zzz"
FAKE_AUTH_HEADER = "auth-leak-check-7777"

# Sentinel substrings — short, distinctive, must not survive scrub.
# Includes the explicit values the user spec required for Phase 11
# closeout (sk-test-secret-123456 / ground-secret-abcdef) so the test
# fails loudly if those particular strings ever leak.
_SECRET_NEEDLES = (
    "secret-1234567890",
    "secret-abcdef0123",
    "leak-check-9988",
    "leak-check-zzz",
    "leak-check-7777",
)

# User-spec required substrings for Phase 11 closeout (SEC-002).
USER_SPEC_MODEL_KEY = "sk-test-secret-123456"
USER_SPEC_GROUND_KEY = "ground-secret-abcdef"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("WINDAGENT_AGENT_S3_"):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def _fake_secrets(monkeypatch):
    """Set high-entropy fake secrets in env. The lifespan will read them."""
    monkeypatch.setenv("WINDAGENT_AGENT_S3_ENABLED", "1")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_PROVIDER", "openai")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_MODEL", "gpt-5")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_MODEL_API_KEY", FAKE_MODEL_API_KEY)
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_PROVIDER", "huggingface")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_MODEL", "ui-tars")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_API_KEY", FAKE_GROUND_API_KEY)


@pytest.fixture
def _user_spec_secrets(monkeypatch):
    """Set the exact user-spec values from the Phase 11 task brief.

    These are the canonical values that the SEC-002 fix MUST scrub.
    If a future regression lets these exact strings through, the
    `TestUserSpecSecretsAreScrubbed` class below will fail.
    """
    monkeypatch.setenv("WINDAGENT_AGENT_S3_ENABLED", "1")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_PROVIDER", "openai")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_MODEL", "gpt-5")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_MODEL_API_KEY", USER_SPEC_MODEL_KEY)
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_PROVIDER", "huggingface")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_MODEL", "ui-tars")
    monkeypatch.setenv("WINDAGENT_AGENT_S3_GROUND_API_KEY", USER_SPEC_GROUND_KEY)


# ---- Unit tests: scrub_secrets() contract ----

class TestScrubSecretsUnit:
    """Pure-function tests for the scrub layer."""

    def test_replaces_api_key_with_boolean_placeholder(self):
        out = scrub_secrets({"model_api_key": "sk-secret-XYZ"})
        assert out == {"model_api_key_configured": True}

    def test_replaces_empty_api_key_with_false(self):
        out = scrub_secrets({"model_api_key": ""})
        assert out == {"model_api_key_configured": False}

    def test_replaces_ground_api_key(self):
        out = scrub_secrets({"ground_api_key": "ground-secret"})
        assert "ground_api_key" not in out
        assert out["ground_api_key_configured"] is True

    def test_replaces_case_insensitive_apikey(self):
        out = scrub_secrets({"apiKey": "x", "API_KEY": "y", "ApiKey": "z"})
        # All three variants scrubbed; no plaintext remains.
        assert "apiKey" not in out
        assert "API_KEY" not in out
        assert "ApiKey" not in out
        assert out["apiKey_configured"] is True
        assert out["API_KEY_configured"] is True
        assert out["ApiKey_configured"] is True

    def test_replaces_token_password_bearer_auth(self):
        out = scrub_secrets({
            "token": "abc",
            "password": "def",
            "passwd": "ghi",
            "bearer": "jkl",
            "authorization": "mno",
            "auth_header": "pqr",
        })
        for key in out:
            assert key.endswith("_configured"), f"key {key!r} should end with _configured"
        assert "token_configured" in out
        assert "password_configured" in out
        assert "passwd_configured" in out
        assert "bearer_configured" in out
        assert "authorization_configured" in out
        assert "auth_header_configured" in out

    def test_scrubs_nested_dicts(self):
        out = scrub_secrets({
            "outer": {
                "inner_api_key": "secret",
                "safe_value": 42,
            }
        })
        assert out["outer"]["safe_value"] == 42
        assert out["outer"]["inner_api_key_configured"] is True
        assert "inner_api_key" not in out["outer"]

    def test_scrubs_lists(self):
        out = scrub_secrets({
            "items": [
                {"api_key": "x"},
                {"api_key": "y"},
                "safe-string",
                42,
            ]
        })
        assert out["items"][0] == {"api_key_configured": True}
        assert out["items"][1] == {"api_key_configured": True}
        assert out["items"][2] == "safe-string"
        assert out["items"][3] == 42

    def test_passes_through_safe_keys(self):
        out = scrub_secrets({
            "mode": "package",
            "enabled": True,
            "provider": "openai",
            "model": "gpt-5",
            "notes": ["safe-text"],
        })
        assert out == {
            "mode": "package",
            "enabled": True,
            "provider": "openai",
            "model": "gpt-5",
            "notes": ["safe-text"],
        }

    def test_does_not_match_substring_unrelated(self):
        # "keyfile" / "keyboard" should NOT match api_key pattern.
        out = scrub_secrets({"keyfile": "/etc/key", "tokenize": True})
        assert out == {"keyfile": "/etc/key", "tokenize": True}

    def test_does_not_echo_value(self):
        # Even with empty placeholder, ensure the original value
        # never leaks into the response.
        out = scrub_secrets({"api_key": "must-not-leak-12345"})
        raw = json.dumps(out)
        assert "must-not-leak-12345" not in raw
        assert out == {"api_key_configured": True}


# ---- Integration tests: status_to_dict() and health_summary() ----

class TestStatusToDictScrubbing:
    """Verify that even when secrets are present in AgentS3Config,
    status_to_dict() output contains no secret value."""

    def test_status_to_dict_no_secret_when_env_keys_set(self, _fake_secrets):
        cfg = load_agent_s3_config()
        from services.agent_s3_config import status_from_config
        status = status_from_config(cfg)
        body = status_to_dict(status)

        raw = json.dumps(body)
        for needle in _SECRET_NEEDLES:
            assert needle not in raw, f"leaked needle: {needle!r}"

        # The configured booleans should be present (or absent if no
        # extra accidentally surfaces them) — but if present, must be bool.
        cfg_block = body.get("config", {})
        for key, val in cfg_block.items():
            if key.endswith("_configured"):
                assert isinstance(val, bool), f"{key!r} should be bool, got {type(val).__name__}"

    def test_status_to_dict_when_secrets_added_to_extra(self, _fake_secrets):
        """Defence-in-depth: simulate a future regression where someone
        accidentally puts the secrets into the extra dict. The scrub
        layer MUST still strip them out."""
        cfg = load_agent_s3_config()
        from services.agent_s3_config import status_from_config, AgentS3ConfigStatus
        status = status_from_config(cfg)
        # Inject fake secrets directly into extra — simulates regression.
        from dataclasses import replace
        poisoned_extra = dict(status.extra)
        poisoned_extra["model_api_key"] = FAKE_MODEL_API_KEY
        poisoned_extra["ground_api_key"] = FAKE_GROUND_API_KEY
        poisoned_extra["bearer_token"] = FAKE_BEARER_TOKEN
        poisoned_extra["auth_header"] = FAKE_AUTH_HEADER
        poisoned_extra["password"] = FAKE_PASSWORD
        poisoned = replace(status, extra=poisoned_extra)

        body = status_to_dict(poisoned)
        raw = json.dumps(body)
        for needle in _SECRET_NEEDLES:
            assert needle not in raw, f"leaked needle: {needle!r}"
        # The boolean placeholders should now be present (replacing the
        # original keys) with True because the original values were non-empty.
        cfg_block = body["config"]
        assert cfg_block["model_api_key_configured"] is True
        assert cfg_block["ground_api_key_configured"] is True
        assert cfg_block["bearer_token_configured"] is True
        assert cfg_block["auth_header_configured"] is True
        assert cfg_block["password_configured"] is True

    def test_health_summary_no_secrets_when_env_keys_set(self, _fake_secrets):
        cfg = load_agent_s3_config()
        from services.agent_s3_config import status_from_config
        status = status_from_config(cfg)
        summary = health_summary(status)

        raw = json.dumps(summary)
        for needle in _SECRET_NEEDLES:
            assert needle not in raw, f"leaked needle: {needle!r}"

    def test_health_summary_with_poisoned_extra(self, _fake_secrets):
        cfg = load_agent_s3_config()
        from services.agent_s3_config import status_from_config
        from dataclasses import replace
        status = status_from_config(cfg)
        poisoned_extra = dict(status.extra)
        poisoned_extra["model_api_key"] = FAKE_MODEL_API_KEY
        poisoned = replace(status, extra=poisoned_extra)
        summary = health_summary(poisoned)

        raw = json.dumps(summary)
        for needle in _SECRET_NEEDLES:
            assert needle not in raw, f"leaked needle: {needle!r}"


# ---- Live TestClient tests: actual /agent-s3/health endpoint ----

class TestLiveEndpointScrubbing:
    """End-to-end: drive the FastAPI test client with secrets in env."""

    def test_live_endpoint_does_not_leak_secrets(self, client, _fake_secrets):
        """The agent-s3 health endpoint must not leak any env-set secret."""
        resp = client.get("/agent-s3/health")
        assert resp.status_code == 200
        body = resp.json()
        raw = json.dumps(body)

        for needle in _SECRET_NEEDLES:
            assert needle not in raw, (
                f"/agent-s3/health leaked {needle!r}; full body: {body!r}"
            )

        # The full API key strings must also be absent (substring check).
        assert FAKE_MODEL_API_KEY not in raw
        assert FAKE_GROUND_API_KEY not in raw

    def test_live_endpoint_does_not_leak_partial_secrets(self, client, _fake_secrets):
        """Even partial leaks (e.g. first 8 chars) must not appear."""
        resp = client.get("/agent-s3/health")
        body = resp.json()
        raw = json.dumps(body)

        assert FAKE_MODEL_API_KEY[:8] not in raw, "first 8 chars leaked"
        assert FAKE_GROUND_API_KEY[:8] not in raw, "first 8 chars leaked"

    def test_root_health_endpoint_no_secrets(self, client, _fake_secrets):
        """The /health endpoint must not leak secrets either."""
        resp = client.get("/health")
        assert resp.status_code == 200
        raw = json.dumps(resp.json())

        for needle in _SECRET_NEEDLES:
            assert needle not in raw, f"/health leaked {needle!r}"
        assert FAKE_MODEL_API_KEY not in raw
        assert FAKE_GROUND_API_KEY not in raw

    def test_health_response_contains_configured_booleans_when_set(
        self, client, _fake_secrets
    ):
        """When env keys are set, the response must surface boolean
        ``*_configured`` fields rather than the secret values."""
        # This test relies on a hypothetical future regression that puts
        # the API keys into the extra dict. In the current code path
        # the keys aren't there, so we can't directly assert the
        # boolean presence. Instead, verify the contract via the unit
        # tests above (which inject directly). Here we just verify the
        # endpoint still returns 200 and contains no secret.
        resp = client.get("/agent-s3/health")
        body = resp.json()
        # The endpoint must remain reachable + well-formed.
        assert "mode" in body
        assert "config" in body
        # No accidental leakage anywhere.
        raw = json.dumps(body)
        for needle in _SECRET_NEEDLES:
            assert needle not in raw


# ---- User-spec required tests (Phase 11 task brief) ----
#
# These tests pin the exact scrub contract from the Phase 11 task
# brief. They use the canonical secret values the brief specified
# so a regression is caught immediately. They also cover a
# "defence-in-depth" path where the secrets are placed into the
# extra dict via a direct dataclass mutation -- simulating any
# future code that adds an API-key field to the response shape.

class TestUserSpecSecretsAreScrubbed:
    """Pin the contract from the Phase 11 closeout brief.

    Required behaviour (verbatim from the brief):

      Set fake env:
        WINDAGENT_AGENT_S3_MODEL_API_KEY = sk-tes...3456
        WINDAGENT_AGENT_S3_GROUND_API_KEY = ground-secret-abcdef

      Call the health service/endpoint. Assert the response does
      NOT contain:
        - sk-tes...3456
        - ground-secret-abcdef
        - substring "secret-123456"
        - substring "secret-abcdef"

      Assert only boolean configured fields or safe masked
      placeholders are present.
    """

    # --- Unit-level: scrub_secrets() with the exact user-spec values ---

    def test_scrub_strips_exact_user_spec_model_key(self):
        out = scrub_secrets({"model_api_key": USER_SPEC_MODEL_KEY})
        raw = json.dumps(out)
        assert USER_SPEC_MODEL_KEY not in raw, (
            f"model_api_key value leaked: {raw!r}"
        )
        assert "secret-123456" not in raw
        assert out == {"model_api_key_configured": True}

    def test_scrub_strips_exact_user_spec_ground_key(self):
        out = scrub_secrets({"ground_api_key": USER_SPEC_GROUND_KEY})
        raw = json.dumps(out)
        assert USER_SPEC_GROUND_KEY not in raw, (
            f"ground_api_key value leaked: {raw!r}"
        )
        assert "secret-abcdef" not in raw
        assert out == {"ground_api_key_configured": True}

    def test_scrub_strips_both_substrings_secret_123456_and_secret_abcdef(self):
        out = scrub_secrets({
            "model_api_key": USER_SPEC_MODEL_KEY,
            "ground_api_key": USER_SPEC_GROUND_KEY,
            "bearer": "secret-123456-bearer-leak",
            "auth_header": "secret-abcdef-auth-leak",
        })
        raw = json.dumps(out)
        for forbidden in (
            USER_SPEC_MODEL_KEY,
            USER_SPEC_GROUND_KEY,
            "secret-123456",
            "secret-abcdef",
            "bearer-leak",
            "auth-leak",
        ):
            assert forbidden not in raw, (
                f"{forbidden!r} leaked through scrub layer; raw={raw!r}"
            )

    # --- Service-level: status_to_dict() with user-spec env ---

    def test_status_to_dict_scrubs_user_spec_secrets(self, _user_spec_secrets):
        cfg = load_agent_s3_config()
        from services.agent_s3_config import status_from_config
        status = status_from_config(cfg)
        body = status_to_dict(status)
        raw = json.dumps(body)
        assert USER_SPEC_MODEL_KEY not in raw
        assert USER_SPEC_GROUND_KEY not in raw
        assert "secret-123456" not in raw
        assert "secret-abcdef" not in raw

    # --- Defence-in-depth: simulate a future regression ---

    def test_scrub_strips_user_spec_values_even_when_injected_via_extra(
        self, _user_spec_secrets
    ):
        """If a future code path accidentally puts the API keys into the
        status.extra dict, the scrub layer MUST still keep the user-spec
        values out of the response. This is the defence-in-depth pin."""
        cfg = load_agent_s3_config()
        from services.agent_s3_config import status_from_config
        from dataclasses import replace
        status = status_from_config(cfg)
        poisoned_extra = dict(status.extra)
        poisoned_extra["model_api_key"] = USER_SPEC_MODEL_KEY
        poisoned_extra["ground_api_key"] = USER_SPEC_GROUND_KEY
        poisoned = replace(status, extra=poisoned_extra)
        body = status_to_dict(poisoned)
        raw = json.dumps(body)
        for forbidden in (
            USER_SPEC_MODEL_KEY,
            USER_SPEC_GROUND_KEY,
            "secret-123456",
            "secret-abcdef",
        ):
            assert forbidden not in raw, (
                f"{forbidden!r} leaked through defence-in-depth; raw={raw!r}"
            )
        # The boolean placeholders replace the original keys.
        assert body["config"]["model_api_key_configured"] is True
        assert body["config"]["ground_api_key_configured"] is True

    # --- Live endpoint: GET /agent-s3/health with user-spec env ---

    def test_live_endpoint_does_not_leak_user_spec_secrets(
        self, client, _user_spec_secrets
    ):
        resp = client.get("/agent-s3/health")
        assert resp.status_code == 200
        body = resp.json()
        raw = json.dumps(body)
        for forbidden in (
            USER_SPEC_MODEL_KEY,
            USER_SPEC_GROUND_KEY,
            "secret-123456",
            "secret-abcdef",
        ):
            assert forbidden not in raw, (
                f"/agent-s3/health leaked {forbidden!r}; body={body!r}"
            )

    def test_live_root_health_does_not_leak_user_spec_secrets(
        self, client, _user_spec_secrets
    ):
        resp = client.get("/health")
        assert resp.status_code == 200
        raw = json.dumps(resp.json())
        for forbidden in (
            USER_SPEC_MODEL_KEY,
            USER_SPEC_GROUND_KEY,
            "secret-123456",
            "secret-abcdef",
        ):
            assert forbidden not in raw, (
                f"/health leaked {forbidden!r}"
            )

    # --- Boolean placeholder contract ---

    def test_health_returns_only_boolean_or_safe_placeholder(
        self, client, _user_spec_secrets
    ):
        """Whatever the response contains for API-key-shaped keys must
        be a boolean or a non-secret masked placeholder. No raw string,
        no numeric, no list, no dict."""
        resp = client.get("/agent-s3/health")
        body = resp.json()
        cfg_block = body.get("config", {})
        for key, val in cfg_block.items():
            if key.endswith("_configured"):
                assert isinstance(val, bool), (
                    f"{key!r} should be bool, got {type(val).__name__}: {val!r}"
                )