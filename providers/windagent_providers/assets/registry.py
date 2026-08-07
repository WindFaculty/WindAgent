"""
Adapter registry for the Universal Asset Gateway (VP3D Phase 5).

Registration order defines the default discovery order. Adapter ids are stable
and versioned; a duplicate id is a configuration error, not a silent override.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.asset_resolution import (
    AssetProviderCapability,
)

from windagent_providers.assets.adapter import AssetAdapter


class AssetAdapterRegistry:
    """Registry of asset adapters keyed by stable adapter_id."""

    def __init__(self) -> None:
        self._adapters: Dict[str, AssetAdapter] = {}

    def register(self, adapter: AssetAdapter) -> None:
        if not adapter.adapter_id:
            raise ValueError("adapter_id must not be empty")
        if adapter.adapter_id in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.adapter_id}")
        self._adapters[adapter.adapter_id] = adapter

    def get(self, adapter_id: str) -> Optional[AssetAdapter]:
        return self._adapters.get(adapter_id)

    def list(self) -> List[AssetAdapter]:
        return list(self._adapters.values())

    def capabilities(self) -> List[AssetProviderCapability]:
        return [adapter.capability() for adapter in self.list()]


__all__ = ["AssetAdapterRegistry"]
