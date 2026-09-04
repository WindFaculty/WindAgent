"""Creative Studio ``Episode`` aggregate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..errors import StudioStaleRevisionError, StudioValidationError
from ..lifecycle import LOCKED_STATES, EpisodeState, EpisodeStateMachine


def utc_now() -> datetime:
    return datetime.now(UTC)


class Episode(BaseModel):
    """Creative Studio episode aggregate."""

    model_config = ConfigDict(frozen=True, extra="allow")

    episode_id: str = Field(min_length=1)
    series_id: str = Field(min_length=1)
    project_id: str | None = Field(default=None)
    title: str = Field(min_length=1)
    episode_number: int = Field(default=1, ge=1)
    logline: str = Field(default="")
    state: EpisodeState = EpisodeState.DRAFT
    current_revision_id: str | None = None
    active_run_id: str | None = None
    awaiting_checkpoint: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    optimistic_version: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise StudioValidationError("Episode title cannot be blank.")
        return v.strip()

    def _check_stale(self, expected_version: int | None) -> None:
        if expected_version is not None and expected_version != self.optimistic_version:
            raise StudioStaleRevisionError(
                "Optimistic version mismatch; episode changed since it was read.",
                context={
                    "episode_id": self.episode_id,
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

    def transition_to(self, target: EpisodeState, *, expected_version: int | None = None) -> Episode:
        self._check_stale(expected_version)
        EpisodeStateMachine.transition(self.state, target)
        awaiting = EpisodeStateMachine.awaiting_checkpoint(target)
        return self._bump(
            state=target,
            awaiting_checkpoint=awaiting.value if awaiting is not None else None,
        )

    def attach_revision(
        self, revision_id: str, *, expected_version: int | None = None
    ) -> Episode:
        self._check_stale(expected_version)
        if self.is_locked:
            raise StudioStaleRevisionError(
                "Cannot attach a revision to a locked episode; derive a new revision instead.",
                context={"episode_id": self.episode_id, "state": self.state.value},
            )
        return self._bump(current_revision_id=revision_id)

    def edit(
        self,
        *,
        title: str | None = None,
        logline: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> Episode:
        self._check_stale(expected_version)
        changes: dict[str, Any] = {}
        if title is not None and title.strip() != self.title:
            changes["title"] = title.strip()
        if logline is not None and logline != self.logline:
            changes["logline"] = logline
        if metadata_patch:
            merged = dict(self.metadata)
            merged.update(metadata_patch)
            if merged != self.metadata:
                changes["metadata"] = merged
        if not changes:
            return self
        return self._bump(**changes)

    def bind_run(self, run_id: str, *, expected_version: int | None = None) -> Episode:
        self._check_stale(expected_version)
        return self._bump(active_run_id=run_id)

    def start_lock_sequence(self, *, expected_version: int | None = None) -> Episode:
        self._check_stale(expected_version)
        if self.state == EpisodeState.LOCKED:
            return self
        EpisodeStateMachine.transition(self.state, EpisodeState.LOCKED)
        return self._bump(state=EpisodeState.LOCKED)

    def finalize_lock(self, *, expected_version: int | None = None) -> Episode:
        self._check_stale(expected_version)
        if self.state == EpisodeState.READY_FOR_PRODUCTION:
            return self
        EpisodeStateMachine.transition(self.state, EpisodeState.READY_FOR_PRODUCTION)
        return self._bump(state=EpisodeState.READY_FOR_PRODUCTION)


__all__ = ["Episode", "utc_now"]
