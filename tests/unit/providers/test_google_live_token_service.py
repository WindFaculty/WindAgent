"""Unit tests for the Google Live ephemeral token service (Phase 5).

Covers the REAL remote path (POST /v1beta/auth_tokens with an injected
transport — no network) and its fail-closed error contract: no response
content may leak into errors, non-200 or malformed responses raise
EphemeralTokenMintError.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from windagent_providers.google.live.token_service import (
    EphemeralToken,
    EphemeralTokenMintError,
    EphemeralTokenService,
    GOOGLE_AUTH_TOKENS_ENDPOINT,
)


def _capturing_post(responder):
    """Wrap an async responder so the request it saw can be asserted."""
    seen = {}

    async def post(url, *, json=None, headers=None):
        seen.update({"url": url, "json": json, "headers": headers})
        return responder(json, headers)

    post.seen = seen
    return post


@pytest.mark.asyncio
async def test_mint_remote_posts_locked_request_and_returns_named_token():
    service = EphemeralTokenService(provider_id="google", model_id="gemini-3.1-flash-live-preview")

    def responder(json, headers):
        assert headers["x-goog-api-key"] == "test-google-api-key"
        assert json["uses"] == 1
        assert json["liveConnectConstraints"]["model"] == "models/gemini-3.1-flash-live-preview"
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"name": "tokens/abc123XYZdef456GHI789jkl012MNO345"},
        )

    post = _capturing_post(responder)
    token = await service.mint_remote(
        api_key="test-google-api-key",
        session_id="ldir_test",
        execution_plan_hash="a" * 64,
        http_post=post,
    )

    assert isinstance(token, EphemeralToken)
    assert token.token == "tokens/abc123XYZdef456GHI789jkl012MNO345"
    assert token.session_id == "ldir_test"
    assert token.execution_plan_hash == "a" * 64
    assert token.ttl_seconds == service.DEFAULT_TTL_SECONDS
    assert post.seen["url"] == GOOGLE_AUTH_TOKENS_ENDPOINT


@pytest.mark.asyncio
async def test_mint_remote_rejects_http_error_without_leaking_body():
    service = EphemeralTokenService()

    def responder(json, headers):
        return SimpleNamespace(
            status_code=403, json=lambda: {"error": "SECRET-MUST-NOT-LEAK"}
        )

    with pytest.raises(EphemeralTokenMintError) as excinfo:
        await service.mint_remote(
            api_key="k",
            session_id="s",
            execution_plan_hash="b" * 64,
            http_post=_capturing_post(responder),
        )
    assert excinfo.value.status == 403
    # Error text carries no response content.
    assert "SECRET-MUST-NOT-LEAK" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_mint_remote_rejects_malformed_success_response():
    service = EphemeralTokenService()
    for bad_body in ({}, {"name": ""}, {"token": "short"}):
        def responder(json, headers, _body=bad_body):
            return SimpleNamespace(status_code=200, json=lambda: _body)

        with pytest.raises(EphemeralTokenMintError):
            await service.mint_remote(
                api_key="k",
                session_id="s",
                execution_plan_hash="c" * 64,
                http_post=_capturing_post(responder),
            )


@pytest.mark.asyncio
async def test_local_fallback_envelope_still_well_formed():
    """The local envelope keeps hermetic CI verifiable without credentials."""
    service = EphemeralTokenService()
    token = service.mint(execution_plan_hash="d" * 64, session_id="s")
    assert len(token.token) >= 32
    assert not token.is_expired
