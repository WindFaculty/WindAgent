"""Domain-agnostic query dispatch contracts."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

QueryT_contra = TypeVar("QueryT_contra", bound="Query[object]", contravariant=True)
HandlerResultT_co = TypeVar("HandlerResultT_co", covariant=True)


class Query[ResultT_co]:
    """Marker base for a side-effect-free request for application data."""

    __slots__ = ()


@runtime_checkable
class QueryHandler(Protocol[QueryT_contra, HandlerResultT_co]):
    """Resolves one query shape into a result."""

    async def handle(self, query: QueryT_contra) -> HandlerResultT_co:
        """Resolve the query without leaking an infrastructure adapter."""


@runtime_checkable
class QueryBus(Protocol):
    """Dispatches a query to its single registered handler."""

    async def ask[ResultT](self, query: Query[ResultT]) -> ResultT:
        """Resolve ``query`` through the application's query boundary."""
