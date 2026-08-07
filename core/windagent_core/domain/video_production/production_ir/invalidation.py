"""
VP3D Phase 1 — Track-scoped invalidation for the Production IR.

A change to ONE IR component must invalidate exactly the dependent scenes /
shots / outputs (plan §4 backlog item 7). The mapping below is the canonical
domain rule set; storage / orchestration adapters call it when an IR revision
changes so caches and scheduler state are invalidated precisely:

- DIALOGUE change            -> audio mix, facial render and final cut
                               (never the baked scene/geometry);
- CAMERA / LIGHTING / SCENE_STRUCTURE / ASSET_REFERENCE / DURATION change
                             -> recompile the scene and re-render the
                               dependent shots;
- ANIMATION / SIMULATION     -> re-render dependent shots;
- RENDER_PROFILE             -> re-render only (no scene recompile);
- FACIAL                     -> facial render + audio/final cut.

Unknown component kinds FAIL CLOSED: callers must not silently treat an
unrecognized change as a no-op.
"""

from __future__ import annotations

from typing import Dict, Set

from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    IrComponentKind,
    IrInvalidationScope,
)
from windagent_core.domain.video_production.errors import VideoProductionProtocolError

# Component -> invalidation scope (plan §4 backlog item 7 test expectations).
IR_COMPONENT_INVALIDATION: Dict[IrComponentKind, IrInvalidationScope] = {
    IrComponentKind.DIALOGUE: IrInvalidationScope.AUDIO_AND_FACIAL_AND_CUT,
    IrComponentKind.FACIAL: IrInvalidationScope.AUDIO_AND_FACIAL_AND_CUT,
    IrComponentKind.CAMERA: IrInvalidationScope.SCENE_COMPILE_AND_RENDER,
    IrComponentKind.LIGHTING: IrInvalidationScope.SCENE_COMPILE_AND_RENDER,
    IrComponentKind.SCENE_STRUCTURE: IrInvalidationScope.SCENE_COMPILE_AND_RENDER,
    IrComponentKind.ASSET_REFERENCE: IrInvalidationScope.SCENE_COMPILE_AND_RENDER,
    IrComponentKind.DURATION: IrInvalidationScope.SCENE_COMPILE_AND_RENDER,
    IrComponentKind.ANIMATION: IrInvalidationScope.DEPENDENT_RENDER,
    IrComponentKind.SIMULATION: IrInvalidationScope.DEPENDENT_RENDER,
    IrComponentKind.RENDER_PROFILE: IrInvalidationScope.RENDER_ONLY,
}

# Scope -> derived artifact kinds that become stale.
_SCOPE_AFFECTED_OUTPUTS: Dict[IrInvalidationScope, Set[DerivedArtifactKind]] = {
    IrInvalidationScope.NONE: set(),
    IrInvalidationScope.AUDIO_AND_FACIAL_AND_CUT: {
        DerivedArtifactKind.MIXED_AUDIO,
        DerivedArtifactKind.FACIAL_RENDER,
        DerivedArtifactKind.FINAL_CUT,
    },
    IrInvalidationScope.SCENE_COMPILE_AND_RENDER: {
        DerivedArtifactKind.SCENE_BLEND,
        DerivedArtifactKind.FRAME_SEQUENCE,
        DerivedArtifactKind.RENDERED_CLIP,
        DerivedArtifactKind.FINAL_CUT,
    },
    IrInvalidationScope.RENDER_ONLY: {
        DerivedArtifactKind.FRAME_SEQUENCE,
        DerivedArtifactKind.RENDERED_CLIP,
        DerivedArtifactKind.FINAL_CUT,
    },
    IrInvalidationScope.DEPENDENT_RENDER: {
        DerivedArtifactKind.FRAME_SEQUENCE,
        DerivedArtifactKind.RENDERED_CLIP,
    },
}


def invalidate_scope(component_kind: IrComponentKind) -> IrInvalidationScope:
    """Return the invalidation scope for a changed IR component.

    Fails closed on unknown component kinds: an unrecognized track change
    must never silently invalidate nothing.
    """
    try:
        return IR_COMPONENT_INVALIDATION[component_kind]
    except KeyError as exc:
        raise VideoProductionProtocolError(
            f"Unknown IR component kind {component_kind!r}; invalidation cannot be computed.",
            details={"component_kind": str(component_kind)},
        ) from exc


def affected_outputs(component_kind: IrComponentKind) -> Set[DerivedArtifactKind]:
    """Return the derived artifact kinds invalidated by a component change."""
    scope = invalidate_scope(component_kind)
    return set(_SCOPE_AFFECTED_OUTPUTS.get(scope, set()))


__all__ = [
    "IR_COMPONENT_INVALIDATION",
    "invalidate_scope",
    "affected_outputs",
]
