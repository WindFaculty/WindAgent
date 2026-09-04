"""Phase 6 unit tests: in-process dispatch and subscription handles."""

from __future__ import annotations

import pytest
from windagent.kernel.events import EventEnvelope
from windagent.kernel.ids import EntityId
from windagent.platform.events import (
    EventDispatchError,
    EventTypeRegistry,
    InProcessEventBus,
    SubscriptionSet,
    UnknownEventTypeError,
)
from windagent.platform.events.contracts import EventHandler


def make_envelope(event_type: str = "studio.episode.planned") -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        aggregate_type="episode",
        aggregate_id=EntityId.new(),
        sequence=0,
        payload={"title": "ep1"},
    )


class RecordingHandler:
    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self.error = error
        self.received: list[EventEnvelope] = []

    async def handle(self, event: EventEnvelope) -> None:
        self.received.append(event)
        if self.error is not None:
            raise self.error


async def test_publish_fans_out_in_registration_order() -> None:
    bus = InProcessEventBus()
    first = RecordingHandler("first")
    second = RecordingHandler("second")
    await bus.subscribe("studio.episode.planned", first)
    await bus.subscribe("studio.episode.planned", second)

    event = make_envelope()
    await bus.publish(event)

    assert first.received == [event]
    assert second.received == [event]


async def test_unsubscribe_stops_delivery() -> None:
    bus = InProcessEventBus()
    handler = RecordingHandler("h")
    subscription = await bus.subscribe("studio.episode.planned", handler)

    await bus.publish(make_envelope())
    await subscription.unsubscribe()
    await bus.publish(make_envelope())

    assert len(handler.received) == 1
    assert bus.subscriber_count("studio.episode.planned") == 0
    assert not subscription.active


async def test_unsubscribe_is_idempotent() -> None:
    bus = InProcessEventBus()
    handler = RecordingHandler("h")
    subscription = await bus.subscribe("studio.episode.planned", handler)

    await subscription.unsubscribe()
    await subscription.unsubscribe()
    await bus.unsubscribe("studio.episode.planned", handler)


async def test_duplicate_subscription_is_rejected() -> None:
    bus = InProcessEventBus()
    handler = RecordingHandler("h")
    await bus.subscribe("studio.episode.planned", handler)

    with pytest.raises(ValueError, match="already subscribed"):
        await bus.subscribe("studio.episode.planned", handler)


async def test_invalid_handlers_are_rejected() -> None:
    bus = InProcessEventBus()

    with pytest.raises(TypeError):
        await bus.subscribe("studio.episode.planned", "not-a-handler")  # type: ignore[arg-type]


async def test_publish_without_subscribers_is_a_noop() -> None:
    bus = InProcessEventBus()

    await bus.publish(make_envelope())

    assert bus.subscriber_count("studio.episode.planned") == 0


async def test_handler_failure_is_isolated_and_raised_after_fanout() -> None:
    bus = InProcessEventBus()
    failing = RecordingHandler("failing", error=RuntimeError("boom"))
    healthy = RecordingHandler("healthy")
    await bus.subscribe("studio.episode.planned", failing)
    await bus.subscribe("studio.episode.planned", healthy)

    event = make_envelope()
    with pytest.raises(EventDispatchError) as excinfo:
        await bus.publish(event)

    # The healthy handler still received the event (isolation), and the
    # failure surfaces afterwards with the responsible handler attached.
    assert healthy.received == [event]
    assert excinfo.value.event is event
    assert [type(handler).__name__ for handler, _ in excinfo.value.failures] == [
        "RecordingHandler"
    ]


async def test_handler_error_hook_replaces_raising() -> None:
    seen: list[tuple[str, str]] = []

    def hook(
        event: EventEnvelope, handler: EventHandler, error: BaseException
    ) -> None:
        seen.append((type(handler).__name__, str(error)))

    bus = InProcessEventBus(on_handler_error=hook)
    failing = RecordingHandler("failing", error=RuntimeError("boom"))
    await bus.subscribe("studio.episode.planned", failing)

    await bus.publish(make_envelope())  # hook swallows the failure

    assert seen == [("RecordingHandler", "boom")]


async def test_registry_validation_is_enforced_when_attached() -> None:
    registry = EventTypeRegistry()
    registry.register("studio.episode.planned")
    bus = InProcessEventBus(registry=registry)
    handler = RecordingHandler("h")
    await bus.subscribe("studio.episode.planned", handler)

    await bus.publish(make_envelope())
    with pytest.raises(UnknownEventTypeError):
        await bus.publish(make_envelope(event_type="unregistered.event"))

    assert len(handler.received) == 1


async def test_subscription_set_unsubscribes_as_a_group() -> None:
    bus = InProcessEventBus()
    first = RecordingHandler("first")
    second = RecordingHandler("second")
    group = SubscriptionSet()
    group.add(await bus.subscribe("studio.episode.planned", first))
    group.add(await bus.subscribe("studio.episode.rendered", second))
    assert group.size == 2

    await group.unsubscribe_all()

    assert group.size == 0
    assert bus.subscriber_count("studio.episode.planned") == 0
    assert bus.subscriber_count("studio.episode.rendered") == 0
    await group.unsubscribe_all()  # idempotent
