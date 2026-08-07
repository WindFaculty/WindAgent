"""Encryption utilities for credential storage.

AES-GCM encryption for API keys and secrets at rest.
Format: enc:v1:[kv<key_version>:]<base64_nonce>:<base64_ciphertext>

Phase 1 — G2.3:
- Removed the fixed zero-byte fallback key. Encryption now **requires** a valid
  key from ``WINDAGENT_ENCRYPTION_KEY`` (canonical) or the legacy alias
  ``WINDA_AGENT_ENCRYPTION_KEY`` (backward compatibility).
- ``decrypt()`` keeps its pass-through for legacy plaintext values so existing
  non-ciphertext rows remain readable during migration.

Stage 1 — GAP C (key rotation):
- Each ciphertext records the master ``key_version`` that encrypted it
  (``enc:v1:kv2:...``); legacy 4-part ``enc:v1:...`` values default to v1.
- ``encrypt(..., key_version=...)`` lets the caller pin a version; the current
  version comes from ``WINDAGENT_ENCRYPTION_KEY_VERSION`` (default ``1``).
- ``reencrypt_to_current()`` decrypts with the recorded version and re-encrypts
  with the current version — the on-read migration path for rotation.
"""

from __future__ import annotations
import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CANONICAL_KEY_ENV = "WINDAGENT_ENCRYPTION_KEY"
_LEGACY_KEY_ENV = "WINDA_AGENT_ENCRYPTION_KEY"
_CURRENT_KEY_VERSION_ENV = "WINDAGENT_ENCRYPTION_KEY_VERSION"
_DEFAULT_KEY_VERSION = 1
_FORMAT_PREFIX = "enc:v1:"


class EncryptionKeyMissingError(RuntimeError):
    """Raised when an encryption/decryption operation needs a key but none is configured."""


def _env_key_for_version(key_version: int) -> Optional[str]:
    """Per-version key env var, e.g. ``WINDAGENT_ENCRYPTION_KEY_V2``."""
    if key_version == _DEFAULT_KEY_VERSION:
        return os.environ.get(_CANONICAL_KEY_ENV) or os.environ.get(_LEGACY_KEY_ENV)
    return os.environ.get(f"{_CANONICAL_KEY_ENV}_V{key_version}")


def current_key_version() -> int:
    """Return the active master key version (from ``WINDAGENT_ENCRYPTION_KEY_VERSION``)."""
    raw = os.environ.get(_CURRENT_KEY_VERSION_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_KEY_VERSION
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_CURRENT_KEY_VERSION_ENV} must be an integer, got {raw!r}"
        ) from exc
    if version < 1:
        raise ValueError(f"{_CURRENT_KEY_VERSION_ENV} must be >= 1, got {version}")
    return version


def _decode_key(key_env: str) -> bytes:
    try:
        key = base64.b64decode(key_env)
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
        raise EncryptionKeyMissingError(
            f"{_CANONICAL_KEY_ENV} must be a valid base64-encoded key: {exc}"
        ) from exc
    if len(key) == 0:
        raise EncryptionKeyMissingError(
            f"{_CANONICAL_KEY_ENV} decoded to an empty key."
        )
    return key


def get_encryption_key(key_version: Optional[int] = None) -> bytes:
    """Return the configured AES-256 key, raising if absent (no fixed fallback).

    Args:
        key_version: Master key version to resolve. ``None`` means the current
            version (``WINDAGENT_ENCRYPTION_KEY_VERSION``). Per-version keys are
            read from ``WINDAGENT_ENCRYPTION_KEY_V<N>``; version 1 falls back to
            the canonical/legacy env vars.

    The key is base64-decoded. Raw 32-byte keys are also accepted for
    convenience. Raise ``EncryptionKeyMissingError`` when the environment does
    not provide a key — failing closed is required for secrets at rest.
    """
    version = key_version if key_version is not None else current_key_version()
    key_env = _env_key_for_version(version)
    if not key_env:
        raise EncryptionKeyMissingError(
            f"Encryption key missing for key_version={version}. Set "
            f"{_CANONICAL_KEY_ENV} (or legacy {_LEGACY_KEY_ENV}) to a "
            f"base64-encoded 32-byte AES-256 key; for key_version>1 also set "
            f"{_CANONICAL_KEY_ENV}_V{version}."
        )
    return _decode_key(key_env)


def key_version_of(ciphertext: str) -> Optional[int]:
    """Return the master key version recorded in a ciphertext, or ``None``.

    Returns ``None`` for plaintext (legacy pre-migration values). Legacy
    4-part ``enc:v1:nonce:ct`` values are reported as version 1.
    """
    if not ciphertext or not ciphertext.startswith(_FORMAT_PREFIX):
        return None
    parts = ciphertext.split(":")
    if len(parts) == 4:  # enc:v1:<nonce>:<ct> — legacy, treated as v1
        return _DEFAULT_KEY_VERSION
    if len(parts) == 5 and parts[2].startswith("kv"):
        try:
            return int(parts[2][2:])
        except ValueError:
            return None
    return None


def encrypt(plaintext: str, key_version: Optional[int] = None) -> str:
    """Encrypt a string using AES-GCM.

    Returns format: enc:v1:kv<key_version>:<base64_nonce>:<base64_ciphertext>.
    Requires a configured encryption key (G2.3 — no fixed fallback). The
    recorded ``key_version`` defaults to the current master key version.
    """
    version = key_version if key_version is not None else current_key_version()
    key = get_encryption_key(version)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    body = f"{base64.b64encode(nonce).decode()}:{base64.b64encode(ciphertext).decode()}"
    if version == _DEFAULT_KEY_VERSION:
        # Keep the legacy 4-part shape for v1 so existing readers keep working.
        return f"{_FORMAT_PREFIX}{body}"
    return f"{_FORMAT_PREFIX}kv{version}:{body}"


def decrypt(ciphertext: str) -> str:
    """Decrypt a string encrypted with encrypt().

    Expects format: enc:v1:[kv<key_version>:]<base64_nonce>:<base64_ciphertext>.
    Legacy plaintext values (no ``enc:v1:`` prefix) are passed through untouched.
    The recorded ``key_version`` selects the per-version master key.
    """
    if not ciphertext or not ciphertext.startswith(_FORMAT_PREFIX):
        return ciphertext  # Assume already plaintext or legacy format

    parts = ciphertext.split(":")
    if len(parts) == 4:
        version = _DEFAULT_KEY_VERSION
        _, _fmt, nonce_b64, ct_b64 = parts
    elif len(parts) == 5 and parts[2].startswith("kv"):
        _, _fmt, kv_part, nonce_b64, ct_b64 = parts
        try:
            version = int(kv_part[2:])
        except ValueError:
            return ciphertext
    else:
        return ciphertext

    key = get_encryption_key(version)
    aesgcm = AESGCM(key)
    nonce = base64.b64decode(nonce_b64)
    ct = base64.b64decode(ct_b64)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")


def reencrypt_to_current(ciphertext: str) -> str:
    """Re-encrypt with the current master key version (on-read migration).

    Plaintext legacy values are returned unchanged (they are migrated by the
    data lane, not here). Ciphertext already at the current version is returned
    as-is. Otherwise the value is decrypted with its recorded version and
    re-encrypted with ``current_key_version()``.
    """
    if not ciphertext or not ciphertext.startswith(_FORMAT_PREFIX):
        return ciphertext
    recorded = key_version_of(ciphertext)
    current = current_key_version()
    if recorded is None or recorded >= current:
        return ciphertext
    plaintext = decrypt(ciphertext)
    return encrypt(plaintext, key_version=current)
