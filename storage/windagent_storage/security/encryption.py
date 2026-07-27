"""Encryption utilities for credential storage.

Simple AES-GCM encryption for API keys and secrets.
Format: enc:v1:<nonce>:<ciphertext>
"""

from __future__ import annotations
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    """Get or derive encryption key from environment."""
    key_env = os.environ.get("WINDA_AGENT_ENCRYPTION_KEY")
    if key_env:
        # Decode base64 key
        return base64.b64decode(key_env)
    # Fallback: derive from a fixed salt (for testing only)
    # In production, WINDA_AGENT_ENCRYPTION_KEY must be set
    return b"0" * 32


def encrypt(plaintext: str) -> str:
    """Encrypt a string using AES-GCM.

    Returns format: enc:v1:<base64_nonce>:<base64_ciphertext>
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"enc:v1:{base64.b64encode(nonce).decode()}:{base64.b64encode(ciphertext).decode()}"


def decrypt(ciphertext: str) -> str:
    """Decrypt a string encrypted with encrypt().

    Expects format: enc:v1:<base64_nonce>:<base64_ciphertext>
    """
    if not ciphertext or not ciphertext.startswith("enc:v1:"):
        return ciphertext  # Assume already plaintext or legacy format

    parts = ciphertext.split(":")
    if len(parts) != 4:
        return ciphertext

    _, version, nonce_b64, ct_b64 = parts
    if version != "v1":
        return ciphertext

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = base64.b64decode(nonce_b64)
    ct = base64.b64decode(ct_b64)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")
