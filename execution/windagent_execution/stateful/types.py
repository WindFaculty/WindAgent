import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
class StatefulSessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    RUNNING = "running"
    IDLE = "idle"
    CHECKPOINTED = "checkpointed"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
class StatefulCheckpointKind(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"
@dataclass(frozen=True)
class SessionDescriptor:
    session_id: str
    status: StatefulSessionStatus
    created_at: datetime
    updated_at: datetime
    runtime_kind: str = "v1"
    fencing_token: str = field(default_factory=lambda: f"fence_{uuid.uuid4().hex[:12]}")
    metadata: Dict[str, Any] = field(default_factory=dict)
    owner_id: Optional[str] = None
    execution_count: int = 0
    checkpoint_count: int = 0
@dataclass
class StatefulExecuteRequest:
    code: Optional[str] = None
    tool_name: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:8]}")
@dataclass(frozen=True)
class StatefulExecuteResult:
    session_id: str
    execution_id: str
    status: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    session_id: str
    created_at: datetime
    sequence: int
    kind: StatefulCheckpointKind = StatefulCheckpointKind.MANUAL
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    execution_count_at_checkpoint: int = 0
@dataclass(frozen=True)
class InspectResult:
    session_id: str
    status: StatefulSessionStatus
    state_vars: Dict[str, Any]
    history: List[Dict[str, Any]]
    checkpoint_ids: List[str]
    fencing_token: str
    runtime_kind: str
    created_at: datetime
    updated_at: datetime
HOST_AUTHORITY_FORBIDDEN_KEYS = frozenset({"credential","credentials","secret","api_key","provider_call","provider_key","schedule","memory_write","learning_promotion","promotion","auth_token","password"})
