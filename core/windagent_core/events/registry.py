"""
Typed Payload Registry and Schema Mapping for WindAgent Canonical Events (Phase 5).
Maps event names to Pydantic v2 payload models.
"""

from __future__ import annotations
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, ConfigDict


class BaseEventPayload(BaseModel):
    """Base class for all typed event payload models."""
    model_config = ConfigDict(frozen=True, extra="allow")


class TaskCreatedPayload(BaseEventPayload):
    task_id: str
    session_id: str
    prompt: str
    priority: int = 0


class TaskTransitionedPayload(BaseEventPayload):
    task_id: str
    from_state: str
    to_state: str
    previous_version: int
    new_version: int
    reason: Optional[str] = None


class WorkflowStartedPayload(BaseEventPayload):
    workflow_id: str
    task_run_id: str
    node_count: int


class StepCompletedPayload(BaseEventPayload):
    step_id: str
    tool_name: str
    output: Any
    duration_ms: float


class PermissionRequestedPayload(BaseEventPayload):
    request_id: str
    action: str
    target: str
    risk_level: str


class ProviderRequestFailedPayload(BaseEventPayload):
    provider_id: str
    endpoint_id: Optional[str] = None
    error_code: str
    message: str
    retryable: bool


class EventRegistry:
    """Registry mapping canonical event dotted names to typed payload models."""
    _PAYLOAD_MAP: Dict[str, Type[BaseEventPayload]] = {
        "task.created": TaskCreatedPayload,
        "task.transitioned": TaskTransitionedPayload,
        "workflow.started": WorkflowStartedPayload,
        "step.completed": StepCompletedPayload,
        "permission.requested": PermissionRequestedPayload,
        "provider.request.failed": ProviderRequestFailedPayload,
    }

    @classmethod
    def register(cls, event_type: str, payload_cls: Type[BaseEventPayload]) -> None:
        cls._PAYLOAD_MAP[event_type] = payload_cls

    @classmethod
    def get_payload_model(cls, event_type: str) -> Optional[Type[BaseEventPayload]]:
        return cls._PAYLOAD_MAP.get(event_type)

    @classmethod
    def parse_payload(cls, event_type: str, raw_payload: Dict[str, Any]) -> BaseEventPayload:
        model_cls = cls.get_payload_model(event_type)
        if model_cls:
            return model_cls.model_validate(raw_payload)
        return BaseEventPayload.model_validate(raw_payload)
