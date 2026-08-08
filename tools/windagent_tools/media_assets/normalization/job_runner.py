"""
AssetJobRunner — engine job port for asset normalization (VP3D Phase 7).

Everything that needs an external 3D engine (Blender) goes through this port:

- ``import_validate``  — sandboxed import of FBX/USD/BLEND, structural report;
- ``generate_lod``     — decimation of a mesh into derived LOD files;
- ``render_preview``   — deterministic turntable/thumbnail preview render.

The host-side pipeline (media_assets) NEVER spawns a process itself: the real
implementation lives in the Blender adapter (``BlenderAssetJobRunner``) and
CI runs deterministic fakes. When no runner is available the pipeline fails
closed for formats that require engine-side work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Protocol

from windagent_core.domain.video_production.asset_normalization.models import (
    PreviewProfile,
)


@dataclass(frozen=True)
class JobInvocation:
    """Typed description of ONE engine job."""

    kind: str  # IMPORT_VALIDATE | GENERATE_LOD | RENDER_PREVIEW
    job_id: str
    input_files: List[str] = field(default_factory=list)
    output_dir: str = ""
    workspace: str = ""
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobResult:
    """Typed outcome of one engine job."""

    job_id: str
    kind: str
    ok: bool
    report: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    generated_files: List[str] = field(default_factory=list)


class AssetJobRunner(Protocol):
    """Engine job runner implemented by the Blender adapter (or fakes)."""

    @property
    def available(self) -> bool:
        """Whether a real engine is present and policy-satisfying."""
        ...

    async def import_validate(self, invocation: JobInvocation) -> JobResult:
        """Sandboxed import + structural validation (FBX/USD/BLEND)."""
        ...

    async def generate_lod(self, invocation: JobInvocation) -> JobResult:
        """Decimate mesh into derived LOD files (never overwrites source)."""
        ...

    async def render_preview(
        self,
        invocation: JobInvocation,
        profile: PreviewProfile,
    ) -> JobResult:
        """Render the deterministic turntable/thumbnail preview."""
        ...


def resolve_existing(paths: List[str]) -> List[Path]:
    return [Path(p) for p in paths if Path(p).is_file()]


__all__ = ["AssetJobRunner", "JobInvocation", "JobResult", "resolve_existing"]
