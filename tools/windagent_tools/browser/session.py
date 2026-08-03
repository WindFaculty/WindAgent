"""
Phase 12 — Persistent browser sessions and profile locking (plan 04 §8.3).

One WindAgent browser session ID maps 1:1 to one Chrome profile. The profile
path never travels through a message queue or a domain event — it lives only
in local metadata. Profiles at rest use the existing encryption/control
(`state_encryption.py`). A file-based lock with a lease prevents two workers
from using the same profile at the same time.

Session metadata carries: owner, created / last-health time, state, and lease.
Closing or reopening a browser never loses the job mapping already stored in
WindAgent (job mapping is a separate durable record).
"""

from __future__ import annotations

import contextlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class BrowserSessionState(str, Enum):
    NEW = "NEW"
    STARTING = "STARTING"
    READY = "READY"
    PAUSED = "PAUSED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class BrowserSessionError(RuntimeError):
    """Base error for browser session/lock failures."""


class BrowserProfileLockError(BrowserSessionError):
    """Raised when a profile lock cannot be acquired (collision)."""


class BrowserSessionRegistryError(BrowserSessionError):
    """Raised for invalid session registry operations."""


@dataclass(frozen=True)
class BrowserSessionMetadata:
    """Local metadata for one browser session (never contains secrets)."""

    session_id: str
    owner: str = "windagent"
    profile_key: str = ""  # opaque hash-derived key, NOT the profile path
    created_at: float = field(default_factory=time.time)
    last_health_at: float = field(default_factory=time.time)
    state: BrowserSessionState = BrowserSessionState.NEW
    lease_token: str = ""
    lease_expires_at: float = 0.0

    def __post_init__(self) -> None:
        # Registry reloads store state as a JSON string; coerce back to enum.
        if isinstance(self.state, str):
            object.__setattr__(self, "state", BrowserSessionState(self.state))

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "owner": self.owner,
            "profile_key": self.profile_key,
            "created_at": self.created_at,
            "last_health_at": self.last_health_at,
            "state": self.state.value,
            "lease_token": self.lease_token,
            "lease_expires_at": self.lease_expires_at,
        }


class BrowserProfileLock:
    """File-based exclusive lock for one profile, with a lease.

    Collision semantics: a second worker that tries to lock the same profile
    while the lease is still valid fails with `BrowserProfileLockError`. A
    stale lock (lease expired) can be broken explicitly through `break_stale`.
    """

    _LOCK_SUFFIX = ".lock"

    def __init__(
        self,
        lock_dir: str,
        *,
        lease_seconds: float = 1800.0,
        clock: Optional[callable] = None,
    ) -> None:
        self.lock_dir = Path(lock_dir).resolve()
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = lease_seconds
        self._clock = clock or time.time

    # ------------------------------------------------------------------
    def lock_path(self, profile_key: str) -> Path:
        if not _SESSION_PATTERN.fullmatch(profile_key):
            raise BrowserSessionError(
                "profile_key must match [A-Za-z0-9._-] and be at most 64 characters."
            )
        return self.lock_dir / f"{profile_key}{self._LOCK_SUFFIX}"

    def acquire(
        self,
        profile_key: str,
        *,
        worker_id: Optional[str] = None,
    ) -> str:
        """Acquire the profile lock, returning a lease token.

        Raises `BrowserProfileLockError` when another worker holds a valid
        lease (collision).
        """
        path = self.lock_path(profile_key)
        now = self._clock()
        token = f"{worker_id or 'worker'}:{uuid.uuid4().hex[:12]}"

        if path.exists():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                record = {}
            expires_at = float(record.get("lease_expires_at", 0.0))
            if expires_at > now:
                holder = record.get("token", "unknown")
                raise BrowserProfileLockError(
                    f"profile {profile_key} is locked by {holder} "
                    f"until {expires_at:.1f} (collision)"
                )

        payload = {
            "token": token,
            "lease_expires_at": now + self.lease_seconds,
            "acquired_at": now,
        }
        path.write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        return token

    def refresh(self, profile_key: str, token: str) -> bool:
        """Extend the lease if and only if `token` is still the holder."""
        path = self.lock_path(profile_key)
        if not path.exists():
            return False
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if record.get("token") != token:
            return False
        record["lease_expires_at"] = self._clock() + self.lease_seconds
        path.write_text(
            json.dumps(record, sort_keys=True) + "\n", encoding="utf-8"
        )
        return True

    def release(self, profile_key: str, token: str) -> bool:
        """Release the lock only if `token` is still the holder."""
        path = self.lock_path(profile_key)
        if not path.exists():
            return True
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            with contextlib.suppress(OSError):
                path.unlink()
            return True
        if record.get("token") == token:
            with contextlib.suppress(OSError):
                path.unlink()
            return True
        return False

    def break_stale(self, profile_key: str) -> bool:
        """Break a stale lock regardless of holder (lease expiry path)."""
        path = self.lock_path(profile_key)
        if not path.exists():
            return False
        with contextlib.suppress(OSError):
            path.unlink()
        return True

    def is_locked(self, profile_key: str) -> bool:
        path = self.lock_path(profile_key)
        if not path.exists():
            return False
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return True
        return float(record.get("lease_expires_at", 0.0)) > self._clock()


class BrowserSessionRegistry:
    """Durable local registry of browser session metadata.

    The registry is a JSON file under `state_dir`; profile paths are never
    stored here (only the opaque profile key).
    """

    def __init__(self, state_dir: str, *, clock: Optional[callable] = None) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self._registry_path = self.state_dir / "browser_sessions.json"
        self._sessions: dict[str, dict] = self._load()

    # ------------------------------------------------------------------
    def _load(self) -> dict[str, dict]:
        if not self._registry_path.exists():
            return {}
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self._registry_path.write_text(
            json.dumps(self._sessions, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    def register(
        self,
        session_id: str,
        *,
        owner: str = "windagent",
        profile_key: str = "",
    ) -> BrowserSessionMetadata:
        if not _SESSION_PATTERN.fullmatch(session_id):
            raise BrowserSessionRegistryError(
                "session_id must match [A-Za-z0-9._-] and be at most 64 characters."
            )
        if session_id in self._sessions:
            raise BrowserSessionRegistryError(f"session {session_id} already registered")
        meta = BrowserSessionMetadata(
            session_id=session_id,
            owner=owner,
            profile_key=profile_key,
            created_at=self._clock(),
            last_health_at=self._clock(),
            state=BrowserSessionState.NEW,
        )
        self._sessions[session_id] = meta.to_dict()
        self._save()
        return meta

    def get(self, session_id: str) -> Optional[BrowserSessionMetadata]:
        raw = self._sessions.get(session_id)
        if raw is None:
            return None
        return BrowserSessionMetadata(**raw)

    def update_state(
        self, session_id: str, state: BrowserSessionState
    ) -> BrowserSessionMetadata:
        raw = self._sessions.get(session_id)
        if raw is None:
            raise BrowserSessionRegistryError(f"session {session_id} is not registered")
        raw["state"] = state.value
        raw["last_health_at"] = self._clock()
        self._sessions[session_id] = raw
        self._save()
        return BrowserSessionMetadata(**raw)

    def touch_health(self, session_id: str) -> BrowserSessionMetadata:
        raw = self._sessions.get(session_id)
        if raw is None:
            raise BrowserSessionRegistryError(f"session {session_id} is not registered")
        raw["last_health_at"] = self._clock()
        self._sessions[session_id] = raw
        self._save()
        return BrowserSessionMetadata(**raw)

    def bind_lease(
        self,
        session_id: str,
        *,
        token: str,
        expires_at: float,
    ) -> BrowserSessionMetadata:
        raw = self._sessions.get(session_id)
        if raw is None:
            raise BrowserSessionRegistryError(f"session {session_id} is not registered")
        raw["lease_token"] = token
        raw["lease_expires_at"] = expires_at
        self._sessions[session_id] = raw
        self._save()
        return BrowserSessionMetadata(**raw)

    def list_sessions(self) -> list[BrowserSessionMetadata]:
        return [
            BrowserSessionMetadata(**raw)
            for raw in sorted(
                self._sessions.values(), key=lambda r: r.get("created_at", 0.0)
            )
        ]

    def close(self, session_id: str) -> Optional[BrowserSessionMetadata]:
        raw = self._sessions.get(session_id)
        if raw is None:
            return None
        raw["state"] = BrowserSessionState.CLOSED.value
        self._sessions[session_id] = raw
        self._save()
        return BrowserSessionMetadata(**raw)


__all__ = [
    "BrowserProfileLock",
    "BrowserProfileLockError",
    "BrowserSessionError",
    "BrowserSessionMetadata",
    "BrowserSessionRegistry",
    "BrowserSessionRegistryError",
    "BrowserSessionState",
]
