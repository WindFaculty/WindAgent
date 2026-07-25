"""Canonical Provider Request model for WindAgent Core contracts (Phase 5)."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.types import CanonicalModelId, ProviderId
from windagent_core.security.types import SecretRef


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
