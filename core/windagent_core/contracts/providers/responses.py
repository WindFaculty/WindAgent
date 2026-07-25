"""Canonical Provider Response and Streaming models for WindAgent Core contracts (Phase 5)."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.contracts.providers.usage import ProviderUsage
from windagent_core.domain.types import CanonicalModelId, ProviderId


class ProviderToolCall(BaseModel):
    """Canonical representation of a model-generated tool call request."""

    call_id: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ProviderResponse(BaseModel):
    """Canonical model response payload returned by provider adapters."""

    provider_id: Optional[Union[ProviderId, str]] = None
    model_id: Optional[Union[CanonicalModelId, str]] = None
    canonical_model_id: Optional[str] = None
    provider_model_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    content: Optional[str] = None
    text: Optional[str] = None
    tool_calls: List[Any] = Field(default_factory=list)
    structured_output: Optional[Dict[str, Any]] = None
    finish_reason: str = "stop"  # stop, length, tool_calls, error
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    provider_request_id: Optional[str] = None
    first_token_latency_ms: Optional[float] = None
    total_latency_ms: float = 0.0
    cost_usd: float = 0.0
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_response_metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    def model_post_init(self, __context: Any) -> None:
        if self.raw_metadata:
            from windagent_core.security.redaction import redact_dict

            object.__setattr__(
                self, "raw_metadata", redact_dict(self.raw_metadata)
            )


class ProviderStreamChunk(BaseModel):
    """Canonical streaming delta chunk emitted by provider adapters."""

    delta_content: str = ""
    delta_tool_calls: List[Any] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[ProviderUsage] = None

    model_config = ConfigDict(extra="allow")
