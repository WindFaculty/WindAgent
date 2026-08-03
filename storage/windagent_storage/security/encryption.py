"""Encryption utilities for credential storage.

AES-GCM encryption for API keys and secrets at rest.
Format: enc:v1:<base64_nonce>:<base64_ciphertext>

Phase 1 — G2.3:
- Removed the fixed zero-byte fallback key. Encryption now **requires** a valid
  key from ``WINDAGENT_ENCRYPTION_KEY`` (canonical) or the legacy alias
  ``WINDA_AGENT_ENCRYPTION_KEY`` (backward compatibility).
- ``decrypt()`` keeps its pass-through for legacy plaintext values so existing
  non-ciphertext rows remain readable during migration.
"""

from __future__ import annotations
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CANONICAL_KEY_ENV = "WINDAGENT_ENCRYPTION_KEY"
_LEGACY_KEY_ENV = "WINDA_AGENT_ENCRYPTION_KEY"


class EncryptionKeyMissingError(RuntimeError):
    """Raised when an encryption/decryption operation needs a key but none is configured."""


def get_encryption_key() -> bytes:
    """Return the configured AES-256 key, raising if absent (no fixed fallback).

    The key is base64-decoded. Raw 32-byte keys are also accepted for
    convenience. Raise ``EncryptionKeyMissingError`` when the environment does
    not provide a key — failing closed is required for secrets at rest.
    """
    key_env = os.environ.get(_CANONICAL_KEY_ENV) or os.environ.get(_LEGACY_KEY_ENV)
    if not key_env:
        raise EncryptionKeyMissingError(
            f"Encryption key missing. Set {_CANONICAL_KEY_ENV} (or legacy "
            f"{_LEGACY_KEY_ENV}) to a base64-encoded 32-byte AES-256 key."
        )
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


def encrypt(plaintext: str) -> str:
    """Encrypt a string using AES-GCM.

    Returns format: enc:v1:<base64_nonce>:<base64_ciphertext>.
    Requires a configured encryption key (G2.3 — no fixed fallback).
    """
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"enc:v1:{base64.b64encode(nonce).decode()}:{base64.b64encode(ciphertext).decode()}"


def decrypt(ciphertext: str) -> str:
    """Decrypt a string encrypted with encrypt().

    Expects format: enc:v1:<base64_nonce>:<base64_ciphertext>.
    Legacy plaintext values (no ``enc:v1:`` prefix) are passed through untouched.
    """
    if not ciphertext or not ciphertext.startswith("enc:v1:"):
        return ciphertext  # Assume already plaintext or legacy format

    parts = ciphertext.split(":")
    if len(parts) != 4:
        return ciphertext

    _, version, nonce_b64, ct_b64 = parts
    if version != "v1":
        return ciphertext

    key = get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = base64.b64decode(nonce_b64)
    ct = base64.b64decode(ct_b64)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")
