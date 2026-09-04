"""Declarative, framework-free definitions for independently loadable modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .contracts import ModuleDescriptor


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


def _require_handler(value: object, field: str) -> object:
    if not callable(getattr(value, "handle", None)):
        raise TypeError(f"{field} must expose a callable handle method")
    return value


def _require_tuple(value: tuple[object, ...], field: str) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")
    return value


@dataclass(frozen=True, slots=True)
class CommandRegistration:
    """Connect one command class to its single application handler."""

    command_type: type[object]
    handler: object

    def __post_init__(self) -> None:
        if not isinstance(self.command_type, type):
            raise TypeError("command_type must be a class")
        object.__setattr__(self, "handler", _require_handler(self.handler, "handler"))

    @property
    def key(self) -> str:
        """Stable diagnostic key used to detect a second owner."""
        return f"{self.command_type.__module__}.{self.command_type.__qualname__}"


@dataclass(frozen=True, slots=True)
class QueryRegistration:
    """Connect one query class to its single application handler."""

    query_type: type[object]
    handler: object

    def __post_init__(self) -> None:
        if not isinstance(self.query_type, type):
            raise TypeError("query_type must be a class")
        object.__setattr__(self, "handler", _require_handler(self.handler, "handler"))

    @property
    def key(self) -> str:
        """Stable diagnostic key used to detect a second owner."""
        return f"{self.query_type.__module__}.{self.query_type.__qualname__}"


@dataclass(frozen=True, slots=True)
class JobRegistration:
    """Connect a stable job type name to the handler that owns it."""

    job_type: str
    handler: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_type", _required_text(self.job_type, "job_type"))
        object.__setattr__(self, "handler", _require_handler(self.handler, "handler"))


@dataclass(frozen=True, slots=True)
class EventHandlerRegistration:
    """Subscribe one handler to a stable event type name.

    Events deliberately allow more than one registration for the same event
    type, unlike commands, queries, and jobs which each have one owner.
    """

    event_type: str
    handler: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", _required_text(self.event_type, "event_type"))
        object.__setattr__(self, "handler", _require_handler(self.handler, "handler"))


_EMPTY_OBJECTS: Final[tuple[object, ...]] = ()
_EMPTY_COMMANDS: Final[tuple[CommandRegistration, ...]] = ()
_EMPTY_QUERIES: Final[tuple[QueryRegistration, ...]] = ()
_EMPTY_JOBS: Final[tuple[JobRegistration, ...]] = ()
_EMPTY_EVENT_HANDLERS: Final[tuple[EventHandlerRegistration, ...]] = ()
_EMPTY_TEXT: Final[tuple[str, ...]] = ()


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """The complete, declarative surface that one feature module contributes.

    Router and migration entries remain ``object`` intentionally. The loader
    treats them as opaque application-owned values, so this contract does not
    pull FastAPI or Alembic into the platform before their phases begin.
    """

    id: str
    version: str
    commands: tuple[CommandRegistration, ...] = _EMPTY_COMMANDS
    queries: tuple[QueryRegistration, ...] = _EMPTY_QUERIES
    jobs: tuple[JobRegistration, ...] = _EMPTY_JOBS
    event_handlers: tuple[EventHandlerRegistration, ...] = _EMPTY_EVENT_HANDLERS
    routers: tuple[object, ...] = _EMPTY_OBJECTS
    migrations: tuple[object, ...] = _EMPTY_OBJECTS
    capabilities: tuple[str, ...] = _EMPTY_TEXT

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "id"))
        object.__setattr__(self, "version", _required_text(self.version, "version"))
        self._validate_registrations("commands", self.commands, CommandRegistration)
        self._validate_registrations("queries", self.queries, QueryRegistration)
        self._validate_registrations("jobs", self.jobs, JobRegistration)
        self._validate_registrations("event_handlers", self.event_handlers, EventHandlerRegistration)
        self._validate_opaque_entries("routers", self.routers)
        self._validate_opaque_entries("migrations", self.migrations)

        normalized_capabilities = tuple(
            _required_text(capability, "capability") for capability in self.capabilities
        )
        if len(set(normalized_capabilities)) != len(normalized_capabilities):
            raise ValueError("capabilities must not contain duplicates")
        object.__setattr__(self, "capabilities", normalized_capabilities)

    @staticmethod
    def _validate_registrations(
        field: str, values: tuple[object, ...], expected_type: type[object]
    ) -> None:
        _require_tuple(values, field)
        if any(not isinstance(value, expected_type) for value in values):
            raise TypeError(f"{field} must contain only {expected_type.__name__} values")

    @staticmethod
    def _validate_opaque_entries(field: str, values: tuple[object, ...]) -> None:
        _require_tuple(values, field)
        if any(value is None for value in values):
            raise ValueError(f"{field} cannot contain None")

    @property
    def descriptor(self) -> ModuleDescriptor:
        """Expose only the stable identity needed by module consumers."""
        return ModuleDescriptor(self.id, self.version, self.capabilities)
