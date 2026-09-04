"""Rendering domain (Phase 16).

Extracted from ``tools/production_engines/blender``: render jobs are
content-addressed, frame-chunked, idempotent, and restartable at chunk
granularity.  The engine validates determinism (same inputs -> same output)
and requires an explicit colorspace declaration before assembly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..errors import ProductionValidationError


class RenderStatus(StrEnum):
    QUEUED = "QUEUED"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FrameSequenceSpec(BaseModel):
    """Declared input of one rendered frame sequence."""

    model_config = ConfigDict(frozen=True, extra="allow")

    sequence_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    frame_start: int = Field(ge=1)
    frame_end: int = Field(ge=1)
    fps: float = Field(default=24.0, gt=0)
    extension: str = Field(default="png")
    colorspace: str = Field(min_length=1, description="REQUIRED: e.g. sRGB, linear, ACEScg")
    frame_dir: str = ""

    @property
    def expected_frame_count(self) -> int:
        return max(0, self.frame_end - self.frame_start + 1)

    def check_valid(self) -> None:
        if not self.colorspace.strip():
            raise ProductionValidationError("Frame sequence colorspace is required.", context={"sequence_id": self.sequence_id})
        if self.frame_end < self.frame_start:
            raise ProductionValidationError("Frame range is inverted.", context={"sequence_id": self.sequence_id})


class RenderJob(BaseModel):
    """Render execution aggregate (one scene/shot chunk collection)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    job_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    revision_id: str | None = None
    scene_id: str = ""
    shot_id: str = ""
    status: RenderStatus = RenderStatus.QUEUED
    frame_start: int = Field(default=1, ge=1)
    frame_end: int = Field(default=24, ge=1)
    colorspace: str = Field(default="sRGB", min_length=1)
    profile_id: str = Field(default="main_1080p_h264")
    attempt: int = Field(default=1, ge=1)
    input_hash: str = ""
    output_hash: str = ""
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def transition_to(self, target: RenderStatus, *, expected_version: int | None = None) -> RenderJob:
        if expected_version is not None and expected_version != self.optimistic_version:
            from ..errors import ProductionStaleRevisionError

            raise ProductionStaleRevisionError(
                "Render job version mismatch.",
                context={"job_id": self.job_id, "expected_version": expected_version, "current_version": self.optimistic_version},
            )
        allowed: dict[RenderStatus, frozenset[RenderStatus]] = {
            RenderStatus.QUEUED: frozenset({RenderStatus.RENDERING, RenderStatus.CANCELLED}),
            RenderStatus.RENDERING: frozenset({RenderStatus.COMPLETED, RenderStatus.FAILED, RenderStatus.CANCELLED}),
            RenderStatus.COMPLETED: frozenset(),
            RenderStatus.FAILED: frozenset({RenderStatus.QUEUED}),
            RenderStatus.CANCELLED: frozenset({RenderStatus.QUEUED}),
        }
        if target not in allowed[self.status]:
            raise ProductionValidationError(
                f"Illegal render transition {self.status.value} -> {target.value}.",
                context={"job_id": self.job_id},
            )
        return self.model_copy(update={"status": target, "updated_at": datetime.now(UTC), "optimistic_version": self.optimistic_version + 1})


__all__ = ["FrameSequenceSpec", "RenderJob", "RenderStatus"]
