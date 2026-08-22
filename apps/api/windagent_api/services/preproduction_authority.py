"""P1.0 pre-production truth authority — actual locked screenplay resolution.

Single fail-closed seam for resolving the ACTUAL locked screenplay of an
episode from the durable V3 resource authority:

    Episode
       ↓
    Lock authority record (state LOCKED + lock metadata)
       ↓
    LockedScreenplayReceipt artifact (when persisted)
       ↓
    actual revision_id / content_hash / artifact_id

Pre-production consumers (storyboard sync, scene creation, production
planning) MUST resolve screenplay lineage through this module instead of
synthesizing revision identifiers like ``rev-{episode_id}-lock``.

Principles enforced here:
- NO SYNTHETIC AUTHORITY: revision ids come from stored lock records only.
- NO GET-SIDE EFFECT: this module never writes; it is read-only.
- Fail closed: when no locked screenplay exists, callers receive
  ``ScreenplayNotLockedError`` and must not create downstream records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from windagent_api.services.v3_demo_seed import (
    NS_EPISODES,
    NS_EPISODE_ARTIFACTS,
)
from windagent_api.services.v3_resource_service import V3ResourceService

LOCKED_STATE = "LOCKED"
LOCK_RECEIPT_KIND = "LockedScreenplayReceipt"
SCREENPLAY_DRAFT_KIND = "ScreenplayDraft"


class PreproductionAuthorityError(Exception):
    """Fail-closed error raised when pre-production lineage cannot be resolved."""

    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class EpisodeNotFoundError(PreproductionAuthorityError):
    def __init__(self, episode_id: str) -> None:
        super().__init__(
            code="EPISODE_NOT_FOUND",
            message=f"Episode '{episode_id}' not found.",
            http_status=404,
        )
        self.episode_id = episode_id


class ScreenplayNotLockedError(PreproductionAuthorityError):
    def __init__(self, episode_id: str, reason: str) -> None:
        super().__init__(
            code="SCREENPLAY_NOT_LOCKED",
            message=f"Episode '{episode_id}' has no locked screenplay ({reason}). "
            "Sync requires an actual locked screenplay from the lock authority.",
            http_status=409,
        )
        self.episode_id = episode_id
        self.reason = reason


@dataclass(frozen=True)
class LockedScreenplayRef:
    """Immutable reference to the ACTUAL locked screenplay of an episode."""

    episode_id: str
    revision_id: str
    content_hash: str
    artifact_id: Optional[str]


def _is_locked(ep: Dict[str, Any]) -> bool:
    state = str(ep.get("state") or "").upper()
    checkpoint = str(ep.get("current_checkpoint") or "").upper()
    metadata = ep.get("metadata") or {}
    return (
        state == LOCKED_STATE
        or checkpoint == LOCKED_STATE
        or bool(metadata.get("locked_revision_id"))
    )


async def resolve_locked_screenplay(
    service: V3ResourceService, episode_id: str
) -> LockedScreenplayRef:
    """Resolve the actual locked screenplay for an episode (read-only).

    Raises:
        EpisodeNotFoundError: episode does not exist in the authority.
        ScreenplayNotLockedError: episode exists but has no locked screenplay.
    """
    ep = await service.get(NS_EPISODES, episode_id)
    if ep is None:
        raise EpisodeNotFoundError(episode_id)

    if not _is_locked(ep):
        raise ScreenplayNotLockedError(
            episode_id, f"state={ep.get('state')!r}, checkpoint={ep.get('current_checkpoint')!r}"
        )

    metadata = ep.get("metadata") or {}
    revision_id = str(
        metadata.get("locked_revision_id") or ep.get("current_revision_id") or ""
    ).strip()
    if not revision_id:
        raise ScreenplayNotLockedError(episode_id, "no locked revision id recorded")

    artifact_id = await _resolve_receipt_artifact(service, episode_id, revision_id)
    return LockedScreenplayRef(
        episode_id=episode_id,
        revision_id=revision_id,
        content_hash=str(metadata.get("content_hash") or ""),
        artifact_id=artifact_id,
    )


async def _resolve_receipt_artifact(
    service: V3ResourceService, episode_id: str, revision_id: str
) -> Optional[str]:
    """Find the receipt/draft artifact id pinning the locked revision (read-only)."""
    artifacts: List[Dict[str, Any]] = await service.list(NS_EPISODE_ARTIFACTS)
    episode_artifacts = [a for a in artifacts if a.get("episode_id") == episode_id]

    receipts = [
        a for a in episode_artifacts if a.get("kind") == LOCK_RECEIPT_KIND
    ]
    if receipts:
        receipts.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
        return receipts[0].get("artifact_id")

    matching_drafts = [
        a
        for a in episode_artifacts
        if a.get("kind") == SCREENPLAY_DRAFT_KIND
        and a.get("revision_id") == revision_id
    ]
    if matching_drafts:
        matching_drafts.sort(key=lambda a: str(a.get("created_at") or ""), reverse=True)
        return matching_drafts[0].get("artifact_id")

    return None


__all__ = [
    "EpisodeNotFoundError",
    "LockedScreenplayRef",
    "PreproductionAuthorityError",
    "ScreenplayNotLockedError",
    "resolve_locked_screenplay",
]
