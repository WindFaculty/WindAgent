"""Event publication and in-process dispatch contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from windagent.kernel.events import EventEnvelope


@runtime_checkable
class EventHandler(Protocol):
    """Consumes an immutable event envelope."""

    async def handle(self, event: EventEnvelope) -> None:
        """Handle one delivered event."""


@runtime_checkable
class EventSubscription(Protocol):
    """A cancellable event-handler subscription."""

    async def unsubscribe(self) -> None:
        """Prevent future deliveries through this subscription."""


@runtime_checkable
class EventBus(Protocol):
    """Dispatches envelopes to subscriptions in the current runtime."""

    async def subscribe(self, event_type: str, handler: EventHandler) -> EventSubscription:
        """Register a handler for a stable event type name."""

    async def publish(self, event: EventEnvelope) -> None:
        """Deliver an envelope through this runtime's subscriptions."""


@runtime_checkable
class EventPublisher(Protocol):
    """Publishes envelopes across a delivery boundary.

    The outbox, ordering, replay, and transport implementation are explicitly
    deferred to Phase 6.
    """

    async def publish(self, event: EventEnvelope) -> None:
        """Make an immutable event envelope available to downstream consumers."""
