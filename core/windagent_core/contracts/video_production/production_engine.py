"""
ProductionEnginePort — canonical engine adapter contract (VP3D Phase 1).

The port consumes TYPED IR units (scene descriptions, shot execution intents,
render intents) and artifact references. It NEVER accepts a Flow prompt, a
`GenerationMode`, or any engine SDK object (`bpy`, Unreal API). The engine
adapter (Blender, Unreal, ...) compiles the IR onto its own execution path and
publishes derived artifacts (`.blend`, frames, clips, audio, final cut).

Design rules:

- inputs are immutable IR models / IDs — no provider-specific payloads;
- every method returns a typed receipt/artifact that records the IR content
  hash it was derived from, so storage can invalidate precisely;
- cancellation and idempotency are first-class (same job id re-inspect is
  safe); retry classification follows the platform error taxonomy.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from windagent_core.domain.video_production.ids import EngineJobId
from windagent_core.domain.video_production.production_ir.enums import DerivedArtifactKind
from windagent_core.domain.video_production.production_ir.models import (
    DerivedArtifact,
    EngineJobReceipt,
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)


@runtime_checkable
class ProductionEnginePort(Protocol):
    """Port for an engine-neutral 3D production engine (Blender, Unreal, ...)."""

    async def submit_scene(self, scene: SceneDescription, render: RenderIntent) -> EngineJobReceipt:
        """Submit a full scene for compile/render; returns a job receipt."""
        ...

    async def submit_shot(self, intent: ShotExecutionIntent, render: RenderIntent) -> EngineJobReceipt:
        """Submit a single shot execution intent; returns a job receipt."""
        ...

    async def inspect_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        """Inspect the current status of a submitted engine job."""
        ...

    async def cancel_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        """Request cancellation of a submitted engine job."""
        ...

    async def download_artifact(
        self,
        job_id: EngineJobId,
        artifact_kind: DerivedArtifactKind,
    ) -> DerivedArtifact:
        """Download a derived artifact published by the engine job."""
        ...


__all__ = ["ProductionEnginePort"]
