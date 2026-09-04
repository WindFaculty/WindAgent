"""HMAC token authentication contracts (issuer + authenticator)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from windagent.kernel.ids import ActorId
from windagent.kernel.time import FrozenClock, normalize_utc, utc_now
from windagent.platform.security import (
    TOKEN_KEY_SECRET_NAME,
    AuthenticationFailedError,
    HmacTokenAuthenticator,
    HmacTokenIssuer,
    Identity,
    IdentityKind,
    InMemoryIdentityStore,
    InMemorySecretStore,
    SecretValue,
    TokenConfigurationError,
)
from windagent.platform.security.authentication import _encode_claims

FROZEN_NOW = normalize_utc(utc_now())
SIGNING_KEY = "unit-test-signing-key"


def _stack(
    *, clock: object = None
) -> tuple[HmacTokenIssuer, HmacTokenAuthenticator, Identity]:
    secrets = InMemorySecretStore()
    secrets.put(TOKEN_KEY_SECRET_NAME, SecretValue(SIGNING_KEY))
    identities = InMemoryIdentityStore()
    identity = Identity(
        actor_id=ActorId.new(), kind=IdentityKind.SERVICE, name="svc"
    )
    identities.put(identity)
    issuer = HmacTokenIssuer(secrets, ttl_s=60.0)
    authenticator = HmacTokenAuthenticator(secrets, identities)
    if clock is not None:
        issuer.clock = clock  # type: ignore[assignment]
        authenticator.clock = clock  # type: ignore[assignment]
    return issuer, authenticator, identity


async def test_issued_token_authenticates_to_the_seeded_identity() -> None:
    issuer, authenticator, identity = _stack()
    token = await issuer.issue(identity.actor_id)
    assert (await authenticator.authenticate(token)) == identity


async def test_expired_tokens_are_rejected() -> None:
    frozen = FrozenClock(FROZEN_NOW)
    issuer, authenticator, identity = _stack(clock=frozen)
    token = await issuer.issue(identity.actor_id)
    authenticator.clock = FrozenClock(FROZEN_NOW + timedelta(seconds=61))
    with pytest.raises(AuthenticationFailedError):
        await authenticator.authenticate(token)


async def test_tampered_signatures_fail_the_constant_time_check() -> None:
    issuer, authenticator, identity = _stack()
    token = await issuer.issue(identity.actor_id)
    head, payload, signature = token.split(".")
    forged = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(AuthenticationFailedError):
        await authenticator.authenticate(f"{head}.{payload}.{forged}")


async def test_payloads_signed_for_another_actor_fail() -> None:
    issuer, authenticator, identity = _stack()
    token = await issuer.issue(identity.actor_id)
    head, _, signature = token.split(".")
    forged_payload = _b64(
        _encode_claims(
            ActorId.new(), FROZEN_NOW, FROZEN_NOW + timedelta(seconds=30)
        )
    )
    with pytest.raises(AuthenticationFailedError):
        await authenticator.authenticate(f"{head}.{forged_payload}.{signature}")


def _b64(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii")


@pytest.mark.parametrize(
    "token",
    ["", "   ", "not-a-token", "wa2.aaa.bbb", "wa1.!!!.bbb", "wa1.aaa"],
)
async def test_malformed_tokens_are_rejected(token: str) -> None:
    _, authenticator, _ = _stack()
    with pytest.raises(AuthenticationFailedError):
        await authenticator.authenticate(token)


async def test_unknown_and_inactive_identities_are_rejected() -> None:
    secrets = InMemorySecretStore()
    secrets.put(TOKEN_KEY_SECRET_NAME, SecretValue(SIGNING_KEY))
    identities = InMemoryIdentityStore()
    issuer = HmacTokenIssuer(secrets, ttl_s=60.0)
    authenticator = HmacTokenAuthenticator(secrets, identities)

    token = await issuer.issue(ActorId.new())
    with pytest.raises(AuthenticationFailedError):
        await authenticator.authenticate(token)

    inactive = Identity(
        actor_id=ActorId.new(),
        kind=IdentityKind.USER,
        name="ghost",
        active=False,
    )
    identities.put(inactive)
    token = await issuer.issue(inactive.actor_id)
    with pytest.raises(AuthenticationFailedError):
        await authenticator.authenticate(token)


async def test_missing_signing_secret_is_a_configuration_error() -> None:
    empty_secrets = InMemorySecretStore()
    identities = InMemoryIdentityStore()
    issuer = HmacTokenIssuer(empty_secrets)
    with pytest.raises(TokenConfigurationError):
        await issuer.issue(ActorId.new())

    secrets = InMemorySecretStore()
    secrets.put(TOKEN_KEY_SECRET_NAME, SecretValue("k"))
    authenticator = HmacTokenAuthenticator(empty_secrets, identities)
    # A structurally valid token (well-padded base64) reaches the key load;
    # malformed tokens fail earlier with AuthenticationFailedError.
    import base64

    filler = base64.urlsafe_b64encode(b"aaaa").decode("ascii")
    with pytest.raises(TokenConfigurationError):
        await authenticator.authenticate(f"wa1.{filler}.bbbb")


def test_issuer_rejects_invalid_ttl() -> None:
    secrets = InMemorySecretStore()
    with pytest.raises(ValueError):
        HmacTokenIssuer(secrets, ttl_s=0)
    with pytest.raises(TypeError):
        HmacTokenIssuer(secrets, ttl_s="60")  # type: ignore[arg-type]
