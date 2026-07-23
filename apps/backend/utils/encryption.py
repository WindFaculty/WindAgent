"""Encryption utilities for sensitive data at rest."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _get_encryption_key() -> str:
    """Get encryption key from environment variable.

    Expected format: base64-encoded 32-byte key (Fernet key).
    Environment variable: WINDAGENT_SECRET_ENCRYPTION_KEY

    Returns:
        str: The encryption key (base64-encoded string).

    Raises:
        ValueError: If the environment variable is not set or invalid.
    """
    key_b64 = os.environ.get("WINDAGENT_SECRET_ENCRYPTION_KEY")
    
    # Check if the environment variable key is valid
    is_valid = False
    if key_b64 and key_b64 != "%KEY%":
        try:
            Fernet(key_b64)
            is_valid = True
        except Exception:
            pass

    # If not valid, attempt to read from key.txt
    if not is_valid:
        key_path = Path(__file__).resolve().parent.parent / "key.txt"
        if key_path.exists():
            try:
                fallback_key = key_path.read_text(encoding="utf-8").strip()
                if fallback_key:
                    # Validate fallback key
                    Fernet(fallback_key)
                    key_b64 = fallback_key
                    os.environ["WINDAGENT_SECRET_ENCRYPTION_KEY"] = key_b64
                    is_valid = True
            except Exception:
                pass

    if not is_valid or not key_b64:
        raise ValueError(
            "Encryption key not set or invalid. Set WINDAGENT_SECRET_ENCRYPTION_KEY environment variable."
        )
        
    return key_b64


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string using Fernet (AES-128 in CBC mode with HMAC).

    Args:
        plaintext: The string to encrypt.

    Returns:
        str: Encrypted string with prefix 'enc:v1:' to indicate version.

    Raises:
        ValueError: If encryption key is not set or invalid.
    """
    if not plaintext:
        return plaintext
    try:
        f = Fernet(_get_encryption_key())
        encrypted_bytes = f.encrypt(plaintext.encode("utf-8"))
        # Return with version prefix for future rotation support
        return f"enc:v1:{encrypted_bytes.decode('utf-8')}"
    except Exception as exc:
        raise ValueError(f"Encryption failed: {exc}") from exc


def decrypt(encrypted_str: str) -> str:
    """Decrypt an encrypted string.

    Args:
        encrypted_str: The encrypted string (may have 'enc:v1:' prefix).

    Returns:
        str: The decrypted plaintext.

    Raises:
        ValueError: If decryption fails (invalid token, missing key, etc.).
    """
    if not encrypted_str:
        return encrypted_str
    # If it doesn't have the prefix, assume it's plaintext (for backward compatibility during migration)
    if not encrypted_str.startswith("enc:v1:"):
        return encrypted_str
    try:
        f = Fernet(_get_encryption_key())
        encrypted_bytes = encrypted_str[7:].encode("utf-8")  # remove 'enc:v1:' prefix
        decrypted_bytes = f.decrypt(encrypted_bytes)
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(f"Invalid encryption token: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Decryption failed: {exc}") from exc


def is_encrypted(value: str) -> bool:
    """Check if a string appears to be encrypted (has our version prefix)."""
    return isinstance(value, str) and value.startswith("enc:v1:")


def mask_api_key(api_key: str, visible_chars: int = 4) -> str:
    """Mask an API key for display, showing only the last few characters.

    Args:
        api_key: The API key string (plain or encrypted).
        visible_chars: Number of characters to show at the end.

    Returns:
        str: Masked string (e.g., '****abcd').
    """
    if not api_key:
        return ""
    # If it's encrypted, we still mask the encrypted string (it's still sensitive)
    if len(api_key) <= visible_chars:
        return "*" * len(api_key)
    return "*" * (len(api_key) - visible_chars) + api_key[-visible_chars:]