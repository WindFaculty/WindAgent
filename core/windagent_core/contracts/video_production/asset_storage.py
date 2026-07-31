"""
AssetStoragePort — canonical contract for content-addressed asset storage.

Storage is keyed by content hash; file-existence checks are never used as a
validity signal (road_map.md REJ-001 / DIR-REQ-005).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.ids import ReferenceAssetId


@runtime_checkable
class AssetStoragePort(Protocol):
    """Port for content-addressed asset storage."""

    async def store(self, asset: ReferenceAsset, data: bytes) -> ReferenceAsset:
        """Store asset bytes; the asset's content hash is authoritative."""
        ...

    async def get(self, asset_id: ReferenceAssetId) -> Optional[bytes]:
        """Retrieve asset bytes by ID."""
        ...

    async def resolve_hash(self, content_hash: str) -> Optional[ReferenceAsset]:
        """Resolve an asset by its content hash (content addressing)."""
        ...


__all__ = ["AssetStoragePort"]
