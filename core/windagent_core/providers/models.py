"""
Canonical Provider Request, Response, Usage, and Streaming Models for WindAgent Core (Phase 9/12).
Fully unified provider data structures supporting both Pydantic v2 validation and rich V3 adapter contracts.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.types import CanonicalModelId, ProviderId
from windagent_core.security.types import SecretRef


class ProviderUsage(BaseModel):
    """Token consumption and cost tracking facts for provider invocations."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    model_config = ConfigDict(extra="allow")

    def model_post_init(self, __context: Any) -> None:
        if self.total_tokens == 0:
            object.__setattr__(self, "total_tokens", self.prompt_tokens + self.completion_tokens)


class ProviderToolCall(BaseModel):
    """Canonical representation of a model-generated tool call request."""
    call_id: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ProviderRequest(BaseModel):
    """Canonical model request payload sent to provider adapters."""
    provider_id: Optional[Union[ProviderId, str]] = None
    model_id: Optional[Union[CanonicalModelId, str]] = None
    prompt: str = ""
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    system_instruction: Optional[str] = None
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = None
    seed: Optional[int] = None
    max_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    stop_sequences: List[str] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    structured_output_schema: Optional[Dict[str, Any]] = None
    image_parts: List[Dict[str, Any]] = Field(default_factory=list)
    provider_extensions: Dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""
    idempotency_key: Optional[str] = None
    timeout_seconds: Optional[float] = 30.0
    cache_directive: Any = None
    is_cancelled: Any = None
    secret_ref: Optional[SecretRef] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)

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
            try:
                from windagent_providers.base.secret_redaction import redact_dict
                object.__setattr__(self, "raw_metadata", redact_dict(self.raw_metadata))
            except ImportError:
                pass


class ProviderStreamChunk(BaseModel):
    """Canonical streaming delta chunk emitted by provider adapters."""
    delta_content: str = ""
    delta_tool_calls: List[Any] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[ProviderUsage] = None

    model_config = ConfigDict(extra="allow")
