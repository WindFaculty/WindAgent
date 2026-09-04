"""Render Service coordinating EDL compilation, rendering, and technical validation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .compiler import EdlCompiler
from .contracts import (
    MediaRendererPort,
    MediaValidationError,
    MediaValidationResult,
    RenderEncodingSpec,
    RenderExecutionError,
    RenderJobState,
    RenderPlan,
    RenderValidationError,
)
from .ffmpeg_adapter import FFmpegRendererAdapter

logger = logging.getLogger("windagent.production.render.service")


class RenderService:
    """Coordinates lifecycle of a production render execution."""

    def __init__(
        self,
        renderer: MediaRendererPort | None = None,
        compiler: EdlCompiler | None = None,
    ) -> None:
        self._renderer = renderer or FFmpegRendererAdapter()
        self._compiler = compiler or EdlCompiler()

    async def execute_render_job(
        self,
        *,
        job_id: str,
        edl_data: dict[str, Any],
        output_path: Path,
        asset_resolver: dict[str, Path] | None = None,
        encoding: RenderEncodingSpec | None = None,
    ) -> tuple[RenderJobState, MediaValidationResult | None, str | None]:
        """Execute complete rendering lifecycle from EDL to validated media file."""
        state = RenderJobState.QUEUED
        logger.info("Render job %s state -> %s", job_id, state)

        # Stage 1: Validation & Compilation
        try:
            plan = self._compiler.compile(
                job_id=job_id,
                edl_data=edl_data,
                output_path=output_path,
                asset_resolver=asset_resolver,
                encoding=encoding,
            )
        except RenderValidationError as err:
            logger.error("Render compilation failed for job %s: %s", job_id, err)
            return RenderJobState.RENDER_FAILED, None, str(err)

        # Stage 2: Rendering
        state = RenderJobState.RENDERING
        logger.info("Render job %s state -> %s", job_id, state)
        try:
            validation_result = await self._renderer.render(plan)
        except RenderExecutionError as err:
            logger.error("Render execution failed for job %s: %s", job_id, err)
            return RenderJobState.RENDER_FAILED, None, str(err)
        except MediaValidationError as err:
            logger.error("Render validation failed for job %s: %s", job_id, err)
            return RenderJobState.VALIDATION_FAILED, None, str(err)

        # Stage 3: Validation succeeded
        state = RenderJobState.READY
        logger.info("Render job %s state -> %s (Valid MP4 produced: %s bytes)", job_id, state, validation_result.file_size_bytes)
        return state, validation_result, None
