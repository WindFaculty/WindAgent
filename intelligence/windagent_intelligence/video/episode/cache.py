"""
Episode asset cache (VP3D Phase 26, Stage M).

Reuse registry for character/environment/animation/audio assets across
scenes AND across runs (backlog 1): a cache entry pins (kind, revision,
content hash, approval state). `resolve` returns one of four decisions
(backlog 6):

    HIT            — entry exists, hash matches, approved -> REUSED;
    MISS           — no entry -> generate;
    INVALIDATED    — entry exists but hash differs (stale revision) -> generate;
    REJECTED_REUSE — entry exists + hash matches but policy forbids reuse
                     (unapproved) -> generate, never reuse.

Persisted as JSON next to the checkpoint dir so reuse survives restarts.
This module is intelligence-side and never imports tools/providers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from windagent_core.domain.video_production.episode import (
    EpisodeArtifactKind,
    EpisodeCacheDecision,
    EpisodeCacheEntry,
    EpisodeCacheReport,
)
from windagent_core.domain.video_production.errors import (
    EpisodeCachePolicyError,
)
from windagent_core.domain.video_production.golden_scene import (
    compute_content_hash,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EpisodeAssetCache:
    """Persisted, fail-closed asset reuse registry.

    Usage (orchestrator):
        decision, entry = cache.resolve(key, expected_hash, approved=True)
        if decision == HIT: reuse entry (record_reuse)
        else: generate, then cache.record_generated(...)
    """

    def __init__(self, cache_dir: Path) -> None:
        self._path = Path(cache_dir) / "episode_asset_cache.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, EpisodeCacheEntry] = {}
        self._decisions: Dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key, data in payload.get("entries", {}).items():
            try:
                self._entries[key] = EpisodeCacheEntry.model_validate(data)
            except Exception:
                continue

    def save(self) -> None:
        payload = {
            "entries": {
                key: entry.model_dump() for key, entry in self._entries.items()
            }
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def resolve(
        self,
        cache_key: str,
        expected_hash: str,
        *,
        approved: bool = True,
    ) -> tuple[str, Optional[EpisodeCacheEntry]]:
        """Decide HIT / MISS / INVALIDATED / REJECTED_REUSE for one asset.

        Never reuses an asset whose recorded hash differs from the expected
        one (stale revision -> INVALIDATED) and never reuses an unapproved
        asset (REJECTED_REUSE) — both fall through to regeneration.
        """
        entry = self._entries.get(cache_key)
        if entry is None:
            self._decisions[cache_key] = EpisodeCacheDecision.MISS.value
            return EpisodeCacheDecision.MISS.value, None
        if entry.content_hash != expected_hash:
            self._decisions[cache_key] = EpisodeCacheDecision.INVALIDATED.value
            return EpisodeCacheDecision.INVALIDATED.value, None
        if approved and not entry.approved:
            self._decisions[cache_key] = EpisodeCacheDecision.REJECTED_REUSE.value
            return EpisodeCacheDecision.REJECTED_REUSE.value, None
        self._decisions[cache_key] = EpisodeCacheDecision.HIT.value
        return EpisodeCacheDecision.HIT.value, entry

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record_generated(
        self,
        cache_key: str,
        kind: EpisodeArtifactKind,
        revision: str,
        content_hash: str,
        *,
        approved: bool = True,
    ) -> EpisodeCacheEntry:
        prev = self._entries.get(cache_key)
        entry = EpisodeCacheEntry(
            cache_key=cache_key,
            kind=kind,
            revision=revision,
            content_hash=content_hash,
            approved=approved,
            usage_count=prev.usage_count if prev else 0,
            last_used=utc_now_iso(),
        )
        self._entries[cache_key] = entry
        return entry

    def record_reuse(self, cache_key: str) -> Optional[EpisodeCacheEntry]:
        entry = self._entries.get(cache_key)
        if entry is None:
            raise EpisodeCachePolicyError(
                f"Cannot record reuse of unknown cache key {cache_key}.",
                details={"cache_key": cache_key},
            )
        updated = entry.model_copy(
            update={"usage_count": entry.usage_count + 1, "last_used": utc_now_iso()}
        )
        self._entries[cache_key] = updated
        return updated

    def mark_unapproved(self, cache_key: str) -> None:
        entry = self._entries.get(cache_key)
        if entry is not None:
            self._entries[cache_key] = entry.model_copy(update={"approved": False})

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def report(self) -> EpisodeCacheReport:
        return EpisodeCacheReport(
            decisions=dict(self._decisions),
            entries=dict(self._entries),
        )

    def clear_decisions(self) -> None:
        self._decisions = {}

    def entry(self, cache_key: str) -> Optional[EpisodeCacheEntry]:
        return self._entries.get(cache_key)

    @property
    def entries(self) -> Dict[str, EpisodeCacheEntry]:
        return dict(self._entries)


def asset_expected_hash(kind: EpisodeArtifactKind, asset_id: str, revision: str) -> str:
    """Deterministic expected content hash for a pinned asset revision."""
    return compute_content_hash(
        {
            "kind": kind.value,
            "asset_id": asset_id,
            "revision": revision,
        }
    )
