"""
Strongly-typed Identifier Value Objects for WindAgent Domain Core (V2 Canonical Architecture).
Distinguishes between UUID-backed domain entity IDs and opaque string-backed external/runtime IDs.
"""

from __future__ import annotations
import uuid
import re
from typing import TypeVar, Any, Optional
from pydantic_core import core_schema
from windagent_core.errors.exceptions import IdentityValidationError

T_UUID = TypeVar("T_UUID", bound="UUIDEntityId")
T_Opaque = TypeVar("T_Opaque", bound="OpaqueId")


class UUIDEntityId:
    """
    Base class for all internal UUID-backed domain entity identifiers.
    Guarantees that the value is a valid UUIDv4 string representation.
    """
    __slots__ = ("_value", "_uuid_obj")

    def __init__(self, value: str | uuid.UUID) -> None:
        if value is None:
            raise IdentityValidationError("UUID identifier value cannot be missing or None.")
        
        if isinstance(value, uuid.UUID):
            self._uuid_obj = value
            self._value = str(value)
        elif isinstance(value, str):
            val_str = value.strip()
            if not val_str:
                raise IdentityValidationError("UUID identifier string cannot be empty.")
            try:
                parsed_uuid = uuid.UUID(val_str)
                self._uuid_obj = parsed_uuid
                self._value = str(parsed_uuid)
            except (ValueError, AttributeError) as exc:
                raise IdentityValidationError(
                    f"Invalid UUID string format for {self.__class__.__name__}: {val_str!r}"
                ) from exc
        else:
            raise IdentityValidationError(
                f"Invalid identifier type for {self.__class__.__name__}: {type(value)}"
            )

    @classmethod
    def generate(cls: type[T_UUID]) -> T_UUID:
        """Explicitly generate a new UUIDv4 entity identifier."""
        return cls(uuid.uuid4())

    @property
    def value(self) -> str:
        return self._value

    def to_uuid(self) -> uuid.UUID:
        """Return the underlying Python uuid.UUID object."""
        return self._uuid_obj

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self._value == other._value
        if isinstance(other, uuid.UUID):
            return self._uuid_obj == other
        if isinstance(other, str):
            return self._value == other
        return False

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self._value))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(cls),
            ]),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(cls),
                core_schema.chain_schema([
                    core_schema.union_schema([
                        core_schema.str_schema(),
                        core_schema.is_instance_schema(uuid.UUID),
                    ]),
                    core_schema.no_info_plain_validator_function(cls),
                ]),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: instance.value if isinstance(instance, cls) else str(instance)
            ),
        )


class OpaqueId:
    """
    Base class for external, provider, or runtime opaque identifiers.
    Backed by non-empty string without UUID validation.
    Does NOT provide to_uuid().
    """
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if value is None:
            raise IdentityValidationError("Opaque identifier value cannot be missing or None.")
        if not isinstance(value, str):
            raise IdentityValidationError(
                f"Invalid opaque identifier type for {self.__class__.__name__}: {type(value)}"
            )
        val_str = value.strip()
        if not val_str:
            raise IdentityValidationError("Opaque identifier string cannot be empty.")
        self._value = val_str

    @classmethod
    def of(cls: type[T_Opaque], value: str) -> T_Opaque:
        """Create an instance from an opaque string."""
        return cls(value)

    @classmethod
    def generate(cls: type[T_Opaque], prefix: str = "") -> T_Opaque:
        raw = str(uuid.uuid4())
        val = f"{prefix}_{raw}" if prefix else raw
        return cls(val)

    @property
    def value(self) -> str:
        return self._value

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, self.__class__):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return False

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self._value))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(cls),
            ]),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(cls),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls),
                ]),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: instance.value if isinstance(instance, cls) else str(instance)
            ),
        )


# --- UUID Domain Entity IDs ---

class TaskId(UUIDEntityId):
    """Identifier for a Task aggregate."""
    pass


class TaskRunId(UUIDEntityId):
    """Identifier for a TaskRun execution instance."""
    pass


# Backward-compatibility alias
RunId = TaskRunId


class SessionId(UUIDEntityId):
    """Identifier for a user/chat session."""
    pass


class WorkflowId(UUIDEntityId):
    """Identifier for a Workflow definition."""
    pass


class WorkflowRunId(UUIDEntityId):
    """Identifier for a WorkflowRun execution instance."""
    pass


class StepId(UUIDEntityId):
    """Identifier for a WorkflowStep within a workflow definition."""
    pass


class StepRunId(UUIDEntityId):
    """Identifier for a StepRun execution instance."""
    pass


class EventId(UUIDEntityId):
    """Identifier for a domain event."""
    pass


class ArtifactId(UUIDEntityId):
    """Identifier for a persisted artifact."""
    pass


class PermissionRequestId(UUIDEntityId):
    """Identifier for a security permission evaluation request."""
    pass


class ToolCallId(UUIDEntityId):
    """Identifier for a ToolInvocation."""
    pass


class ToolInvocationId(UUIDEntityId):
    """Identifier for a ToolInvocation."""
    pass


class DecisionId(UUIDEntityId):
    """Identifier for a security PermissionDecision."""
    pass


class ModelCallId(UUIDEntityId):
    """Identifier for a ModelRequest execution."""
    pass


# --- Opaque External / Runtime IDs ---

class ProviderId(OpaqueId):
    """Identifier for an LLM provider (e.g. 'openai', 'anthropic')."""
    pass


class EndpointId(OpaqueId):
    """Identifier for a provider endpoint (e.g. 'ep_openai_v1')."""
    pass


class CanonicalModelId(OpaqueId):
    """Canonical model identifier (e.g. 'gpt-4o', 'claude-3-5-sonnet')."""
    pass


class ProviderModelId(OpaqueId):
    """Provider-specific model string identifier."""
    pass


class RuntimeRunId(OpaqueId):
    """Execution runtime engine process or run ID."""
    pass


class RuntimeSessionId(OpaqueId):
    """Execution runtime session ID."""
    pass


class WorkerId(OpaqueId):
    """Identifier for a registered worker node/process."""
    pass


class RouteLockId(OpaqueId):
    """Identifier for a provider route lock."""
    pass


class RouteAttemptId(OpaqueId):
    """Identifier for a route dispatch attempt."""
    pass


class ExternalRequestId(OpaqueId):
    """Identifier for an external HTTP or provider request."""
    pass


# --- Migration Identity Classifier ---

_UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_OPAQUE_PREFIX_REGEX = re.compile(
    r"^(prv|end|wkr|req|rt|lock|att|usr|sys)_[a-zA-Z0-9_\-]+$"
)


def classify_identifier(value: Any) -> str:
    """
    Classify an identifier string into 'uuid', 'opaque_prefix', 'opaque', or 'invalid'.
    """
    if not isinstance(value, str):
        return "invalid"
    val_str = value.strip()
    if not val_str:
        return "invalid"
    if _UUID_REGEX.match(val_str):
        return "uuid"
    if _OPAQUE_PREFIX_REGEX.match(val_str):
        return "opaque_prefix"
    return "opaque"
