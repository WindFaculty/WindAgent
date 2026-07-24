"""
WindAgent Core Events Package.
Exports canonical EventEnvelope, EventCatalog, EventRegistry, and processor utilities.
Legacy compatibility mappers live only at the API edge adapter boundary.
"""

from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.events.registry import EventRegistry, BaseEventPayload
from windagent_core.events.processor import redact_event_payload, EventDeduplicator, ReplayFilter

__all__ = [
    "EventEnvelope",
    "EventCatalog",
    "EventRegistry",
    "BaseEventPayload",
    "redact_event_payload",
    "EventDeduplicator",
    "ReplayFilter",
]
