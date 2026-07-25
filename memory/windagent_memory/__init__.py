"""
WindAgent Memory Package (V2 Architecture — Phase 21).
Multi-layered memory (working, session, project, user, episodic),
durable storage, security write policies, TTL-based eviction,
content-hash deduplication, and project isolation.
"""

from windagent_memory.models import MemoryScope, MemoryRecord, RetentionPolicy, DEFAULT_SCOPE_TTL
from windagent_memory.write_policy import MemoryWritePolicy
from windagent_memory.store import MemoryStore
from windagent_memory.repository import MemoryRecordRepository

__version__ = "0.4.0"

__all__ = [
    "MemoryScope", "MemoryRecord", "RetentionPolicy", "DEFAULT_SCOPE_TTL",
    "MemoryWritePolicy",
    "MemoryStore",
    "MemoryRecordRepository",
]
