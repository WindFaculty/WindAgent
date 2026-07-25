"""Implementation-independent capability and descriptor schemas for providers (Phase 5).

Core owns the capability schema; providers own registry/transport implementations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


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
class ProviderHealth:
    """Endpoint / Adapter Diagnostic Health Record."""

    provider_name: str
    healthy: bool
    latency_ms: float = 0.0
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    last_check_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


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
class ProviderStreamEvent:
    """Structured Event Emission for Streaming Calls."""

    event_type: str  # "token", "thinking_delta", "tool_call_delta", "metadata", "error", "done"
    sequence_number: int
    delta: Optional[str] = None
    reasoning_delta: Optional[str] = None
    tool_call_delta: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    usage: Optional[Any] = None  # ProviderUsage (pydantic); kept loose to avoid module cycle
    error: Optional[str] = None
