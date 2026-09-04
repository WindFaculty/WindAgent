"""Phase 6 unit tests: event type registry."""

from __future__ import annotations

import pytest
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.platform.events import (
    EventTypeRegistry,
    EventVersionMismatchError,
    UnknownEventTypeError,
)


def make_envelope(event_type: str = "studio.episode.planned", version: int = 1) -> EventEnvelope:
    from windagent.kernel.types import Version

    return EventEnvelope(
        event_type=event_type,
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
        sequence=0,
        event_version=Version(version),
    )


def test_register_and_lookup_versions() -> None:
    registry = EventTypeRegistry()

    registry.register("studio.episode.planned")
    registry.register("studio.episode.rendered", version=3)

    assert registry.version_of("studio.episode.planned") == 1
    assert registry.version_of("studio.episode.rendered") == 3
    assert registry.version_of("studio.episode.deleted") is None
    assert registry.registered_types() == (
        "studio.episode.planned",
        "studio.episode.rendered",
    )


def test_duplicate_registration_with_conflicting_version_is_rejected() -> None:
    registry = EventTypeRegistry()
    registry.register("studio.episode.planned", version=2)

    with pytest.raises(EventVersionMismatchError, match="version 2"):
        registry.register("studio.episode.planned", version=3)
    with pytest.raises(ValueError):
        registry.register("studio.episode.planned", version=0)


def test_registration_is_idempotent_at_the_same_version() -> None:
    registry = EventTypeRegistry()

    registry.register("studio.episode.planned", version=2)
    registry.register("studio.episode.planned", version=2)

    assert registry.version_of("studio.episode.planned") == 2


def test_validation_accepts_registered_envelopes() -> None:
    registry = EventTypeRegistry()
    registry.register("studio.episode.planned")

    registry.validate(make_envelope())  # does not raise


def test_validation_rejects_unknown_event_types() -> None:
    registry = EventTypeRegistry()

    with pytest.raises(UnknownEventTypeError, match="not registered"):
        registry.validate(make_envelope(event_type="mystery.event"))


def test_validation_rejects_version_drift() -> None:
    registry = EventTypeRegistry()
    registry.register("studio.episode.planned", version=2)

    with pytest.raises(EventVersionMismatchError, match="version 1"):
        registry.validate(make_envelope(version=1))


def test_event_type_names_are_validated() -> None:
    registry = EventTypeRegistry()

    with pytest.raises(ValueError):
        registry.register("   ")
    with pytest.raises(ValueError):
        registry.register("studio.episode.planned", version=0)
