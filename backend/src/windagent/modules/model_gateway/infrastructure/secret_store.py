"""Durable, encrypted-at-rest secret store for provider credentials.

Preserved from the frozen ``storage/windagent_storage/security/encryption.py``
semantics: AES-256-GCM with the ``enc:v<version>:<nonce>:<ciphertext>``
envelope, a base64-encoded master key read from
``WINDAGENT_MODEL_GATEWAY_ENCRYPTION_KEY`` (per version via
``..._ENCRYPTION_KEY_V<N>``), and fail-closed behavior when the key is
missing — no fallback key, no plaintext storage, ever.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import CursorResult

from windagent.kernel.errors import DomainError
from windagent.platform.security import SecretStore, SecretValue

from .tables import secrets_table

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

CANONICAL_KEY_ENV = "WINDAGENT_MODEL_GATEWAY_ENCRYPTION_KEY"
CURRENT_KEY_VERSION_ENV = "WINDAGENT_MODEL_GATEWAY_ENCRYPTION_KEY_VERSION"
DEFAULT_KEY_VERSION = 1
CIPHERTEXT_ENVELOPE = re.compile(r"^enc:v(\d+):([A-Za-z0-9+/=]+):([A-Za-z0-9+/=]+)$")
NONCE_BYTES = 12
AES_KEY_SIZES = (16, 24, 32)


class EncryptionKeyMissingError(DomainError):
    """No encryption key is configured; refusing to store or read secrets."""

    default_code = "encryption_key_missing"


def current_key_version() -> int:
    """The active master key version (defaults to 1)."""
    raw = os.environ.get(CURRENT_KEY_VERSION_ENV)
    if raw is None:
        return DEFAULT_KEY_VERSION
    try:
        version = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{CURRENT_KEY_VERSION_ENV} must be an integer, got {raw!r}"
        ) from exc
    if version < 1:
        raise ValueError(f"{CURRENT_KEY_VERSION_ENV} must be >= 1, got {version}")
    return version


def _env_key_name(key_version: int) -> str:
    if key_version == DEFAULT_KEY_VERSION:
        return CANONICAL_KEY_ENV
    return f"{CANONICAL_KEY_ENV}_V{key_version}"


def get_encryption_key(key_version: int | None = None) -> bytes:
    """Resolve and decode the AES master key; fail closed when absent."""
    version = key_version if key_version is not None else current_key_version()
    env_name = _env_key_name(version)
    raw = os.environ.get(env_name)
    if not raw:
        raise EncryptionKeyMissingError(
            f"{env_name} is not configured; provider credentials cannot be "
            "stored or read without it",
            context={"key_version": version},
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001 - binascii.Error family
        raise EncryptionKeyMissingError(
            f"{env_name} must be a valid base64-encoded AES key",
            context={"key_version": version},
        ) from exc
    if len(key) not in AES_KEY_SIZES:
        raise EncryptionKeyMissingError(
            f"{env_name} must decode to 16, 24, or 32 bytes",
            context={"key_version": version},
        )
    return key


def encrypt_secret(plaintext: str, *, key_version: int | None = None) -> tuple[str, int]:
    """Encrypt to the ``enc:v<version>:...`` envelope; returns (ciphertext, version)."""
    version = key_version if key_version is not None else current_key_version()
    key = get_encryption_key(version)
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext = (
        f"enc:v{version}:"
        f"{base64.b64encode(nonce).decode()}:{base64.b64encode(sealed).decode()}"
    )
    return ciphertext, version


def decrypt_secret(ciphertext: str, *, key_version: int | None = None) -> str:
    """Decrypt an ``enc:v<version>:...`` envelope (fail closed without the key)."""
    match = CIPHERTEXT_ENVELOPE.match(ciphertext)
    if match is None:
        raise DomainError(
            "stored secret is not a recognized ciphertext envelope",
            code="validation_error",
        )
    envelope_version = int(match.group(1))
    resolved = key_version if key_version is not None else envelope_version
    key = get_encryption_key(resolved)
    nonce = base64.b64decode(match.group(2))
    sealed = base64.b64decode(match.group(3))
    return AESGCM(key).decrypt(nonce, sealed, None).decode("utf-8")


@dataclass(slots=True)
class EncryptedSecretStore(SecretStore):
    """Durable secret store backed by the ``model_gateway_secrets`` table.

    Each operation runs in its own short transaction via the injected
    async session factory; the store never joins domain transactions.
    """

    session_factory: async_sessionmaker[AsyncSession]
    key_version: int | None = None

    async def read(self, name: str) -> SecretValue | None:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(secrets_table.c.ciphertext).where(
                        secrets_table.c.secret_name == name
                    )
                )
            ).first()
        if row is None:
            return None
        return SecretValue(decrypt_secret(str(row[0])))

    async def write(self, name: str, value: SecretValue) -> None:
        ciphertext, version = encrypt_secret(
            value.reveal(), key_version=self.key_version
        )
        async with self.session_factory() as session:
            existing = (
                await session.execute(
                    select(secrets_table.c.secret_name).where(
                        secrets_table.c.secret_name == name
                    )
                )
            ).first()
            if existing is None:
                await session.execute(
                    insert(secrets_table).values(
                        secret_name=name,
                        ciphertext=ciphertext,
                        key_version=version,
                        created_at=func.now(),
                    )
                )
            else:
                await session.execute(
                    update(secrets_table)
                    .where(secrets_table.c.secret_name == name)
                    .values(ciphertext=ciphertext, key_version=version)
                )
            await session.commit()

    async def delete(self, name: str) -> bool:
        async with self.session_factory() as session:
            outcome = await session.execute(
                delete(secrets_table).where(secrets_table.c.secret_name == name)
            )
            await session.commit()
        return bool(cast("CursorResult[Any]", outcome).rowcount)


@dataclass(slots=True)
class ChainedSecretStore(SecretStore):
    """Reads through a chain of stores; writes land on the primary.

    The composition root chains the read-only environment store (provisioned
    signing material) with the durable encrypted store (API-managed provider
    credentials).  Reads try each store in order; writes and deletes go to
    ``primary`` only.
    """

    primary: SecretStore
    fallbacks: tuple[SecretStore, ...] = ()

    async def read(self, name: str) -> SecretValue | None:
        for store in (self.primary, *self.fallbacks):
            value = await store.read(name)
            if value is not None:
                return value
        return None

    async def write(self, name: str, value: SecretValue) -> None:
        await self.primary.write(name, value)

    async def delete(self, name: str) -> bool:
        return await self.primary.delete(name)
