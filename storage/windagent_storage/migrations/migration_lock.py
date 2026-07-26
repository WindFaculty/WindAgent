"""
Migration Lock for WindAgent Storage Layer.
Prevents concurrent migrations and ensures migration safety.
"""

from __future__ import annotations
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger("windagent.storage.migrations.lock")


class LockStatus(Enum):
    """Status of a migration lock."""
    ACQUIRED = "acquired"
    RELEASED = "released"
    EXPIRED = "expired"
    ABANDONED = "abandoned"


class LockType(Enum):
    """Type of lock."""
    MIGRATION = "migration"
    SCHEMA_CHECK = "schema_check"
    BACKUP = "backup"


@dataclass
class LockInfo:
    """Information about a lock."""
    lock_id: str
    lock_type: LockType
    acquired_by: str
    acquired_at: datetime
    expires_at: datetime
    status: LockStatus
    heartbeat_at: Optional[datetime]
    
    def is_expired(self) -> bool:
        """Check if lock has expired."""
        return datetime.now() > self.expires_at


class MigrationLock:
    """
    Manages migration locks to prevent concurrent migrations.
    
    Uses a database table for distributed locking:
    - migration_locks (lock_id, lock_type, acquired_by, acquired_at, expires_at, status)
    
    Features:
    - Automatic expiration (default: 5 minutes)
    - Heartbeat to extend lock
    - Lock cleanup on startup
    - Context manager support
    """
    
    LOCK_TABLE_NAME = "migration_locks"
    DEFAULT_LOCK_TIMEOUT_SECONDS = 300  # 5 minutes
    HEARTBEAT_INTERVAL_SECONDS = 60  # 1 minute
    
    def __init__(self, engine: Engine, lock_timeout: int = DEFAULT_LOCK_TIMEOUT_SECONDS):
        self._engine = engine
        self._lock_timeout = lock_timeout
        self._lock_id: Optional[str] = None
        self._lock_ids: List[str] = []
        self._session: Optional[Session] = None
        self._ensure_lock_table()
    
    def _ensure_lock_table(self) -> None:
        """Ensure the lock table exists."""
        with self._engine.connect() as conn:
            # Check if table exists
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
            ), {"table_name": self.LOCK_TABLE_NAME})
            
            if result.fetchone() is None:
                # Create table
                conn.execute(text(f"""
                    CREATE TABLE {self.LOCK_TABLE_NAME} (
                        lock_id TEXT PRIMARY KEY,
                        lock_type TEXT NOT NULL,
                        acquired_by TEXT NOT NULL,
                        acquired_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'acquired',
                        heartbeat_at TEXT
                    )
                """))
                conn.commit()
                logger.info(f"Created lock table {self.LOCK_TABLE_NAME}")
    
    def acquire(
        self,
        lock_type: LockType = LockType.MIGRATION,
        identifier: Optional[str] = None,
    ) -> bool:
        """
        Acquire a lock.
        
        Args:
            lock_type: Type of lock to acquire
            identifier: Optional identifier (defaults to random UUID)
            
        Returns:
            True if lock acquired, False otherwise
        """
        self._ensure_lock_table()
        
        lock_id = identifier or str(uuid.uuid4())
        acquired_by = f"process-{uuid.uuid4().hex[:8]}"
        acquired_at = datetime.now()
        expires_at = acquired_at + timedelta(seconds=self._lock_timeout)
        
        with self._engine.connect() as conn:
            try:
                # Try to insert lock
                conn.execute(text(f"""
                    INSERT INTO {self.LOCK_TABLE_NAME} 
                    (lock_id, lock_type, acquired_by, acquired_at, expires_at, status)
                    VALUES (:lock_id, :lock_type, :acquired_by, :acquired_at, :expires_at, :status)
                """), {
                    "lock_id": lock_id,
                    "lock_type": lock_type.value,
                    "acquired_by": acquired_by,
                    "acquired_at": acquired_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "status": LockStatus.ACQUIRED.value,
                })
                conn.commit()
                
                self._lock_id = lock_id
                self._lock_ids.append(lock_id)
                logger.info(f"Acquired lock {lock_id} of type {lock_type.value}")
                return True
                
            except OperationalError:
                # Lock already exists or other error
                logger.warning(f"Failed to acquire lock {lock_id}")
                return False
    
    def release(self, lock_id: Optional[str] = None) -> bool:
        """
        Release a lock.
        
        Args:
            lock_id: Lock ID to release (defaults to current lock)
            
        Returns:
            True if lock released, False otherwise
        """
        lock_id = lock_id or (self._lock_ids[-1] if self._lock_ids else self._lock_id)
        if not lock_id:
            logger.warning("No lock to release")
            return False
        
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                UPDATE {self.LOCK_TABLE_NAME}
                SET status = :status, heartbeat_at = :heartbeat_at
                WHERE lock_id = :lock_id AND status = :old_status
            """), {
                "lock_id": lock_id,
                "status": LockStatus.RELEASED.value,
                "old_status": LockStatus.ACQUIRED.value,
                "heartbeat_at": datetime.now().isoformat(),
            })
            conn.commit()
            
            if result.rowcount > 0:
                logger.info(f"Released lock {lock_id}")
                if lock_id in self._lock_ids:
                    self._lock_ids.remove(lock_id)
                self._lock_id = self._lock_ids[-1] if self._lock_ids else None
                return True
            else:
                logger.warning(f"Lock {lock_id} not found or already released")
                return False
    
    def heartbeat(self, lock_id: Optional[str] = None) -> bool:
        """
        Extend lock expiration with heartbeat.
        
        Args:
            lock_id: Lock ID to heartbeat (defaults to current lock)
            
        Returns:
            True if heartbeat successful, False otherwise
        """
        lock_id = lock_id or self._lock_id
        if not lock_id:
            logger.warning("No lock to heartbeat")
            return False
        
        with self._engine.connect() as conn:
            expires_at = datetime.now() + timedelta(seconds=self._lock_timeout)
            result = conn.execute(text(f"""
                UPDATE {self.LOCK_TABLE_NAME}
                SET expires_at = :expires_at, heartbeat_at = :heartbeat_at
                WHERE lock_id = :lock_id AND status = :status
            """), {
                "lock_id": lock_id,
                "expires_at": expires_at.isoformat(),
                "heartbeat_at": datetime.now().isoformat(),
                "status": LockStatus.ACQUIRED.value,
            })
            conn.commit()
            
            if result.rowcount > 0:
                logger.debug(f"Heartbeat for lock {lock_id}")
                return True
            else:
                logger.warning(f"Lock {lock_id} not found or not acquired")
                return False
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired locks.
        
        Returns:
            Number of locks cleaned up
        """
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                UPDATE {self.LOCK_TABLE_NAME}
                SET status = :expired_status
                WHERE status = :acquired_status AND expires_at < :now
            """), {
                "expired_status": LockStatus.EXPIRED.value,
                "acquired_status": LockStatus.ACQUIRED.value,
                "now": datetime.now().isoformat(),
            })
            conn.commit()
            return result.rowcount
    
    def is_locked(self, lock_type: Optional[LockType] = None) -> bool:
        """
        Check if a lock of given type is held.
        
        Args:
            lock_type: Optional lock type to check (checks all if None)
            
        Returns:
            True if any matching lock is held
        """
        with self._engine.connect() as conn:
            if lock_type:
                result = conn.execute(text(f"""
                    SELECT COUNT(*) FROM {self.LOCK_TABLE_NAME}
                    WHERE status = :status AND lock_type = :lock_type
                """), {
                    "status": LockStatus.ACQUIRED.value,
                    "lock_type": lock_type.value,
                })
            else:
                result = conn.execute(text(f"""
                    SELECT COUNT(*) FROM {self.LOCK_TABLE_NAME}
                    WHERE status = :status
                """), {
                    "status": LockStatus.ACQUIRED.value,
                })
            
            count = result.scalar()
            return count > 0
    
    def get_active_locks(self) -> List[LockInfo]:
        """Get all currently active locks."""
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT lock_id, lock_type, acquired_by, acquired_at, expires_at, status, heartbeat_at
                FROM {self.LOCK_TABLE_NAME}
                WHERE status = :status
            """), {
                "status": LockStatus.ACQUIRED.value,
            })
            
            locks = []
            for row in result:
                lock = LockInfo(
                    lock_id=row[0],
                    lock_type=LockType(row[1]),
                    acquired_by=row[2],
                    acquired_at=datetime.fromisoformat(row[3]),
                    expires_at=datetime.fromisoformat(row[4]),
                    status=LockStatus(row[5]),
                    heartbeat_at=datetime.fromisoformat(row[6]) if row[6] else None,
                )
                locks.append(lock)
            
            return locks
    
    @contextmanager
    def acquire_context(self, lock_type: LockType = LockType.MIGRATION):
        """
        Context manager for acquiring and releasing a lock.
        
        Args:
            lock_type: Type of lock to acquire
            
        Yields:
            The lock ID if acquired
            
        Raises:
            RuntimeError: If lock cannot be acquired
        """
        if self.acquire(lock_type):
            try:
                yield self._lock_id
            finally:
                self.release()
        else:
            raise RuntimeError(f"Could not acquire {lock_type.value} lock")
