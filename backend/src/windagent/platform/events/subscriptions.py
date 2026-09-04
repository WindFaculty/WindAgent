"""Subscription handles for event dispatch."""

from __future__ import annotations

from collections.abc import Callable

from .contracts import EventHandler

type UnsubscribeCallback = Callable[[], None]


class Subscription:
    """A cancellable handle returned when subscribing to the event bus.

    ``unsubscribe`` is idempotent: repeated calls are safe no-ops, matching
    the ``EventSubscription`` contract's fire-once expectation without
    punishing defensive callers.
    """

    __slots__ = ("_event_type", "_handler", "_unsubscribe", "_active")

    def __init__(self, event_type: str, handler: EventHandler, unsubscribe: UnsubscribeCallback) -> None:
        self._event_type = event_type
        self._handler = handler
        self._unsubscribe = unsubscribe
        self._active = True

    @property
    def event_type(self) -> str:
        """The event type this subscription receives."""
        return self._event_type

    @property
    def handler(self) -> EventHandler:
        """The subscribed handler."""
        return self._handler

    @property
    def active(self) -> bool:
        """Whether the subscription still receives deliveries."""
        return self._active

    async def unsubscribe(self) -> None:
        """Detach the handler; safe to call multiple times."""
        if not self._active:
            return
        self._active = False
        self._unsubscribe()


class SubscriptionSet:
    """A named group of subscriptions that can be cancelled together.

    Feature modules keep one set per lifecycle (e.g. per session) and tear
    the whole group down in one call.
    """

    __slots__ = ("_subscriptions",)

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []

    def add(self, subscription: Subscription) -> Subscription:
        """Track ``subscription`` in this set and return it."""
        if not isinstance(subscription, Subscription):
            raise TypeError("SubscriptionSet accepts Subscription instances")
        self._subscriptions.append(subscription)
        return subscription

    @property
    def size(self) -> int:
        """Number of tracked subscriptions still active."""
        return sum(1 for subscription in self._subscriptions if subscription.active)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe every tracked subscription; idempotent."""
        for subscription in self._subscriptions:
            await subscription.unsubscribe()
        self._subscriptions.clear()
