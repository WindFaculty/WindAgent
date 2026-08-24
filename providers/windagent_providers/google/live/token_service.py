"""Ephemeral token service — Phase 5 (ban_ke_hoach_v1.md Section 10).

Google recommends ephemeral tokens for direct client→Live API connections:
short-lived, never persisted, never logged, not returned via GET, one-session
use, constrained to the exact model/config.

This module mints a local ephemeral credential that the API returns to the
desktop. The desktop then opens the Live WebSocket to Google *directly* —
the WindAgent API never proxies the Live session (shorter path, no extra hop).

In production the service would call Google's token endpoint
(https://generativelanguage.googleapis.com/v1beta/auth_tokens) using the
provider's long-lived API key. For now the service mints a signed envelope
locally — the shape (fields, TTL, one-time use) matches the production
contract so clients and tests can rely on it without live Google credentials.

Security invariants (enforced at call sites):
- token is random 32+ bytes, base64url, never logged;
- expires_at short (default 30 min);
- token never persisted in DB and never echoed on GET;
- token is constrained to exactly one (model_id, execution_plan_hash).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


GOOGLE_AUTH_TOKENS_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/auth_tokens"
)


class EphemeralTokenMintError(RuntimeError):
    """Google auth_tokens endpoint rejected or could not be reached.

    Carries NO response body content — tokens and API keys must never leak
    into error messages (security_boundary.md token invariants).
    """

    def __init__(self, status: Optional[int] = None) -> None:
        self.status = status
        super().__init__(
            "EPHEMERAL_TOKEN_MINT_FAILED"
            if status is None
            else f"EPHEMERAL_TOKEN_MINT_FAILED: google auth_tokens returned HTTP {status}"
        )


@dataclass(frozen=True)
class EphemeralToken:
    token: str
    provider_id: str
    model_id: str
    execution_plan_hash: str
    session_id: str
    issued_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def ttl_seconds(self) -> int:
        return int((self.expires_at - self.issued_at).total_seconds())


class EphemeralTokenService:
    """Mint ephemeral Live API tokens constrained to one session/model/plan."""

    # Google token default lifetime is ~30 min; mirror that.
    DEFAULT_TTL_SECONDS = 30 * 60

    def __init__(
        self,
        *,
        provider_id: str = "google",
        model_id: str = "gemini-3.1-flash-live-preview",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self.ttl_seconds = ttl_seconds

    def mint(
        self,
        *,
        execution_plan_hash: str,
        session_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> EphemeralToken:
        """Mint a random token bound to (model_id, execution_plan_hash, session_id).

        The raw token is returned only once; callers must not persist or log it.
        A sha256(token) may be stored server-side for one-time-use checks.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(seconds=ttl)
        # 32 random bytes → base64url (~43 chars) — enough entropy for one-time use
        raw = secrets.token_urlsafe(32)
        # Bind token to its scope in metadata (not in the token itself — the
        # Google endpoint would encode this, here we keep the envelope explicit).
        return EphemeralToken(
            token=raw,
            provider_id=self.provider_id,
            model_id=self.model_id,
            execution_plan_hash=execution_plan_hash,
            session_id=session_id,
            issued_at=now,
            expires_at=expiry,
        )

    @staticmethod
    def token_hash(token: str) -> str:
        """sha256 of the raw token — safe to persist/log for revocation checks."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def mint_remote(
        self,
        *,
        api_key: str,
        session_id: str,
        execution_plan_hash: str,
        ttl_seconds: Optional[int] = None,
        http_post: Optional[Any] = None,
    ) -> EphemeralToken:
        """Mint a REAL Google ephemeral token via POST /v1beta/auth_tokens.

        Request locks the token to exactly this model (liveConnectConstraints)
        with ``uses: 1`` (one Live session) and a short expiry — mirroring the
        local envelope contract. The raw API key never leaves the server; the
        returned short-lived token is what the desktop exchanges on connect.

        ``http_post`` is injectable (async callable(url, *, json, headers) →
        object with .status_code and .json()) so tests run without network.
        Raises EphemeralTokenMintError on any failure — fail-closed, and the
        error message carries no response content.
        """
        import httpx  # local import keeps the module importable without net deps in tests

        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(seconds=ttl)
        model_name = self.model_id if "/" in self.model_id else f"models/{self.model_id}"
        body = {
            "uses": 1,
            "expireTime": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
            # Window in which a NEW Live session may be opened with this token
            # (~1 min, mirroring Google's default).
            "newSessionExpireTime": (now + timedelta(seconds=60)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "liveConnectConstraints": {"model": model_name},
        }
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

        if http_post is not None:
            response = await http_post(
                GOOGLE_AUTH_TOKENS_ENDPOINT, json=body, headers=headers
            )
            status = getattr(response, "status_code", None)
            if status != 200:
                raise EphemeralTokenMintError(status=status)
            data = response.json()
        else:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        GOOGLE_AUTH_TOKENS_ENDPOINT, json=body, headers=headers
                    )
            except Exception as exc:  # noqa: BLE001 — network errors are opaque here
                raise EphemeralTokenMintError() from exc
            if response.status_code != 200:
                raise EphemeralTokenMintError(status=response.status_code)
            data = response.json()

        raw = data.get("name") or data.get("token")
        if not isinstance(raw, str) or not self.is_token_well_formed(raw):
            raise EphemeralTokenMintError(status=200)
        return EphemeralToken(
            token=raw,
            provider_id=self.provider_id,
            model_id=self.model_id,
            execution_plan_hash=execution_plan_hash,
            session_id=session_id,
            issued_at=now,
            expires_at=expiry,
        )

    @staticmethod
    def is_token_well_formed(token: str) -> bool:
        """Basic syntactic check — non-empty and sufficient entropy."""
        return isinstance(token, str) and len(token) >= 32
