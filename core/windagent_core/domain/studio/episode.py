"""
Canonical creative ``Episode`` aggregate (studio.contract/v0.1).

Distinct from VP3D ``EpisodeRunId``/``EpisodeSceneId``/``EpisodeFixture``. The
aggregate holds lifecycle state, the current revision link, authoring metadata,
and an optimistic version used for stale-write protection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.studio.ids import EpisodeId, ProductionRevisionId, SeriesProjectId, StudioRunId
from windagent_core.contracts.studio.errors import (
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.domain.studio.lifecycle import (
    EpisodeState,
    EpisodeStateMachine,
    LOCKED_STATES,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Episode(BaseModel):
    """Creative Studio episode aggregate."""

    model_config = ConfigDict(frozen=True, extra="allow")

    episode_id: EpisodeId
    series_id: SeriesProjectId
    title: str = Field(min_length=1)
    episode_number: int = Field(default=1, ge=1)
    state: EpisodeState = EpisodeState.DRAFT
    current_revision_id: Optional[ProductionRevisionId] = None
    active_run_id: Optional[StudioRunId] = None
    awaiting_checkpoint: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Episode title cannot be blank.")
        return v.strip()

    def _check_stale(self, expected_version: Optional[int]) -> None:
        if expected_version is not None and expected_version != self.optimistic_version:
            raise StudioStaleRevisionError(
                "Optimistic version mismatch; episode changed since it was read.",
                details={
                    "episode_id": str(self.episode_id),
                    "expected_version": expected_version,
                    "current_version": self.optimistic_version,
                },
            )

    def _bump(self, **changes: Any) -> Episode:
        return self.model_copy(
            update={
                **changes,
                "optimistic_version": self.optimistic_version + 1,
                "updated_at": utc_now(),
            }
        )

    @property
    def is_terminal(self) -> bool:
        return EpisodeStateMachine.is_terminal(self.state)

    @property
    def is_locked(self) -> bool:
        return self.state in LOCKED_STATES

    def transition_to(self, target: EpisodeState, *, expected_version: Optional[int] = None) -> Episode:
        """Validate and apply a lifecycle transition with stale-write protection."""
        self._check_stale(expected_version)
        EpisodeStateMachine.transition(self.state, target)
        awaiting = EpisodeStateMachine.awaiting_checkpoint(target)
        return self._bump(
            state=target,
            awaiting_checkpoint=awaiting.value if awaiting is not None else None,
        )

    def attach_revision(
        self,
        revision_id: ProductionRevisionId,
        *,
        expected_version: Optional[int] = None,
    ) -> Episode:
        self._check_stale(expected_version)
        if self.is_locked:
            raise StudioStaleRevisionError(
                "Cannot attach a revision to a locked episode; derive a new revision instead.",
                details={"episode_id": str(self.episode_id), "state": self.state.value},
            )
        return self._bump(current_revision_id=revision_id)

    def edit(
        self,
        *,
        title: Optional[str] = None,
        metadata_patch: Optional[Dict[str, Any]] = None,
        expected_version: Optional[int] = None,
    ) -> "Episode":
        """Presentation-only edit (P0.4): title + metadata merge.

        Returns ``self`` unchanged when the patch is a no-op. Stale-write
        protection via ``expected_version``. Generation semantics (which keys
        are immutable once the episode leaves DRAFT) are enforced by the
        application authority, not here.
        """
        self._check_stale(expected_version)
        changes: Dict[str, Any] = {}
        if title is not None and title.strip() != self.title:
            changes["title"] = title.strip()
        if metadata_patch:
            merged = dict(self.metadata)
            merged.update(metadata_patch)
            if merged != self.metadata:
                changes["metadata"] = merged
        if not changes:
            return self
        return self._bump(**changes)

    def bind_run(self, run_id: StudioRunId, *, expected_version: Optional[int] = None) -> Episode:
        self._check_stale(expected_version)
        return self._bump(active_run_id=run_id)

    def start_lock_sequence(self, *, expected_version: Optional[int] = None) -> Episode:
        """Idempotently resumable first step: SCREENPLAY_REVIEW -> LOCKED."""
        self._check_stale(expected_version)
        if self.state == EpisodeState.LOCKED:
            return self
        EpisodeStateMachine.transition(self.state, EpisodeState.LOCKED)
        return self._bump(state=EpisodeState.LOCKED)

    def finalize_lock(self, *, expected_version: Optional[int] = None) -> Episode:
        """Idempotently resumable second step: LOCKED -> READY_FOR_PRODUCTION."""
        self._check_stale(expected_version)
        if self.state == EpisodeState.READY_FOR_PRODUCTION:
            return self
        EpisodeStateMachine.transition(self.state, EpisodeState.READY_FOR_PRODUCTION)
        return self._bump(state=EpisodeState.READY_FOR_PRODUCTION)


__all__ = ["utc_now", "Episode"]
