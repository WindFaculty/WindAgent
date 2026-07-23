"""
TaskState Enumeration for WindAgent Architecture V2.
15 explicit lifecycle states.
"""

from __future__ import annotations
from enum import Enum


class TaskState(str, Enum):
    RECEIVED = "received"
    CLASSIFYING = "classifying"
    CONTEXT_BUILDING = "context_building"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    WAITING_PERMISSION = "waiting_permission"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    RECOVERING = "recovering"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
