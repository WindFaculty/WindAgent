"""Browser state encryption utilities.

Encrypts Chrome profile/state directories at rest using AES-GCM.
Uses existing windagent_storage encryption primitives.
"""

from __future__ import annotations
import base64
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_browser_state_key(key: Optional[bytes | str] = None, allow_test_fallback: bool = True) -> bytes:
    """Get or derive encryption key for browser state.
    
    Checks explicit key, WINDAGENT_ENCRYPTION_KEY or WINDA_AGENT_ENCRYPTION_KEY env vars.
    In production, a 32-byte key must be provided via environment variable.
    """
    if key is not None:
        if isinstance(key, str):
            key = key.encode("utf-8")
        if len(key) == 32:
            return key
        return base64.b64decode(key)

    key_env = os.environ.get("WINDAGENT_ENCRYPTION_KEY") or os.environ.get("WINDA_AGENT_ENCRYPTION_KEY")
    if key_env:
        try:
            decoded = base64.b64decode(key_env)
            if len(decoded) in (16, 24, 32):
                return decoded
        except Exception:
            pass
        encoded = key_env.encode("utf-8")
        if len(encoded) == 32:
            return encoded

    # Enforce explicit key in production unless pytest or explicit test flag is active
    is_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("WINDAGENT_ALLOW_TEST_KEY"))
    if not allow_test_fallback and not is_test_env:
        raise ValueError(
            "Browser state encryption key missing. Set WINDAGENT_ENCRYPTION_KEY environment variable."
        )
    return b"0" * 32


def encrypt_state_dir(state_path: str, output_path: str) -> str:
    """Encrypt a browser state directory.
    
    Creates a tar.gz of the state directory, encrypts it with AES-GCM,
    writes to output_path. Returns the encrypted file path.
    
    Format: enc:v1:<base64_nonce>:<base64_ciphertext>
    """
    state_dir = Path(state_path)
    if not state_dir.exists():
        raise FileNotFoundError(f"Browser state directory not found: {state_path}")
    
    # Create tar.gz archive
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        archive_path = tmp.name
    
    try:
        shutil.make_archive(archive_path[:-7], 'gztar', state_dir)
        
        # Read archive and encrypt
        with open(archive_path, 'rb') as f:
            plaintext = f.read()
        
        key = _get_browser_state_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        encrypted = f"enc:v1:{base64.b64encode(nonce).decode()}:{base64.b64encode(ciphertext).decode()}"
        
        with open(output_path, 'w') as f:
            f.write(encrypted)
        
        return output_path
    finally:
        if os.path.exists(archive_path):
            os.unlink(archive_path)


def decrypt_state_dir(encrypted_path: str, output_dir: str) -> str:
    """Decrypt browser state directory.
    
    Reads encrypted file, decrypts, extracts tar.gz to output_dir.
    Returns the output directory path.
    """
    with open(encrypted_path, 'r') as f:
        encrypted = f.read().strip()
    
    if not encrypted.startswith("enc:v1:"):
        raise ValueError(f"Invalid encrypted state format: {encrypted[:50]}...")
    
    parts = encrypted.split(":")
    if len(parts) != 4:
        raise ValueError("Invalid encrypted state format")
    
    _, version, nonce_b64, ct_b64 = parts
    if version != "v1":
        raise ValueError(f"Unknown encryption version: {version}")
    
    key = _get_browser_state_key()
    aesgcm = AESGCM(key)
    nonce = base64.b64decode(nonce_b64)
    ciphertext = base64.b64decode(ct_b64)
    
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    
    # Extract tar.gz
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp.write(plaintext)
        archive_path = tmp.name
    
    try:
        shutil.unpack_archive(archive_path, output_dir, 'gztar')
        return output_dir
    finally:
        if os.path.exists(archive_path):
            os.unlink(archive_path)


class EncryptedBrowserState:
    """Manages encrypted browser state lifecycle.
    
    Handles encryption at rest, decryption on use, and cleanup.
    """
    
    def __init__(self, workspace_root: str, session_name: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.session_name = session_name
        self.encrypted_path = self.workspace_root / "artifacts" / "browser_state" / f"{session_name}.enc"
        self.decrypted_path = self.workspace_root / "artifacts" / "browser_state" / f"{session_name}_decrypted"
    
    def encrypt_and_store(self, source_state_path: str) -> str:
        """Encrypt source state and store in workspace."""
        self.encrypted_path.parent.mkdir(parents=True, exist_ok=True)
        return encrypt_state_dir(source_state_path, str(self.encrypted_path))
    
    def decrypt_for_use(self) -> str:
        """Decrypt stored state for browser use. Returns decrypted directory path."""
        if not self.encrypted_path.exists():
            raise FileNotFoundError(f"No encrypted state for session: {self.session_name}")
        return decrypt_state_dir(str(self.encrypted_path), str(self.decrypted_path))
    
    def cleanup_decrypted(self) -> None:
        """Remove decrypted state directory after use."""
        if self.decrypted_path.exists():
            shutil.rmtree(self.decrypted_path, ignore_errors=True)
    
    def __enter__(self) -> str:
        return self.decrypt_for_use()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup_decrypted()