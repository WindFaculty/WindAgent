"""Composition-root implementations of the Phase 3 command/query contracts.

``platform.commands.contracts`` and ``platform.queries.contracts`` state that
implementations belong to a composition root or a later runtime phase.  The
API app owns the only in-process transports it needs.  Routers dispatch
through the ``CommandBus`` / ``QueryBus`` Protocol seams, so a future
distributed bus can replace these classes without touching a single route.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from windagent.platform.commands import Command, CommandBus, CommandHandler
from windagent.platform.observability import NoOpTelemetry, Telemetry
from windagent.platform.queries import Query, QueryBus, QueryHandler


class DispatchError(RuntimeError):
    """Base class for expected dispatch failures."""


class DuplicateHandlerError(DispatchError):
    """Raised when a second handler claims the same command or query type."""


class UnregisteredMessageError(DispatchError):
    """Raised when no handler owns the dispatched command or query type."""


def _validated_handler(handler: object, kind: str) -> object:
    if not callable(getattr(handler, "handle", None)):
        raise TypeError(f"{kind} handler must expose a callable handle method")
    return handler


@dataclass(slots=True)
class InProcessCommandBus(CommandBus):
    """Dispatch each command to its single registered in-process handler."""

    _handlers: dict[type[object], object] = field(default_factory=dict, init=False)
    telemetry: Telemetry = field(default_factory=NoOpTelemetry)

    def register(self, command_type: type[object], handler: object) -> None:
        """Bind one command type to the only handler allowed to own it."""
        if not isinstance(command_type, type):
            raise TypeError("command_type must be a class")
        if command_type in self._handlers:
            raise DuplicateHandlerError(
                f"command {command_type.__qualname__!r} already has a handler"
            )
        self._handlers[command_type] = _validated_handler(handler, "command")

    async def dispatch[ResultT](self, command: Command[ResultT]) -> ResultT:
        handler = self._handlers.get(type(command))
        if handler is None:
            raise UnregisteredMessageError(
                f"no handler registered for command {type(command).__qualname__!r}"
            )
        typed_handler = cast(
            CommandHandler[Command[ResultT], ResultT],
            handler,
        )
        message_type = type(command).__qualname__
        span = self.telemetry.start_span(
            "command.dispatch", attributes={"message.type": message_type}
        )
        try:
            result = await typed_handler.handle(command)
        except BaseException as error:
            span.record_exception(error)
            self.telemetry.increment_counter(
                "message.dispatches",
                attributes={"kind": "command", "outcome": "error"},
            )
            raise
        else:
            self.telemetry.increment_counter(
                "message.dispatches",
                attributes={"kind": "command", "outcome": "succeeded"},
            )
            return result
        finally:
            span.end()


@dataclass(slots=True)
class InProcessQueryBus(QueryBus):
    """Resolve each query through its single registered in-process handler."""

    _handlers: dict[type[object], object] = field(default_factory=dict, init=False)
    telemetry: Telemetry = field(default_factory=NoOpTelemetry)

    def register(self, query_type: type[object], handler: object) -> None:
        """Bind one query type to the only handler allowed to own it."""
        if not isinstance(query_type, type):
            raise TypeError("query_type must be a class")
        if query_type in self._handlers:
            raise DuplicateHandlerError(
                f"query {query_type.__qualname__!r} already has a handler"
            )
        self._handlers[query_type] = _validated_handler(handler, "query")

    async def ask[ResultT](self, query: Query[ResultT]) -> ResultT:
        handler = self._handlers.get(type(query))
        if handler is None:
            raise UnregisteredMessageError(
                f"no handler registered for query {type(query).__qualname__!r}"
            )
        typed_handler = cast(QueryHandler[Query[ResultT], ResultT], handler)
        message_type = type(query).__qualname__
        span = self.telemetry.start_span(
            "query.ask", attributes={"message.type": message_type}
        )
        try:
            result = await typed_handler.handle(query)
        except BaseException as error:
            span.record_exception(error)
            self.telemetry.increment_counter(
                "message.dispatches",
                attributes={"kind": "query", "outcome": "error"},
            )
            raise
        else:
            self.telemetry.increment_counter(
                "message.dispatches",
                attributes={"kind": "query", "outcome": "succeeded"},
            )
            return result
        finally:
            span.end()
