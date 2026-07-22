"""
Abstract Base Model Provider Contract for WindAgent Architecture V2.
Declares mandatory methods for model provider integration adapters.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from windagent_core.domain.types import ModelCallId
from windagent_core.domain.models import ModelRequest, ModelResponse
from windagent_providers.capabilities import ModelCapabilityProfile


@dataclass
class ProviderHealth:
    provider_name: str
    healthy: bool
    latency_ms: float = 0.0
    error_message: Optional[str] = None
    last_check_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class QuotaSnapshot:
    provider_name: str
    has_quota: bool = True
    remaining_tokens: Optional[int] = None
    remaining_requests: Optional[int] = None
    reset_at: Optional[datetime] = None


@dataclass
class ModelChunk:
    call_id: ModelCallId
    delta: str
    finish_reason: Optional[str] = None


class BaseModelProvider(ABC):
    def __init__(self, provider_name: str, api_key: Optional[str] = None):
        self.provider_name = provider_name
        self.api_key = api_key

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Lists available models provided by this adapter."""
        pass

    @abstractmethod
    async def health(self) -> ProviderHealth:
        """Runs a diagnostic health check."""
        pass

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Executes a synchronous/complete generation call."""
        pass

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        """Executes a streaming generation call."""
        pass

    @abstractmethod
    def estimate_cost(self, request: ModelRequest) -> float:
        """Estimates request cost in USD."""
        pass

    @abstractmethod
    async def get_quota(self) -> QuotaSnapshot:
        """Queries remaining quota snapshot."""
        pass

    @abstractmethod
    async def cancel(self, call_id: ModelCallId) -> bool:
        """Cancels an ongoing generation call."""
        pass

    @abstractmethod
    def capabilities(self) -> List[ModelCapabilityProfile]:
        """Returns capability profiles supported by this provider's models."""
        pass
