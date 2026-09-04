"""API composition root: security stack, buses, and the application factory."""

from .audit_outbox import AUDIT_AGGREGATE_TYPE, AUDIT_EVENT_TYPE, OutboxAuditSink
from .buses import (
    DispatchError,
    DuplicateHandlerError,
    InProcessCommandBus,
    InProcessQueryBus,
    UnregisteredMessageError,
)
from .factory import create_app
from .module_runtime import ApiModuleRuntime

__all__ = [
    "AUDIT_AGGREGATE_TYPE",
    "AUDIT_EVENT_TYPE",
    "ApiModuleRuntime",
    "DispatchError",
    "DuplicateHandlerError",
    "InProcessCommandBus",
    "InProcessQueryBus",
    "OutboxAuditSink",
    "UnregisteredMessageError",
    "create_app",
]
