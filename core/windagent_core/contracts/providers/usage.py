"""Canonical Provider Usage model for WindAgent Core contracts (Phase 5)."""

from __future__ import annotations
from typing import Any

from pydantic import BaseModel, ConfigDict


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
            object.__setattr__(
                self, "total_tokens", self.prompt_tokens + self.completion_tokens
            )
