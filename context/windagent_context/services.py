"""Query service aliases for composition roots.

ContextService is the async facade over ContextPipeline used by API/Worker
composition roots. It exposes the minimum surface the composition root calls.
"""
from __future__ import annotations

from windagent_context.pipeline import ContextPipeline, ContextPipelineConfig


class ContextService:
    """Async query service over ContextPipeline."""

    def __init__(self, pipeline: ContextPipeline | None = None) -> None:
        self._pipeline = pipeline or ContextPipeline(ContextPipelineConfig())

    async def assemble(self, *args, **kwargs):  # ponytail: thin pass-through
        return self._pipeline.assemble(*args, **kwargs)

    async def close(self) -> None:
        pass


__all__ = ["ContextService"]
