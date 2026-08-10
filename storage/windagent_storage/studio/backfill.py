"""Deterministic Studio backfill helpers (Plan A — A3).

Pure stdlib functions shared by the A3 migration (raw SQL driver) and the
dual-read repositories (async driver) so both derive the same synthetic
identities. Backfill NEVER invents story content: only structural metadata
(ids, timestamps, statuses, a structural checksum for legacy rows that carry
no content hash) is produced.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

BACKFILL_MARKER = "backfill:v1"
SYNTHETIC_EPISODE_PREFIX = "backfill_ep_"
SYNTHETIC_ACTOR = "legacy:migration"


def synthetic_episode_id(project_id_value: str) -> str:
    """Deterministic episode id for the single placeholder episode of a legacy project."""
    digest = hashlib.sha256(project_id_value.encode("utf-8")).hexdigest()[:16]
    return f"{SYNTHETIC_EPISODE_PREFIX}{project_id_value}_{digest}"


def legacy_revision_content_hash(revision_id: str, sequence: int, legacy_status: str) -> str:
    """Deterministic 64-char structural checksum for legacy revisions without a real hash."""
    payload = {
        "backfill": BACKFILL_MARKER,
        "revision_id": revision_id,
        "legacy_sequence": sequence,
        "legacy_status": legacy_status,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def normalize_legacy_hash(value: str, revision_id: str, sequence: int, legacy_status: str) -> str:
    """Keep a real legacy content hash; derive a structural one only when absent."""
    if is_valid_sha256(value):
        return value
    return legacy_revision_content_hash(revision_id, sequence, legacy_status)


def series_metadata(*, legacy_status: str, legacy_active_revision_id: str) -> Dict[str, Any]:
    return {
        "backfilled": True,
        "backfill_version": BACKFILL_MARKER,
        "legacy_project_status": legacy_status,
        "legacy_active_revision_id": legacy_active_revision_id,
    }


def episode_metadata(*, legacy_project_id: str) -> Dict[str, Any]:
    return {
        "backfilled": True,
        "backfill_version": BACKFILL_MARKER,
        "legacy_project_id": legacy_project_id,
    }


def revision_metadata(*, legacy_status: str, legacy_sequence: int, hash_backfilled: bool) -> Dict[str, Any]:
    return {
        "backfilled": True,
        "backfill_version": BACKFILL_MARKER,
        "legacy_status": legacy_status,
        "legacy_sequence": legacy_sequence,
        "hash_backfilled": hash_backfilled,
    }


LEGACY_STATUS_TO_STUDIO = {
    "DRAFT": "DRAFT",
    "LOCKED": "LOCKED",
    "IN_REVIEW": "IN_REVIEW",
    "SUPERSEDED": "SUPERSEDED",
    "FAILED": "FAILED",
    "COMPLETED": "LOCKED",
}


def map_legacy_status(legacy_status: str) -> str:
    return LEGACY_STATUS_TO_STUDIO.get(legacy_status.upper(), "DRAFT")


def lock_state_for(status: str, mapped: str) -> str:
    """Legacy LOCKED revisions stay locked; everything else stays unlocked."""
    if status.upper() == "LOCKED":
        return "LOCKED"
    return "UNLOCKED"


__all__ = [
    "BACKFILL_MARKER",
    "SYNTHETIC_EPISODE_PREFIX",
    "SYNTHETIC_ACTOR",
    "synthetic_episode_id",
    "legacy_revision_content_hash",
    "is_valid_sha256",
    "normalize_legacy_hash",
    "series_metadata",
    "episode_metadata",
    "revision_metadata",
    "map_legacy_status",
    "lock_state_for",
]
