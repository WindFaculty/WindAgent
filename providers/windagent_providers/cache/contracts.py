"""
Cache contracts for WindAgent Provider Subsystem V3.

Defines shared types, in-band metadata, and an abstract singleflight port.
No transport implementation here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional, TypeVar

from windagent_providers.base.contracts import ProviderResponse


T = TypeVar("T")


@dataclass(frozen=True)
class CacheNamespace:
    """Logical namespace that isolates cached data by ownership boundary."""

    tenant_id: Optional[str] = None
    user_id: Optional[str] = None

    def key_prefix(self) -> str:
        parts: List[str] = []
        if self.tenant_id:
            parts.append(f"t:{self.tenant_id}")
        if self.user_id:
            parts.append(f"u:{self.user_id}")
        return ":".join(parts) if parts else "global"


@dataclass(frozen=True)
class CacheTags:
    """Tag set for group invalidation."""

    canonical_model_id: Optional[str] = None
    revision: Optional[str] = None
    endpoint_id: Optional[str] = None
    credential_version: Optional[str] = None
    provider_behavior_version: Optional[str] = None


@dataclass
class CacheEntry:
    """Generic cache entry with value and metadata."""

    value: Any
    stored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: CacheTags = field(default_factory=CacheTags)
    ttl_seconds: Optional[int] = None


@dataclass(frozen=True)
class ResponseCacheKey:
    """Structured components of a response cache key."""

    namespace: CacheNamespace
    canonical_model_id: str
    revision: Optional[str]
    messages_hash: str
    system_hash: str
    tools_hash: str
    structured_output_hash: str
    temperature: Optional[float]
    top_p: Optional[float]
    seed: Optional[int]
    max_output_tokens: Optional[int]
    provider_behavior_version: str

    def to_string(self) -> str:
        return (
            f"response:{self.namespace.key_prefix()}"
            f":cm:{self.canonical_model_id}"
            f":rev:{self.revision or 'none'}"
            f":msg:{self.messages_hash}"
            f":sys:{self.system_hash}"
            f":tool:{self.tools_hash}"
            f":json:{self.structured_output_hash}"
            f":t:{self.temperature if self.temperature is not None else 'none'}"
            f":tp:{self.top_p if self.top_p is not None else 'none'}"
            f":seed:{self.seed if self.seed is not None else 'none'}"
            f":max:{self.max_output_tokens if self.max_output_tokens is not None else 'none'}"
            f":pbv:{self.provider_behavior_version}"
        )


@dataclass
class ResponseCacheHit:
    """Wrapper returned on response cache hit."""

    response: ProviderResponse
    cached_at: datetime
    cache_key: str


class SingleFlightPort(ABC):
    """Port for collapsing in-flight duplicate operations across callers."""

    @abstractmethod
    async def do(
        self,
        key: str,
        operation: Any,
    ) -> Any:
        """
        Execute ``operation`` once for ``key`` even if called concurrently.
        Returns the same result (or raises the same exception) to all waiters.
        """
        pass
