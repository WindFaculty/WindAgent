"""Memory Scope & Validation Status taxonomy (Phase 14).

Defines the 8 extended memory scopes:
- Working Memory (active reasoning / execution context)
- Session Memory (session continuity)
- Episodic Memory (raw experiences and episode traces)
- Project Memory (project facts & domain constants)
- Semantic Memory (validated reusable knowledge)
- Procedural Memory (reusable workflows, skills & recipe specs)
- Policy Memory (promoted behavioral rules & guidelines)
- User Memory (user preferences)

Plus ValidationStatus and default scope TTL definitions.
"""

from __future__ import annotations

from enum import StrEnum


class MemoryScope(StrEnum):
    WORKING = "working"
    SESSION = "session"
    PROJECT = "project"
    USER = "user"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    POLICY = "policy"


class ValidationStatus(StrEnum):
    UNVALIDATED = "unvalidated"
    PROPOSED = "proposed"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


VALIDATED_STATUSES: frozenset[ValidationStatus] = frozenset(
    {
        ValidationStatus.VALIDATED,
        ValidationStatus.PROMOTED,
    }
)

TERMINAL_VALIDATION_STATUSES: frozenset[ValidationStatus] = frozenset(
    {
        ValidationStatus.REJECTED,
        ValidationStatus.SUPERSEDED,
    }
)

DEFAULT_SCOPE_TTL: dict[MemoryScope, int | None] = {
    MemoryScope.WORKING: 3600,       # 1 hour
    MemoryScope.SESSION: 86400,      # 24 hours
    MemoryScope.PROJECT: None,       # Persistent
    MemoryScope.USER: None,          # Persistent
    MemoryScope.EPISODIC: 604800,    # 7 days
    MemoryScope.SEMANTIC: None,      # Persistent validated knowledge
    MemoryScope.PROCEDURAL: None,    # Persistent reusable workflows
    MemoryScope.POLICY: None,        # Persistent promoted rules
}
