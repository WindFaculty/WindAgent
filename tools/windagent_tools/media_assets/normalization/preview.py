"""
Preview render (VP3D Phase 7, Stage C item 6).

Turntable/thumbnail preview uses the DETERMINISTIC Blender profile of Stage B
(Cycles, locked samples, CPU fallback, Standard color management). The actual
render is engine work (``AssetJobRunner``); CI uses deterministic fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from windagent_core.domain.video_production.asset_normalization.errors import (
    PreviewRenderError,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    NormalizationRequest,
    PreviewRenderResult,
)

from windagent_tools.media_assets.normalization.job_runner import (
    AssetJobRunner,
    JobInvocation,
)
from windagent_tools.media_assets.normalization.snapshot import MeshSnapshot


class PreviewRunner:
    """Runs the deterministic preview render through the engine job runner."""

    def __init__(self, *, job_runner: Optional[AssetJobRunner] = None) -> None:
        self._job_runner = job_runner

    async def render(
        self,
        snapshot: MeshSnapshot,
        request: NormalizationRequest,
        *,
        workspace: str,
    ) -> PreviewRenderResult:
        if self._job_runner is None:
            raise PreviewRenderError(
                "preview render requires an engine job runner (fail closed)"
            )
        profile = request.config.preview
        invocation = JobInvocation(
            kind="RENDER_PREVIEW",
            job_id=f"preview_{request.asset.content_hash[:8]}",
            input_files=[request.source_uri] if request.source_uri else [],
            output_dir=workspace,
            workspace=workspace,
            config={
                "content_hash": request.asset.content_hash,
                "format": request.format.value,
                "engine": profile.engine,
                "device": profile.device,
                "samples": profile.samples,
                "color_management": profile.color_management,
                "denoise": profile.denoise,
            },
        )
        result = await self._job_runner.render_preview(invocation, profile)
        if not result.ok:
            raise PreviewRenderError(
                f"preview render failed: {result.error}",
                details={"job_id": result.job_id},
            )
        return PreviewRenderResult(
            ok=True,
            thumbnail_file=str(result.report.get("thumbnail_file", "")),
            turntable_files=list(result.report.get("turntable_files", [])),
            frames_rendered=int(result.report.get("frames_rendered", profile.frames)),
            engine=profile.engine,
            device=profile.device,
            profile=profile,
            content_hash=str(result.report.get("content_hash", "")),
            local_files=[p for p in result.generated_files if Path(p).is_file()],
            generated_by=str(result.report.get("generated_by", "blender_job")),
        )


__all__ = ["PreviewRunner"]
