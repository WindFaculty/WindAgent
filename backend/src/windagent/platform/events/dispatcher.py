"""In-process event bus implementing the platform dispatch contract."""

from __future__ import annotations

from collections.abc import Callable

from windagent.kernel.events import EventEnvelope

from .contracts import EventBus, EventHandler
from .registry import EventTypeRegistry
from .subscriptions import Subscription

type HandlerErrorHook = Callable[[EventEnvelope, EventHandler, BaseException], None]


class EventDispatchError(RuntimeError):
    """Raised when one or more handlers failed during a fan-out.

    Every matching handler still ran (error isolation); this error is raised
    afterwards so failures surface instead of being swallowed.
    """

    def __init__(
        self,
        event: EventEnvelope,
        failures: tuple[tuple[EventHandler, BaseException], ...],
    ) -> None:
        self.event = event
        self.failures = failures
        summary = "; ".join(
            f"{type(handler).__name__}: {error!r}" for handler, error in failures
        )
        super().__init__(
            f"event {event.event_type!r} failed in {len(failures)} handler(s): {summary}"
        )


class InProcessEventBus(EventBus):
    """Fan-out dispatch to in-process handlers, in registration order.

    One handler failing never prevents the remaining handlers from running.
    With no ``on_handler_error`` hook, the failures are raised together as
    :class:`EventDispatchError` after the fan-out completes.
    """

    def __init__(
        self,
        *,
        registry: EventTypeRegistry | None = None,
        on_handler_error: HandlerErrorHook | None = None,
    ) -> None:
        self._registry = registry
        self._on_handler_error = on_handler_error
        self._handlers: dict[str, list[EventHandler]] = {}

    async def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        """Register ``handler`` for ``event_type``.

        Duplicate (type, handler) pairs are rejected so a handler never
        receives an event twice through the same bus.
        """
        name = _required_name(event_type)
        if not callable(getattr(handler, "handle", None)):
            raise TypeError("handler must provide an async handle() method")
        handlers = self._handlers.setdefault(name, [])
        if any(existing is handler for existing in handlers):
            raise ValueError(f"handler is already subscribed to {name!r}")
        handlers.append(handler)
        return Subscription(name, handler, lambda: self._detach(name, handler))

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Detach ``handler`` from ``event_type`` if subscribed."""
        self._detach(_required_name(event_type), handler)

    async def publish(self, event: EventEnvelope) -> None:
        """Deliver ``event`` to every current subscriber of its type."""
        if self._registry is not None:
            self._registry.validate(event)

        failures: list[tuple[EventHandler, BaseException]] = []
        for handler in tuple(self._handlers.get(event.event_type, ())):
            try:
                await handler.handle(event)
            except Exception as error:  # noqa: BLE001 - isolation by design
                if self._on_handler_error is not None:
                    self._on_handler_error(event, handler, error)
                else:
                    failures.append((handler, error))

        if failures:
            raise EventDispatchError(event, tuple(failures))

    def subscriber_count(self, event_type: str) -> int:
        """Number of handlers currently subscribed to ``event_type``."""
        return len(self._handlers.get(event_type, ()))

    def _detach(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type)
        if handlers is None:
            return
        remaining = [existing for existing in handlers if existing is not handler]
        if remaining:
            self._handlers[event_type] = remaining
        else:
            self._handlers.pop(event_type, None)


def _required_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("event type must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("event type cannot be empty")
    return normalized
