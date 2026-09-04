"""Live Record plan aggregate (Phase 17).

REWRITE of ``core/domain/live_record/plan.py`` onto V2 contracts:
- ``LiveExecutionPlan`` is the lineage root (Episode -> Plan -> Take).
- ``PreparedAction`` carries ONLY ``artifact://`` payload_ref (Principle C).
- Plan hash is canonical sorted-JSON SHA-256 under schema ``live_record.plan/v0``.
- Content is immutable after FROZEN; only STALE may be observed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import (
    LiveRecordInvalidTransitionError,
    LiveRecordNotFrozenError,
    LiveRecordPlanFrozenError,
    LiveRecordValidationError,
)
from .lifecycle import LiveExecutionPlanStatus, PlanStatusStateMachine

PLAN_HASH_SCHEMA_VERSION = "live_record.plan/v0"

TypingMode = Literal["TYPE", "PASTE"]
PreparedActionType = Literal[
    "CODE_PLAYBACK",
    "BROWSER_NAVIGATION",
    "BROWSER_ACTION",
    "RUN_COMMAND",
    "TOOL_RUN",
    "OPEN_FILE",
    "VISUAL_VERIFY",
    "SCENE_CONTROL",
    "MARKER",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_content_hash(*, content: Any, schema_version: str = PLAN_HASH_SCHEMA_VERSION) -> str:
    payload = {"schema_version": schema_version, "content": content}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExpectedVisualState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state_id: str = Field(min_length=1)
    description: str = ""
    url_contains: str | None = None
    file_should_contain_hash: str | None = None
    test_should_pass: bool | None = None
    screenshot_ref: str | None = None


class PreparedAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str = Field(min_length=1)
    type: PreparedActionType
    scene_id: str = Field(min_length=1)
    cue_id: str | None = None
    payload_ref: str = Field(min_length=1)
    target_file: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    typing_mode: TypingMode | None = None
    chars_per_second: int | None = Field(default=None, ge=1, le=200)
    browser_semantic_target: str | None = None
    command_ref: str | None = None
    expected_after: ExpectedVisualState | None = None
    idempotency_key: str = Field(min_length=1)
    retry_allowed: bool = True

    @field_validator("payload_ref")
    @classmethod
    def _payload_ref_must_be_artifact_uri(cls, v: str) -> str:
        if not v.startswith("artifact://"):
            raise LiveRecordValidationError(
                f"PAYLOAD_REF_MUST_BE_ARTIFACT_URI: prepared actions may only reference artifact:// payloads, got '{v[:64]}'.",
            )
        return v


class RecordingCue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cue_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    title: str = ""
    narration_ref: str | None = None
    action_ids: list[str] = Field(default_factory=list)
    expected_state: ExpectedVisualState | None = None
    recovery_hint: str | None = None


class RecordingScene(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scene_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    title: str = ""
    narration_source: str = ""
    narration_text: str | None = None
    cues: list[RecordingCue] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    expected_result: dict[str, Any] = Field(default_factory=dict)
    duration_sec: float = Field(default=0.0, ge=0)


class RecordingProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    resolution: Literal["1920x1080", "1280x720", "3840x2160"] = "1920x1080"
    fps: Literal[30, 60] = 60
    codec: Literal["H264", "HEVC"] = "H264"
    segment_minutes: Literal[5, 10] = 5


class LiveExecutionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    episode_revision_id: str = Field(min_length=1)
    preparation_revision: int = Field(default=1, ge=1)
    plan_hash: str = Field(default="", max_length=64)
    status: LiveExecutionPlanStatus = LiveExecutionPlanStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    frozen_at: datetime | None = None
    director_role: Literal["LIVE_DIRECTOR"] = "LIVE_DIRECTOR"
    recording_profile: RecordingProfile = Field(default_factory=RecordingProfile)
    scenes: list[RecordingScene] = Field(default_factory=list)
    actions: list[PreparedAction] = Field(default_factory=list)
    payload_bundles: dict[str, str] = Field(default_factory=dict)
    source_workspace_hash: str = Field(default="", max_length=64)
    optimistic_version: int = Field(default=0, ge=0)

    @property
    def allowed_action_ids(self) -> frozenset[str]:
        return frozenset(action.action_id for action in self.actions)

    @property
    def allowed_state_ids(self) -> frozenset[str]:
        ids: set[str] = set()
        for scene in self.scenes:
            for cue in scene.cues:
                if cue.expected_state is not None:
                    ids.add(cue.expected_state.state_id)
        for action in self.actions:
            if action.expected_after is not None:
                ids.add(action.expected_after.state_id)
        return frozenset(ids)

    def compute_plan_hash(self) -> str:
        content = {
            "plan_id": self.plan_id,
            "episode_id": self.episode_id,
            "episode_revision_id": self.episode_revision_id,
            "preparation_revision": self.preparation_revision,
            "recording_profile": self.recording_profile.model_dump(),
            "scenes": [scene.model_dump() for scene in self.scenes],
            "actions": [action.model_dump() for action in self.actions],
            "payload_bundles": self.payload_bundles,
        }
        return canonical_content_hash(content=content, schema_version=PLAN_HASH_SCHEMA_VERSION)

    def validate_lineage(self) -> None:
        scene_ids = {scene.scene_id for scene in self.scenes}
        cue_ids = {cue.cue_id for scene in self.scenes for cue in scene.cues}
        seen_actions: set[str] = set()
        for action in self.actions:
            if action.scene_id not in scene_ids:
                raise LiveRecordValidationError(
                    f"ACTION_SCENE_UNKNOWN: action '{action.action_id}' references unknown scene '{action.scene_id}'.",
                )
            if action.cue_id is not None and action.cue_id not in cue_ids:
                raise LiveRecordValidationError(
                    f"ACTION_CUE_UNKNOWN: action '{action.action_id}' references unknown cue '{action.cue_id}'.",
                )
            if action.action_id in seen_actions:
                raise LiveRecordValidationError(f"ACTION_DUPLICATE: action_id '{action.action_id}' appears twice.")
            seen_actions.add(action.action_id)
        for scene in self.scenes:
            unknown = [aid for aid in scene.action_ids if aid not in seen_actions]
            if unknown:
                raise LiveRecordValidationError(f"SCENE_ACTION_UNKNOWN: scene '{scene.scene_id}' lists unknown actions {unknown}.")

    def _bump(self, **changes: Any) -> LiveExecutionPlan:
        return self.model_copy(update={**changes, "optimistic_version": self.optimistic_version + 1})

    def _assert_editable(self) -> None:
        if not PlanStatusStateMachine.is_content_editable(self.status):
            if PlanStatusStateMachine.is_frozen(self.status):
                raise LiveRecordPlanFrozenError(
                    f"Plan '{self.plan_id}' is FROZEN and immutable; derive a new preparation_revision instead.",
                    context={"plan_id": self.plan_id},
                )
            raise LiveRecordValidationError(
                f"Plan '{self.plan_id}' status {self.status.value} is terminal; derive a new plan.",
                context={"plan_id": self.plan_id, "status": self.status.value},
            )

    def edit_content(
        self,
        *,
        scenes: list[RecordingScene] | None = None,
        actions: list[PreparedAction] | None = None,
        payload_bundles: dict[str, str] | None = None,
        source_workspace_hash: str | None = None,
    ) -> LiveExecutionPlan:
        self._assert_editable()
        changes: dict[str, Any] = {}
        if scenes is not None:
            changes["scenes"] = scenes
        if actions is not None:
            changes["actions"] = actions
        if payload_bundles is not None:
            changes["payload_bundles"] = payload_bundles
        if source_workspace_hash is not None:
            changes["source_workspace_hash"] = source_workspace_hash
        if self.status == LiveExecutionPlanStatus.VALIDATED:
            changes["status"] = LiveExecutionPlanStatus.PREPARED
        updated = self._bump(**changes)
        updated.validate_lineage()
        return updated

    def mark_prepared(self) -> LiveExecutionPlan:
        return self._bump(status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.PREPARED))

    def mark_validated(self) -> LiveExecutionPlan:
        self.validate_lineage()
        for action in self.actions:
            if not action.payload_ref or not action.idempotency_key:
                raise LiveRecordValidationError(f"ACTION_MALFORMED: action '{action.action_id}' missing payload_ref/idempotency_key.")
        return self._bump(status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.VALIDATED), plan_hash=self.compute_plan_hash())

    def freeze(self) -> LiveExecutionPlan:
        if self.status != LiveExecutionPlanStatus.VALIDATED:
            raise LiveRecordInvalidTransitionError(
                f"PLAN_NOT_VALIDATED: freeze requires VALIDATED, got {self.status.value}.",
                context={"plan_id": self.plan_id, "status": self.status.value},
            )
        plan_hash = self.compute_plan_hash()
        return self._bump(status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.FROZEN), plan_hash=plan_hash, frozen_at=utc_now())

    def mark_stale(self) -> LiveExecutionPlan:
        return self._bump(status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.STALE))

    def mark_invalid(self) -> LiveExecutionPlan:
        return self._bump(status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.INVALID))

    def staleness_reason(self, current_episode_revision_id: str) -> str | None:
        if self.episode_revision_id != current_episode_revision_id:
            return f"RECORDING_PLAN_STALE: plan bound to revision '{self.episode_revision_id}', episode currently at '{current_episode_revision_id}'."
        return None

    def assert_usable_for_recording(self, current_episode_revision_id: str) -> None:
        if not PlanStatusStateMachine.is_recordable(self.status):
            raise LiveRecordNotFrozenError(
                f"RECORDING_PLAN_NOT_FROZEN: status={self.status.value} plan_id={self.plan_id}.",
                context={"plan_id": self.plan_id, "status": self.status.value},
            )
        reason = self.staleness_reason(current_episode_revision_id)
        if reason:
            raise LiveRecordValidationError(reason, context={"plan_id": self.plan_id})


__all__ = [
    "ExpectedVisualState",
    "LiveExecutionPlan",
    "PLAN_HASH_SCHEMA_VERSION",
    "PreparedAction",
    "PreparedActionType",
    "RecordingCue",
    "RecordingProfile",
    "RecordingScene",
    "TypingMode",
    "canonical_content_hash",
]
