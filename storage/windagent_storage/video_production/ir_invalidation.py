"""
IR track-scoped invalidation — the REAL storage caller of the canonical
`invalidate_scope` / `affected_outputs` domain rules (VP3D Stage A Phase 2).

Stage A §2 requires the track-scoped invalidation mapping (dialogue change ->
audio/facial/final-cut only; camera change -> scene compile + render) to be
USED by an orchestration/storage caller, not merely to exist as a domain
mapping + unit test.

This service is that caller: when an IR revision changes one component, it

1. calls the canonical `invalidate_scope(component_kind)` +
   `affected_outputs(component_kind)` (fail-closed on unknown kinds), and
2. applies non-destructive STALE marks + audit entries to the storage
   `ArtifactRecord`s for exactly those derived artifacts (never deletes,
   never rewrites history).

The artifact-id mapping is injected so the caller stays storage-neutral:
`artifact_id_for(scene_id, DerivedArtifactKind) -> storage artifact id`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    IrComponentKind,
)
from windagent_core.domain.video_production.production_ir.invalidation import (
    affected_outputs,
    invalidate_scope,
)

from windagent_storage.video_production.store import ArtifactRecordStore

IR_INVALIDATION_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class IrInvalidationResult:
    """Outcome of invalidating one IR component change."""

    component_kind: IrComponentKind
    scope: str
    affected_artifact_kinds: List[str] = field(default_factory=list)
    affected_artifact_ids: List[str] = field(default_factory=list)
    marked_stale: List[str] = field(default_factory=list)
    audit: List[Dict[str, Any]] = field(default_factory=list)


class IrTrackInvalidationService:
    """Storage caller for track-scoped IR invalidation (engine-neutral)."""

    def __init__(
        self,
        *,
        record_store: ArtifactRecordStore,
        artifact_id_for: Optional[Callable[[str, DerivedArtifactKind], str]] = None,
    ) -> None:
        self._record_store = record_store
        # The default artifact-id mapping must be filesystem-safe (no ':' etc.).
        self._artifact_id_for = artifact_id_for or (
            lambda scene_id, kind: f"{scene_id}__{kind.value}"
        )

    # -- scope computation (uses the canonical domain rules) ---------------
    def affected_artifact_ids(
        self, component_kind: IrComponentKind, scene_id: str
    ) -> tuple[str, List[DerivedArtifactKind], List[str]]:
        """Return (scope, affected kinds, affected storage artifact ids).

        Delegates to the canonical `invalidate_scope` / `affected_outputs`
        mapping — a DIALOGUE change can never invalidate baked scene geometry
        and an unknown component kind fails closed.
        """
        scope = invalidate_scope(component_kind)
        kinds = sorted(affected_outputs(component_kind), key=str)
        artifact_ids = [self._artifact_id_for(scene_id, kind) for kind in kinds]
        return scope.value, kinds, artifact_ids

    # -- apply (non-destructive) -------------------------------------------
    def invalidate_component(
        self,
        component_kind: IrComponentKind,
        scene_id: str,
        *,
        reason: str = "",
        actor: str = "system",
        clock: Optional[Callable[[], float]] = None,
    ) -> IrInvalidationResult:
        """Mark exactly the dependent derived artifacts STALE (never deletes)."""
        now = clock or time.time
        scope_value, kinds, artifact_ids = self.affected_artifact_ids(
            component_kind, scene_id
        )
        result = IrInvalidationResult(
            component_kind=component_kind,
            scope=scope_value,
            affected_artifact_kinds=[k.value for k in kinds],
            affected_artifact_ids=artifact_ids,
        )
        for artifact_id in artifact_ids:
            record = self._record_store.load(artifact_id)
            if record is None:
                # Fail closed: a silently-missing record would hide staleness.
                raise ValueError(
                    f"Cannot invalidate unknown IR-derived artifact {artifact_id!r} "
                    f"for scene {scene_id} ({component_kind.value} change)."
                )
            record.mark_stale(
                reason=reason or f"IR {component_kind.value} change in scene {scene_id}",
                actor=actor,
                at=now(),
            )
            self._record_store.save(record)
            result.marked_stale.append(artifact_id)
            result.audit.append(
                {
                    "artifact_id": artifact_id,
                    "component_kind": component_kind.value,
                    "scope": scope_value,
                    "status": record.status.value,
                    "actor": actor,
                    "at": now(),
                }
            )
        return result


__all__ = [
    "IR_INVALIDATION_SCHEMA_VERSION",
    "IrInvalidationResult",
    "IrTrackInvalidationService",
]
