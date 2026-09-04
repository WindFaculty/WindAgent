"""In-process command/query bus contracts (composition-root owned)."""

from __future__ import annotations

import pytest
from windagent.platform.commands import Command
from windagent.platform.observability import InMemoryTelemetry
from windagent.platform.queries import Query
from windagent_api.bootstrap.buses import (
    DuplicateHandlerError,
    InProcessCommandBus,
    InProcessQueryBus,
    UnregisteredMessageError,
)


class PingCommand(Command[str]):
    __slots__ = ()


class GetAnswerQuery(Query[int]):
    __slots__ = ()


class PingHandler:
    async def handle(self, command: PingCommand) -> str:
        return f"ping:{type(command).__name__}"


class AnswerHandler:
    def __init__(self, answer: int) -> None:
        self._answer = answer

    async def handle(self, query: GetAnswerQuery) -> int:
        return self._answer


class NotAHandler:
    pass


async def test_command_bus_dispatches_to_the_single_owner() -> None:
    telemetry = InMemoryTelemetry()
    bus = InProcessCommandBus(telemetry=telemetry)
    bus.register(PingCommand, PingHandler())
    assert await bus.dispatch(PingCommand()) == "ping:PingCommand"
    assert telemetry.spans[0].name == "command.dispatch"
    assert telemetry.spans[0].attributes["message.type"] == "PingCommand"
    assert telemetry.metrics.counters()[0].value == 1


async def test_command_bus_rejects_unknown_commands() -> None:
    bus = InProcessCommandBus()
    with pytest.raises(UnregisteredMessageError):
        await bus.dispatch(PingCommand())


async def test_command_bus_rejects_a_second_owner() -> None:
    bus = InProcessCommandBus()
    bus.register(PingCommand, PingHandler())
    with pytest.raises(DuplicateHandlerError):
        bus.register(PingCommand, PingHandler())


def test_command_bus_rejects_non_handler_and_non_type() -> None:
    bus = InProcessCommandBus()
    with pytest.raises(TypeError):
        bus.register(PingCommand, NotAHandler())
    with pytest.raises(TypeError):
        bus.register("not-a-type", PingHandler())  # type: ignore[arg-type]


async def test_query_bus_resolves_through_the_single_owner() -> None:
    telemetry = InMemoryTelemetry()
    bus = InProcessQueryBus(telemetry=telemetry)
    bus.register(GetAnswerQuery, AnswerHandler(42))
    assert await bus.ask(GetAnswerQuery()) == 42
    assert telemetry.spans[0].name == "query.ask"


async def test_query_bus_rejects_unknown_queries() -> None:
    bus = InProcessQueryBus()
    with pytest.raises(UnregisteredMessageError):
        await bus.ask(GetAnswerQuery())


async def test_query_bus_rejects_a_second_owner() -> None:
    bus = InProcessQueryBus()
    bus.register(GetAnswerQuery, AnswerHandler(1))
    with pytest.raises(DuplicateHandlerError):
        bus.register(GetAnswerQuery, AnswerHandler(2))


def test_query_bus_rejects_non_handler() -> None:
    bus = InProcessQueryBus()
    with pytest.raises(TypeError):
        bus.register(GetAnswerQuery, NotAHandler())
