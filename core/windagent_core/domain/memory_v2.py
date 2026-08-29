"""Memory V2 Domain Models & Extended Taxonomy (ban_ke_hoach_v1 §11).

Defines extended memory semantics:
- Working Memory (active reasoning / execution context)
- Session Memory (session continuity)
- Episodic Memory (raw experiences and episode traces)
- Project Memory (project facts & domain constants)
- Semantic Memory (validated reusable knowledge)
- Procedural Memory (reusable workflows, skills & recipe specs)
- Policy Memory (promoted behavioral rules & guidelines)
- User Memory (user preferences)

Plus structured LearningMetadata, ValidationStatus, TTL defaults, and hashing.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


DEF_UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(DEF_UTC)


class MemoryScope(str, Enum):
    WORKING = "working"
    SESSION = "session"
    PROJECT = "project"
    USER = "user"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    POLICY = "policy"


class ValidationStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    PROPOSED = "proposed"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


VALIDATED_STATUSES: Set[ValidationStatus] = {
    ValidationStatus.VALIDATED,
    ValidationStatus.PROMOTED,
}

TERMINAL_VALIDATION_STATUSES: Set[ValidationStatus] = {
    ValidationStatus.REJECTED,
    ValidationStatus.SUPERSEDED,
}

DEFAULT_SCOPE_TTL: Dict[MemoryScope, Optional[int]] = {
    MemoryScope.WORKING: 3600,       # 1 hour
    MemoryScope.SESSION: 86400,      # 24 hours
    MemoryScope.PROJECT: None,       # Persistent
    MemoryScope.USER: None,          # Persistent
    MemoryScope.EPISODIC: 604800,    # 7 days
    MemoryScope.SEMANTIC: None,      # Persistent validated knowledge
    MemoryScope.PROCEDURAL: None,    # Persistent reusable workflows
    MemoryScope.POLICY: None,        # Persistent promoted rules
}


class LearningMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sample_size: int = Field(default=0, ge=0)
    source_run_ids: List[str] = Field(default_factory=list)
    harness_version: Optional[str] = None
    validation_status: ValidationStatus = Field(default=ValidationStatus.UNVALIDATED)
    last_validated_at: Optional[datetime] = None
    supersedes_id: Optional[str] = None

    def is_validated(self) -> bool:
        return self.validation_status in VALIDATED_STATUSES

    def is_terminal(self) -> bool:
        return self.validation_status in TERMINAL_VALIDATION_STATUSES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_refs": list(self.evidence_refs),
            "confidence": float(self.confidence),
            "sample_size": int(self.sample_size),
            "source_run_ids": list(self.source_run_ids),
            "harness_version": self.harness_version,
            "validation_status": self.validation_status.value,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "supersedes_id": self.supersedes_id,
        }


def compute_content_hash(key: str, value: Any) -> str:
    try:
        raw = json.dumps({"key": key, "value": value}, sort_keys=True, default=str)
    except Exception:
        raw = f"{key}:{value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MemoryRecordV2(BaseModel):
    model_config = ConfigDict(frozen=False, extra="ignore")

    id: str
    scope: MemoryScope
    key: str
    value: Any
    provenance_source: str
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)
    ttl_seconds: Optional[int] = None
    content_hash: Optional[str] = None
    learning_metadata: LearningMetadata = Field(default_factory=LearningMetadata)
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def get_effective_ttl(self) -> Optional[int]:
        if self.ttl_seconds is not None:
            return self.ttl_seconds
        return DEFAULT_SCOPE_TTL.get(self.scope)

    def is_expired(self, reference_time: Optional[datetime] = None) -> bool:
        ttl = self.get_effective_ttl()
        if ttl is None:
            return False
        ref = reference_time or utc_now()
        expiry = self.updated_at + timedelta(seconds=ttl)
        return ref >= expiry

    def ensure_hash(self) -> str:
        if not self.content_hash:
            self.content_hash = compute_content_hash(self.key, self.value)
        return self.content_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope.value,
            "key": self.key,
            "value": self.value,
            "provenance_source": self.provenance_source,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "tags": dict(self.tags),
            "ttl_seconds": self.ttl_seconds,
            "content_hash": self.ensure_hash(),
            "learning_metadata": self.learning_metadata.to_dict(),
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
