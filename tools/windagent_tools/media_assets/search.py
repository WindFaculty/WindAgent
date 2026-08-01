"""
AssetSearchService (plan 02 §21.1) — acquisition search.

Search records the query, source provider, result URL and retrieval time.
Results exist ONLY in the DISCOVERED lifecycle state — they are never used
as a reference until downloaded, validated, and approved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Protocol

from windagent_core.domain.video_production.asset_lifecycle import (
    AssetLifecycleState,
)

from windagent_tools.media_assets.errors import UrlBlockedError
from windagent_tools.media_assets.security import validate_download_url


@dataclass(frozen=True)
class SearchResult:
    """A single DISCOVERED search result."""

    result_id: str
    query: str
    source_provider: str
    source_url: str
    retrieved_at: datetime
    lifecycle_state: AssetLifecycleState = AssetLifecycleState.DISCOVERED
    metadata: dict = field(default_factory=dict)

    @property
    def asset_id(self) -> str:
        return self.result_id


class SearchProviderPort(Protocol):
    """Port a search backend implements (never leaks provider SDK objects)."""

    def search(self, query: str, *, limit: int = 10) -> List[dict]:
        """Return raw search items with at least 'url' and 'title' keys."""
        ...


class AssetSearchService:
    """Records acquisition search results as DISCOVERED assets only."""

    def __init__(self, provider: Optional[SearchProviderPort] = None) -> None:
        self.provider = provider

    def search(
        self,
        query: str,
        *,
        provider: Optional[str] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        if self.provider is None:
            return []
        provider_name = provider or getattr(self.provider, "name", "unknown")
        raw_items = self.provider.search(query, limit=limit)
        now = datetime.now(timezone.utc)
        results: List[SearchResult] = []
        for idx, item in enumerate(raw_items):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            # Validate scheme/host now so DISCOVERED records never carry
            # SSRF-prone URLs (plan 02 §21.1).
            try:
                validate_download_url(url)
            except UrlBlockedError:
                continue
            results.append(
                SearchResult(
                    result_id=item.get("id") or f"discovered_{idx}_{provider_name}",
                    query=query,
                    source_provider=provider_name,
                    source_url=url,
                    retrieved_at=now,
                    metadata={k: v for k, v in item.items() if k not in ("url", "id")},
                )
            )
        return results


__all__ = ["AssetSearchService", "SearchResult", "SearchProviderPort"]
