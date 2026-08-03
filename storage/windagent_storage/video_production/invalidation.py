"""
Artifact invalidation service (plan 05 §14.3, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

Invalidation NEVER deletes an artifact and NEVER rewrites history: it moves
records from VALID to STALE (or SUPERSEDED when a replacement is supplied)
and appends an audit entry for later garbage collection under a retention
policy (§14.3).

Scope rules (minimal affected set):

- SCREENPLAY_REVISION change invalidates the GENERATED_FROM chain downstream
  (cinematic plan -> shot plan -> prompt/request -> frames/references ->
  clips -> final cut);
- CHARACTER_REFERENCE change invalidates ONLY the shots bound to that
  character (CHARACTER_BINDING) and their downstream cuts — never other
  characters' shots;
- BGM change invalidates audio mix + final cut (AUDIO_INPUT + downstream)
  but NEVER visual clips.

Fail-closed:

- an unknown artifact/revision change target raises ValidationError (a
  silently-no-op invalidation would hide staleness);
- an invalidated record is never deleted; history is append-only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

from windagent_storage.video_production.graph import (
    ArtifactDependencyGraph,
    ArtifactDependencyType,
    build_bgm_scope,
    build_character_scope,
)
from windagent_storage.video_production.store import ArtifactRecordStore

INVALIDATION_SCHEMA_VERSION = "1.0.0"


class InvalidationChangeType:
    SCREENPLAY_REVISION = "SCREENPLAY_REVISION"
    CHARACTER_REFERENCE = "CHARACTER_REFERENCE"
    BGM = "BGM"
    PROMPT = "PROMPT"
    MODEL = "MODEL"
    PARAMETER = "PARAMETER"
    REVISION = "REVISION"


@dataclass(frozen=True)
class InvalidationChange:
    """A declared change that may make downstream artifacts stale (§14.3)."""

    change_type: str
    target_artifact_id: Optional[str] = None  # for artifact-bound changes
    domain_revision_hash: Optional[str] = None  # for revision-bound changes
    reason: str = ""

    def __post_init__(self) -> None:
        if self.change_type == InvalidationChangeType.REVISION:
            if not self.domain_revision_hash:
                raise ValidationError(
                    "REVISION change requires domain_revision_hash",
                    code="WINDAGENT_ERR_VALIDATION",
                )
        elif not self.target_artifact_id:
            raise ValidationError(
                f"Change type {self.change_type} requires target_artifact_id",
                code="WINDAGENT_ERR_VALIDATION",
            )


@dataclass
class InvalidationResult:
    """Outcome of one invalidation pass (affected scope + applied marks)."""

    change: InvalidationChange
    affected_artifact_ids: List[str] = field(default_factory=list)
    marked_stale: List[str] = field(default_factory=list)
    marked_superseded: List[str] = field(default_factory=list)
    audit: List[Dict[str, Any]] = field(default_factory=list)


class ArtifactInvalidationService:
    """Computes the minimal affected scope and applies non-destructive marks."""

    def __init__(
        self,
        *,
        graph: ArtifactDependencyGraph,
        record_store: ArtifactRecordStore,
        clock=None,
    ) -> None:
        self.graph = graph
        self.record_store = record_store
        self._clock = clock or time.time

    # -- scope computation (pure, deterministic) ---------------------------
    def affected_scope(self, change: InvalidationChange) -> List[str]:
        """Return the minimal set of artifact ids affected by `change` (§14.3).

        Fail-closed: an artifact-targeted change whose target is NOT a known
        graph node raises ValidationError — a silently-empty scope would hide
        staleness.
        """
        graph = self.graph
        ctype = change.change_type
        if ctype != InvalidationChangeType.REVISION:
            if not graph.has_node(change.target_artifact_id):
                raise ValidationError(
                    f"Cannot invalidate unknown artifact {change.target_artifact_id!r}",
                    code="WINDAGENT_ERR_VALIDATION",
                    details={"target": change.target_artifact_id, "change_type": ctype},
                )

        if ctype == InvalidationChangeType.SCREENPLAY_REVISION:
            # Full GENERATED_FROM chain downstream of the screenplay.
            return sorted(
                graph.transitive_inbound(change.target_artifact_id, {ArtifactDependencyType.GENERATED_FROM})
            )

        if ctype == InvalidationChangeType.CHARACTER_REFERENCE:
            # ONLY shots bound to this character + their downstream cuts.
            bound_shots, downstream = build_character_scope(graph, change.target_artifact_id)
            return sorted(set(bound_shots) | set(downstream))

        if ctype == InvalidationChangeType.BGM:
            # Audio mix + final cut ONLY — visual clips survive.
            return build_bgm_scope(graph, change.target_artifact_id)

        if ctype == InvalidationChangeType.PROMPT:
            # Prompt changes invalidate the request/frames/clips downstream.
            return sorted(
                graph.transitive_inbound(change.target_artifact_id, {ArtifactDependencyType.GENERATED_FROM})
            )

        if ctype == InvalidationChangeType.MODEL or ctype == InvalidationChangeType.PARAMETER:
            return sorted(
                graph.transitive_inbound(change.target_artifact_id, {ArtifactDependencyType.GENERATED_FROM})
            )

        if ctype == InvalidationChangeType.REVISION:
            # Revision-hash change: every artifact that depends on that hash.
            affected: List[str] = []
            for edge in graph.edges():
                if (
                    edge.domain_revision_hash == change.domain_revision_hash
                    and edge.dependency_type == ArtifactDependencyType.REVISION
                ):
                    if edge.artifact_id not in affected:
                        affected.append(edge.artifact_id)
            return sorted(affected)

        raise ValidationError(
            f"Unknown invalidation change type {ctype!r}",
            code="WINDAGENT_ERR_VALIDATION",
        )

    # -- apply (non-destructive) -------------------------------------------
    def invalidate(
        self,
        change: InvalidationChange,
        *,
        actor: str = "system",
        supersede_with: Optional[Dict[str, str]] = None,
    ) -> InvalidationResult:
        """Mark the affected scope STALE (or SUPERSEDED where a replacement is
        supplied). Records are never deleted; history is append-only."""
        affected = self.affected_scope(change)
        result = InvalidationResult(change=change, affected_artifact_ids=affected)
        supersede_with = supersede_with or {}

        for artifact_id in affected:
            record = self.record_store.load(artifact_id)
            if record is None:
                raise ValidationError(
                    f"Cannot invalidate unknown artifact {artifact_id!r}",
                    code="WINDAGENT_ERR_VALIDATION",
                    details={"artifact_id": artifact_id},
                )
            replacement = supersede_with.get(artifact_id)
            if replacement:
                record.mark_superseded(
                    superseded_by=replacement,
                    reason=change.reason or f"{change.change_type} change",
                    actor=actor,
                    at=self._clock(),
                )
                result.marked_superseded.append(artifact_id)
            else:
                record.mark_stale(
                    reason=change.reason or f"{change.change_type} change",
                    actor=actor,
                    at=self._clock(),
                )
                result.marked_stale.append(artifact_id)
            self.record_store.save(record)
            result.audit.append(
                {
                    "artifact_id": artifact_id,
                    "change_type": change.change_type,
                    "status": record.status.value,
                    "superseded_by": record.superseded_by,
                    "at": self._clock(),
                    "actor": actor,
                }
            )
        return result

    # -- helpers -----------------------------------------------------------
    def summary(self, result: InvalidationResult) -> Dict[str, Any]:
        return {
            "change_type": result.change.change_type,
            "target": result.change.target_artifact_id or result.change.domain_revision_hash,
            "affected_count": len(result.affected_artifact_ids),
            "marked_stale": result.marked_stale,
            "marked_superseded": result.marked_superseded,
        }


__all__ = [
    "INVALIDATION_SCHEMA_VERSION",
    "InvalidationChangeType",
    "InvalidationChange",
    "InvalidationResult",
    "ArtifactInvalidationService",
]
