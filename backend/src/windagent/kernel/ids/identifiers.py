"""Immutable, nominal UUID identifiers.

Identifiers are deliberately distinct Python types even though their wire
representation is a UUID.  This keeps an ``ActorId`` from being accidentally
used where an ``EntityId`` or a ``CorrelationId`` is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True, init=False)
class Identifier:
    """Base value object for UUID-backed identifiers.

    The stored value is the canonical, lowercase UUID string so it is safe to
    use at serialization boundaries without a second normalization step.
    """

    value: str

    def __init__(self, value: str | UUID) -> None:
        object.__setattr__(self, "value", self._normalize(value))

    @staticmethod
    def _normalize(value: str | UUID) -> str:
        if isinstance(value, UUID):
            return str(value)
        if not isinstance(value, str):
            raise TypeError("identifier value must be a UUID or UUID string")

        candidate = value.strip()
        if not candidate:
            raise ValueError("identifier value cannot be empty")
        try:
            return str(UUID(candidate))
        except ValueError as exc:
            raise ValueError(f"invalid UUID identifier: {value!r}") from exc

    @classmethod
    def new(cls) -> Self:
        """Create a new random UUIDv4 identifier of this exact nominal type."""

        return cls(uuid4())

    @classmethod
    def generate(cls) -> Self:
        """Alias for :meth:`new` for readability at call sites."""

        return cls.new()

    def to_uuid(self) -> UUID:
        """Return the identifier as a ``uuid.UUID`` instance."""

        return UUID(self.value)

    def __str__(self) -> str:
        return self.value


class EntityId(Identifier):
    """Identifier of a domain aggregate or entity."""


class EventId(Identifier):
    """Identifier of a single immutable event."""


class CorrelationId(Identifier):
    """Identifier shared by all work caused by one logical operation."""


class CausationId(Identifier):
    """Identifier of the event or action that directly caused a new event."""


class ActorId(Identifier):
    """Identifier of the principal that initiated an action."""
