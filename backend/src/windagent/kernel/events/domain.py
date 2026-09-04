"""The base class for in-process domain events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from ..ids import EventId
from ..time import normalize_utc, utc_now
from ..types import Version


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Immutable metadata shared by all domain events.

    Subclasses should also use ``kw_only=True`` so their domain data can be
    added without conflicting with these defaulted metadata fields.
    """

    event_id: EventId = field(default_factory=EventId.new)
    occurred_at: datetime = field(default_factory=utc_now)
    event_version: Version = field(default_factory=lambda: Version(1))

    event_name: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise TypeError("event_id must be an EventId")
        if not isinstance(self.event_version, Version):
            raise TypeError("event_version must be a Version")
        if self.event_version.value < 1:
            raise ValueError("event_version must be at least 1")
        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at))

    @property
    def event_type(self) -> str:
        """Return an explicit name or a stable fully-qualified class name."""

        explicit_name = type(self).event_name
        if explicit_name is not None:
            normalized = explicit_name.strip()
            if not normalized:
                raise ValueError("event_name cannot be empty")
            return normalized
        event_class = type(self)
        return f"{event_class.__module__}.{event_class.__qualname__}"
