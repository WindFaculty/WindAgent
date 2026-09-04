"""Event type registry validating envelopes before dispatch and delivery."""

from __future__ import annotations

from windagent.kernel.errors import DomainError
from windagent.kernel.events import EventEnvelope


class UnknownEventTypeError(DomainError):
    """The envelope's event type was never registered."""

    default_code = "unknown_event_type"


class EventVersionMismatchError(DomainError):
    """The envelope's schema version disagrees with the registry."""

    default_code = "event_version_mismatch"


class EventTypeRegistry:
    """Stable mapping of event type names to schema versions.

    Feature modules register their event types at composition time; the
    registry stays domain-agnostic and only knows names and versions.
    """

    def __init__(self) -> None:
        self._versions: dict[str, int] = {}

    def register(self, event_type: str, *, version: int = 1) -> None:
        """Register ``event_type`` at ``version``.

        Re-registering the same type at the same version is idempotent; a
        conflicting version is rejected to protect consumers from silently
        changing contracts.
        """
        name = _required_name(event_type)
        if version < 1:
            raise ValueError("event version must be at least 1")
        existing = self._versions.get(name)
        if existing is not None and existing != version:
            raise EventVersionMismatchError(
                f"event type {name!r} is already registered at version "
                f"{existing}, refusing re-registration at version {version}",
                context={"event_type": name, "registered_version": existing},
            )
        self._versions[name] = version

    def version_of(self, event_type: str) -> int | None:
        """Return the registered schema version, or ``None`` if unknown."""
        return self._versions.get(_required_name(event_type))

    def registered_types(self) -> tuple[str, ...]:
        """Return all registered event type names in registration order."""
        return tuple(self._versions)

    def validate(self, envelope: EventEnvelope) -> None:
        """Validate an envelope against the registry.

        Raises :class:`UnknownEventTypeError` for unregistered types and
        :class:`EventVersionMismatchError` for version drift.
        """
        name = _required_name(envelope.event_type)
        registered = self._versions.get(name)
        if registered is None:
            raise UnknownEventTypeError(
                f"event type {name!r} is not registered",
                context={"event_type": name},
            )
        if int(envelope.event_version) != registered:
            raise EventVersionMismatchError(
                f"event type {name!r} is registered at version {registered} "
                f"but the envelope carries version {int(envelope.event_version)}",
                context={
                    "event_type": name,
                    "registered_version": registered,
                    "envelope_version": int(envelope.event_version),
                },
            )


def _required_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("event type must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("event type cannot be empty")
    return normalized
