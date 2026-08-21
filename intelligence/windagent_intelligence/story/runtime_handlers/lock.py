"""Plan B B8 runtime task handler: ``studio.story.lock`` (S10).

Thin application service over the pure lock assembly pipeline, exactly as
``story_task_io.json`` declares (ScreenplayDraft + ReviewReport ->
LockedScreenplayReceipt + LockedScreenplayPackage). Validates the A-issued
receipt authority, review threshold, iteration status, and complete lineage,
then assembles the immutable package from A refs — never copied mutable
state. Never touches persistence, task execution infrastructure, or provider
internals; the A atomic lock transition (``READY_FOR_PRODUCTION``) is an A
checkpoint command issued outside this handler, and the A-issued receipt is
accepted as authority.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.review import (
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewReport,
)
from windagent_core.domain.story.screenplay import ScreenplayDraft
from windagent_intelligence.story.review.service import (
    LockResult,
    LockService,
)

__all__ = ["LockHandler", "LOCK_HANDLER_REGISTRY"]


class LockHandler:
    """Handler for ``studio.story.lock`` (Draft + Report -> Receipt + Package)."""

    task_type = StudioTaskType.LOCK

    def __init__(self) -> None:
        self.service = LockService()

    async def handle(
        self,
        draft: ScreenplayDraft,
        report: ReviewReport,
        receipt: LockedScreenplayReceipt,
        *,
        lineage_refs: List[PackageArtifactRef],
        title: Optional[str] = None,
    ) -> LockResult:
        return self.service.assemble(
            draft=draft,
            report=report,
            receipt=receipt,
            lineage_refs=lineage_refs,
            title=title,
        )


#: B8 handler surface: task type -> handler class (B9 instantiates per task).
LOCK_HANDLER_REGISTRY: Dict[StudioTaskType, Any] = {
    StudioTaskType.LOCK: LockHandler,
}
