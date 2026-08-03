"""Browser state retention and cleanup policies."""

from __future__ import annotations
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class BrowserStateRetentionPolicy:
    """Policy for browser state retention and cleanup."""
    
    # Maximum age of browser state before cleanup (seconds)
    max_age_seconds: float = 86400 * 7  # 7 days default
    
    # Maximum number of state files to keep
    max_states: int = 100
    
    # Maximum total size of state files (bytes)
    max_total_size_bytes: int = 500 * 1024 * 1024  # 500 MB default
    
    # Cleanup interval
    cleanup_interval_seconds: float = 86400  # Daily
    
    @classmethod
    def from_env(cls, env_prefix: str = "WINDA_AGENT_BROWSER_STATE_") -> "BrowserStateRetentionPolicy":
        """Create policy from environment variables."""
        return cls(
            max_age_seconds=float(os.environ.get(f"{env_prefix}MAX_AGE_SECONDS", 86400 * 7)),
            max_states=int(os.environ.get(f"{env_prefix}MAX_STATES", 100)),
            max_total_size_bytes=int(os.environ.get(f"{env_prefix}MAX_TOTAL_SIZE_BYTES", 500 * 1024 * 1024)),
            cleanup_interval_seconds=float(os.environ.get(f"{env_prefix}CLEANUP_INTERVAL_SECONDS", 86400)),
        )


@dataclass
class BrowserStateMetadata:
    """Metadata for a browser state file."""
    session_name: str
    encrypted_path: Path
    created_at: float
    last_accessed: float
    size_bytes: int
    profile_used: Optional[str] = None
    authenticated: bool = False


class BrowserStateManager:
    """Manages browser state lifecycle: encryption, retention, cleanup."""
    
    def __init__(
        self,
        workspace_root: str,
        policy: Optional[BrowserStateRetentionPolicy] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.policy = policy or BrowserStateRetentionPolicy()
        self.state_dir = self.workspace_root / "artifacts" / "browser_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_cache: dict[str, BrowserStateMetadata] = {}
        self._last_cleanup = 0.0
    
    def _scan_states(self) -> dict[str, BrowserStateMetadata]:
        """Scan for encrypted state files and build metadata."""
        metadata = {}
        for enc_file in self.state_dir.glob("*.enc"):
            session_name = enc_file.stem
            stat = enc_file.stat()
            metadata[session_name] = BrowserStateMetadata(
                session_name=session_name,
                encrypted_path=enc_file,
                created_at=stat.st_ctime,
                last_accessed=stat.st_atime,
                size_bytes=stat.st_size,
            )
        return metadata
    
    def get_metadata(self, session_name: str) -> Optional[BrowserStateMetadata]:
        """Get metadata for a specific state."""
        if session_name not in self._metadata_cache:
            self._metadata_cache = self._scan_states()
        return self._metadata_cache.get(session_name)
    
    def list_states(self) -> list[BrowserStateMetadata]:
        """List all browser states sorted by last accessed (newest first)."""
        self._metadata_cache = self._scan_states()
        return sorted(
            self._metadata_cache.values(),
            key=lambda m: m.last_accessed,
            reverse=True,
        )
    
    def cleanup(self, force: bool = False) -> int:
        """Clean up old/expired browser states.
        
        Returns number of states removed.
        """
        now = time.time()
        if not force and (now - self._last_cleanup) < self.policy.cleanup_interval_seconds:
            return 0
        
        states = self.list_states()
        removed = 0
        
        # Remove by age
        for meta in states:
            if (now - meta.last_accessed) > self.policy.max_age_seconds:
                try:
                    meta.encrypted_path.unlink()
                    removed += 1
                except OSError:
                    pass
        
        # Remove by count (keep newest)
        states = self.list_states()
        if len(states) > self.policy.max_states:
            for meta in states[self.policy.max_states:]:
                try:
                    meta.encrypted_path.unlink()
                    removed += 1
                except OSError:
                    pass
        
        # Remove by total size
        states = self.list_states()
        total_size = sum(m.size_bytes for m in states)
        if total_size > self.policy.max_total_size_bytes:
            for meta in states:
                if total_size <= self.policy.max_total_size_bytes:
                    break
                try:
                    meta.encrypted_path.unlink()
                    total_size -= meta.size_bytes
                    removed += 1
                except OSError:
                    pass
        
        self._last_cleanup = now
        self._metadata_cache = {}
        return removed
    
    def touch_state(self, session_name: str) -> None:
        """Update last accessed time for a state."""
        meta = self.get_metadata(session_name)
        if meta:
            os.utime(meta.encrypted_path, (time.time(), time.time()))
            self._metadata_cache = {}
    
    def get_state_path(self, session_name: str) -> Path:
        """Get encrypted state file path for session."""
        return self.state_dir / f"{session_name}.enc"

    def save_encrypted_state(self, session_name: str, raw_state_dir: str | Path) -> Path:
        """Encrypt raw state directory into the managed state storage area and run retention cleanup."""
        from windagent_tools.browser.state_encryption import encrypt_state_dir

        out_path = self.get_state_path(session_name)
        encrypt_state_dir(str(raw_state_dir), str(out_path))
        self.cleanup(force=True)
        return out_path

    def load_encrypted_state(self, session_name: str, target_dir: str | Path) -> Path:
        """Decrypt managed encrypted state file into target directory."""
        from windagent_tools.browser.state_encryption import decrypt_state_dir

        enc_path = self.get_state_path(session_name)
        if not enc_path.exists():
            raise FileNotFoundError(f"Encrypted state file not found for session [{session_name}]: {enc_path}")
        decrypt_state_dir(str(enc_path), str(target_dir))
        self.touch_state(session_name)
        return Path(target_dir)

    def create_isolated_profile_copy(self, profile_src: str | Path) -> Path:
        """Create a temporary isolated copy of a Chrome profile directory.
        
        Prevents modifying or polluting the user's main profile during automated runs.
        """
        src_path = Path(profile_src).resolve()
        temp_dir = Path(tempfile.mkdtemp(prefix="windagent_profile_"))
        if src_path.exists() and src_path.is_dir():
            target_path = temp_dir / src_path.name
            shutil.copytree(src_path, target_path, dirs_exist_ok=True)
            return target_path
        return temp_dir

    @staticmethod
    def cleanup_isolated_profile(profile_path: str | Path) -> bool:
        """Remove a temporary isolated profile directory."""
        path = Path(profile_path).resolve()
        parent_candidate = path if "windagent_profile_" in path.name else path.parent
        if parent_candidate.exists() and "windagent_profile_" in parent_candidate.name:
            try:
                shutil.rmtree(parent_candidate, ignore_errors=True)
                return True
            except OSError:
                pass
        return False


def create_state_manager(workspace_root: str) -> BrowserStateManager:
    """Factory for BrowserStateManager with env-based policy."""
    return BrowserStateManager(workspace_root, BrowserStateRetentionPolicy.from_env())