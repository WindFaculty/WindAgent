"""Code Video domain (Phase 16).

Deterministic tutorial workspace + checkpoint model extracted from
``tools/code_video/workspace`` and ``workflows/code_video``.  The 9-step
pipeline (COMPILE_PLAN .. FINAL_QC) and checkpoint tracking are the
canonical production-owned semantics; the rendering/capture adapters are
treated as external capability adapters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..errors import ProductionValidationError

CODE_VIDEO_STEPS: tuple[str, ...] = (
    "COMPILE_PLAN",
    "BUILD_WORKSPACE",
    "VERIFY_TUTORIAL",
    "RENDER_STUDIO",
    "RUN_REPLAY",
    "CAPTURE_TAKES",
    "RENDER_GRAPHICS",
    "ASSEMBLE_MASTER",
    "FINAL_QC",
)


class CodeVideoStatus(StrEnum):
    DRAFT = "DRAFT"
    BUILDING = "BUILDING"
    VERIFIED = "VERIFIED"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CheckpointStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CodeVideoProject(BaseModel):
    """Tutorial workspace aggregate."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    status: CodeVideoStatus = CodeVideoStatus.DRAFT
    repo_url: str = ""
    branch: str = "main"
    tutorial_steps: tuple[str, ...] = Field(default_factory=lambda: CODE_VIDEO_STEPS)
    current_checkpoint: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def transition_to(self, target: CodeVideoStatus, *, expected_version: int | None = None) -> CodeVideoProject:
        if expected_version is not None and expected_version != self.optimistic_version:
            from ..errors import ProductionStaleRevisionError

            raise ProductionStaleRevisionError(
                "CodeVideo version mismatch.",
                context={
                    "project_id": self.project_id,
                    "expected_version": expected_version,
                    "current_version": self.optimistic_version,
                },
            )
        allowed: dict[CodeVideoStatus, frozenset[CodeVideoStatus]] = {
            CodeVideoStatus.DRAFT: frozenset({CodeVideoStatus.BUILDING, CodeVideoStatus.FAILED, CodeVideoStatus.CANCELLED}),
            CodeVideoStatus.BUILDING: frozenset({CodeVideoStatus.VERIFIED, CodeVideoStatus.FAILED, CodeVideoStatus.CANCELLED}),
            CodeVideoStatus.VERIFIED: frozenset({CodeVideoStatus.RENDERING, CodeVideoStatus.FAILED, CodeVideoStatus.CANCELLED}),
            CodeVideoStatus.RENDERING: frozenset({CodeVideoStatus.COMPLETED, CodeVideoStatus.FAILED, CodeVideoStatus.CANCELLED}),
            CodeVideoStatus.COMPLETED: frozenset(),
            CodeVideoStatus.FAILED: frozenset({CodeVideoStatus.DRAFT}),
            CodeVideoStatus.CANCELLED: frozenset({CodeVideoStatus.DRAFT}),
        }
        if target not in allowed[self.status]:
            raise ProductionValidationError(
                f"Illegal code_video transition {self.status.value} -> {target.value}.",
                context={"project_id": self.project_id},
            )
        return self.model_copy(update={"status": target, "updated_at": datetime.now(UTC), "optimistic_version": self.optimistic_version + 1})


class TutorialCheckpoint(BaseModel):
    """One checkpoint/take receipt."""

    model_config = ConfigDict(frozen=True, extra="allow")

    checkpoint_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    status: CheckpointStatus = CheckpointStatus.PENDING
    attempt: int = Field(default=1, ge=1)
    input_hash: str = ""
    output_hash: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["CODE_VIDEO_STEPS", "CheckpointStatus", "CodeVideoProject", "CodeVideoStatus", "TutorialCheckpoint"]
