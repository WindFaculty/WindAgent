"""Domain-agnostic command dispatch contracts.

Implementations belong to a composition root or a later runtime phase.  A
feature module may depend on these interfaces, but this module must never know
which commands a feature defines.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

CommandT_contra = TypeVar("CommandT_contra", bound="Command[object]", contravariant=True)
HandlerResultT_co = TypeVar("HandlerResultT_co", covariant=True)


class Command[ResultT_co]:
    """Marker base for an intention that produces ``ResultT_co`` when handled."""

    __slots__ = ()


@runtime_checkable
class CommandHandler(Protocol[CommandT_contra, HandlerResultT_co]):
    """Handles exactly one command shape.

    Handler selection, transactions, retries, and transport concerns are owned
    by later phases; the contract only fixes the application boundary.
    """

    async def handle(self, command: CommandT_contra) -> HandlerResultT_co:
        """Execute the command and return its application result."""


@runtime_checkable
class CommandBus(Protocol):
    """Dispatches a command to its single registered handler."""

    async def dispatch[ResultT](self, command: Command[ResultT]) -> ResultT:
        """Route ``command`` without exposing handler lookup to callers."""
