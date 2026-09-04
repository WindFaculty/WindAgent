"""Credential verification: HMAC-signed bearer tokens (stdlib only).

Token format (version 1, deliberately simple and dependency-free):

```text
wa1.<base64url(payload_json)>.<base64url(hmac_sha256(key, "wa1." + payload))>
```

The signing key lives in the ``SecretStore`` under ``auth/token_key``;
verification is constant-time, expiry is checked against the kernel clock,
and the presented ``ActorId`` must resolve to an active identity before
authentication succeeds.  A standard JWT library can replace this codec
behind the same ``Authenticator`` protocol without touching any caller.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, Protocol, runtime_checkable

from windagent.kernel.ids import ActorId
from windagent.kernel.time import Clock, SystemClock, normalize_utc

from .contracts import SecretStore
from .errors import AuthenticationFailedError, TokenConfigurationError
from .identity import Identity, IdentityStore

TOKEN_KEY_SECRET_NAME: Final[str] = "auth/token_key"
DEFAULT_TOKEN_TTL_S: Final[float] = 3600.0
_TOKEN_PREFIX: Final[str] = "wa1"
_SIGNED_PREFIX: Final[bytes] = b"wa1."


@runtime_checkable
class Authenticator(Protocol):
    """Verifies presented credentials and returns the identity behind them."""

    async def authenticate(self, token: str) -> Identity:
        """Return the identity for valid credentials; raise otherwise."""


def _b64encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii")


def _b64decode(encoded: str) -> bytes:
    try:
        return urlsafe_b64decode(encoded.encode("ascii"))
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise AuthenticationFailedError("authentication failed") from error


async def _load_key(secrets: SecretStore, secret_name: str) -> bytes:
    value = await secrets.read(secret_name)
    if value is None:
        raise TokenConfigurationError(
            f"token signing secret {secret_name!r} is not configured"
        )
    return value.reveal().encode("utf-8")


def _signature(key: bytes, payload: bytes) -> str:
    digest = hmac.new(key, _SIGNED_PREFIX + payload, hashlib.sha256).digest()
    return _b64encode(digest)


@dataclass(frozen=True, slots=True)
class _TokenClaims:
    actor_id: ActorId
    expires_at: datetime


def _encode_claims(actor_id: ActorId, issued_at: datetime, expires_at: datetime) -> bytes:
    return json.dumps(
        {
            "actor_id": actor_id.value,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_claims(payload: bytes) -> _TokenClaims:
    try:
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict):
            raise TypeError("token payload must be an object")
        return _TokenClaims(
            actor_id=ActorId(document["actor_id"]),
            expires_at=normalize_utc(datetime.fromisoformat(document["expires_at"])),
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        raise AuthenticationFailedError("authentication failed") from error


@dataclass(slots=True)
class HmacTokenIssuer:
    """Mints version-1 bearer tokens (CLI, tests, service bootstrap)."""

    secrets: SecretStore
    clock: Clock = field(default_factory=SystemClock)
    ttl_s: float = DEFAULT_TOKEN_TTL_S
    secret_name: str = TOKEN_KEY_SECRET_NAME

    def __post_init__(self) -> None:
        _validate_ttl(self.ttl_s)

    async def issue(self, actor_id: ActorId, *, ttl_s: float | None = None) -> str:
        """Return a signed token for ``actor_id``."""
        if not isinstance(actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId")
        effective_ttl = self.ttl_s if ttl_s is None else ttl_s
        _validate_ttl(effective_ttl)
        key = await _load_key(self.secrets, self.secret_name)
        now = normalize_utc(self.clock.now())
        payload = _encode_claims(
            actor_id, now, now + timedelta(seconds=effective_ttl)
        )
        return f"{_TOKEN_PREFIX}.{_b64encode(payload)}.{_signature(key, payload)}"


@dataclass(slots=True)
class HmacTokenAuthenticator:
    """Verifies version-1 tokens against the secret store and identities."""

    secrets: SecretStore
    identities: IdentityStore
    clock: Clock = field(default_factory=SystemClock)
    secret_name: str = TOKEN_KEY_SECRET_NAME

    async def authenticate(self, token: str) -> Identity:
        if not isinstance(token, str) or not token.strip():
            raise AuthenticationFailedError("authentication failed")
        parts = token.strip().split(".")
        if len(parts) != 3 or parts[0] != _TOKEN_PREFIX:
            raise AuthenticationFailedError("authentication failed")

        payload = _b64decode(parts[1])
        key = await _load_key(self.secrets, self.secret_name)
        if not hmac.compare_digest(_signature(key, payload), parts[2]):
            raise AuthenticationFailedError("authentication failed")

        claims = _decode_claims(payload)
        if claims.expires_at <= normalize_utc(self.clock.now()):
            raise AuthenticationFailedError("authentication failed")

        identity = await self.identities.get(claims.actor_id)
        if identity is None or not identity.active:
            raise AuthenticationFailedError("authentication failed")
        return identity


def _validate_ttl(ttl_s: float) -> None:
    if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)):
        raise TypeError("ttl_s must be a number")
    if ttl_s <= 0:
        raise ValueError("ttl_s must be positive")
