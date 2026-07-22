"""
Strongly-typed Identifier Value Objects for WindAgent Domain Core.
Enforces type safety across entity IDs without raw string/UUID passing.
"""

from __future__ import annotations
import uuid
from typing import Generic, TypeVar, Any


T = TypeVar("T", bound="BaseEntityId")


class BaseEntityId:
    __slots__ = ("_value",)

    def __init__(self, value: str | uuid.UUID | None = None) -> None:
        if value is None:
            val_str = str(uuid.uuid4())
        elif isinstance(value, uuid.UUID):
            val_str = str(value)
        elif isinstance(value, str):
            val_str = value.strip()
            if not val_str:
                raise ValueError("Entity identifier string cannot be empty.")
        else:
            raise TypeError(f"Invalid identifier type: {type(value)}")
        
        object.__setattr__(self, "_value", val_str)

    @classmethod
    def generate(cls: type[T]) -> T:
        return cls(uuid.uuid4())

    @property
    def value(self) -> str:
        return self._value

    def to_uuid(self) -> uuid.UUID:
        return uuid.UUID(self._value)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self._value == other._value
        if isinstance(other, (str, uuid.UUID)):
            return self._value == str(other)
        return False

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self._value))


class TaskId(BaseEntityId):
    """Identifier for a Task entity."""
    pass


class RunId(BaseEntityId):
    """Identifier for a TaskRun or WorkflowRun execution instance."""
    pass


class SessionId(BaseEntityId):
    """Identifier for a user/chat session."""
    pass


class WorkflowId(BaseEntityId):
    """Identifier for a Workflow definition or run."""
    pass


class StepId(BaseEntityId):
    """Identifier for a WorkflowStep within a workflow."""
    pass


class ToolCallId(BaseEntityId):
    """Identifier for a ToolInvocation."""
    pass


class ModelCallId(BaseEntityId):
    """Identifier for a ModelRequest/Response call."""
    pass


class EventId(BaseEntityId):
    """Identifier for a domain or system event."""
    pass


class ArtifactId(BaseEntityId):
    """Identifier for a generated or persisted artifact."""
    pass
