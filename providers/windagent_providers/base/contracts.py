"""
Unified Provider Data Contracts for WindAgent Provider Subsystem V3.
100% Type-Annotated dataclasses and immutable specifications.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from windagent_providers.base.secret_redaction import redact_dict


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


@dataclass
class CacheDirective:
    """Caching instructions for prompt caching & response caching."""
    enable_prompt_cache: bool = False
    enable_response_cache: bool = False
    ttl_seconds: Optional[int] = None
    cache_key_override: Optional[str] = None


@dataclass
class ProviderUsage:
    """Standardized Token Usage and Cost Metrics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass
class ProviderHealth:
    """Endpoint / Adapter Diagnostic Health Record."""
    provider_name: str
    healthy: bool
    latency_ms: float = 0.0
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    last_check_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class QuotaState:
    """Snapshot of Provider Quota Balance."""
    provider_id: str
    has_quota: bool = True
    remaining_requests_today: Optional[int] = None
    remaining_tokens_today: Optional[int] = None
    remaining_credit: Optional[float] = None
    credit_currency: Optional[str] = None
    reset_at: Optional[datetime] = None


@dataclass
class RateLimitState:
    """Current Rate Limit Status (RPM / TPM)."""
    rpm_limit: Optional[int] = None
    rpm_remaining: Optional[int] = None
    tpm_limit: Optional[int] = None
    tpm_remaining: Optional[int] = None
    retry_after_seconds: Optional[float] = None


@dataclass
class ProviderCapabilities:
    """Capability Descriptor for Model Capabilities."""
    supports_chat: bool = True
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    supports_structured_output: bool = False
    supports_prompt_caching: bool = False
    max_context_window: int = 128000
    max_output_tokens: int = 4096


@dataclass
class ModelDescriptor:
    """Canonical or Provider Model Descriptor."""
    model_id: str
    provider_id: str
    display_name: str
    vendor: str
    family: str
    revision: Optional[str] = None
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)


@dataclass
class DiscoveredModel:
    """Dynamically Discovered Model Information."""
    raw_model_id: str
    canonical_name: str
    provider_id: str
    context_window: Optional[int] = None
    capabilities: List[str] = field(default_factory=list)


@dataclass
class ConnectionTestResult:
    """Result payload for Test Connect interactions."""
    success: bool
    provider_id: str
    endpoint_url: Optional[str] = None
    detected_protocol: Optional[str] = None
    detected_vendor: Optional[str] = None
    confidence_score: float = 0.0
    evidence: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    error_message: Optional[str] = None


@dataclass
class ProtocolDetectionResult:
    """Fingerprint match result during Test Connect probe."""
    protocol_type: str  # "openai", "anthropic", "gemini", "ollama"
    vendor: str
    confidence: float
    evidence: List[str]


@dataclass
class ProviderRequest:
    """Unified Request Contract for Model Execution."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_instruction: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    seed: Optional[int] = None
    max_output_tokens: Optional[int] = None
    stop_sequences: List[str] = field(default_factory=list)
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    structured_output_schema: Optional[Dict[str, Any]] = None
    image_parts: List[Dict[str, Any]] = field(default_factory=list)
    provider_extensions: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=str)
    idempotency_key: Optional[str] = None
    timeout_seconds: Optional[float] = 30.0
    cache_directive: Optional[CacheDirective] = None
    is_cancelled: Optional[Callable[[], bool]] = None


@dataclass
class ProviderResponse:
    """Unified Response Contract for Synchronous Model Execution."""
    canonical_model_id: str
    provider_model_id: str
    endpoint_id: Optional[str] = None
    text: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    structured_output: Optional[Dict[str, Any]] = None
    finish_reason: str = FinishReason.STOP.value
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    provider_request_id: Optional[str] = None
    first_token_latency_ms: Optional[float] = None
    total_latency_ms: float = 0.0
    cost_usd: float = 0.0
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Automatically redact raw metadata upon creation
        if self.raw_metadata:
            self.raw_metadata = redact_dict(self.raw_metadata)


@dataclass
class ProviderStreamEvent:
    """Structured Event Emission for Streaming Calls."""
    event_type: str  # "token", "thinking_delta", "tool_call_delta", "metadata", "error", "done"
    sequence_number: int
    delta: Optional[str] = None
    reasoning_delta: Optional[str] = None
    tool_call_delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    usage: Optional[ProviderUsage] = None
    error: Optional[str] = None
