"""Live Record domain entities (live_record.contract/v0.1).

Python mirror of the Phase-0-frozen TS contracts in
``frontend/app/src/features/live-record/domain/types.ts``:

- ``LiveExecutionPlan`` aggregate with ``scenes[]``/``actions[]`` value objects.
- ``PreparedAction`` carries ONLY an ``artifact://`` payload reference — never
  inline code/commands (Principle C). The deterministic executor resolves the
  payload and verifies ``before_hash``/``after_hash``.
- Plan content is immutable after FROZEN; edits before that bump
  ``optimistic_version`` and drop VALIDATED back to PREPARED.

Plan hash reuses the studio canonical content hash (sorted-JSON SHA-256) under
schema version ``live_record.plan/v0`` so equivalent plans hash identically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windagent_core.contracts.live_record.errors import (
    LiveRecordInvalidTransitionError,
    LiveRecordNotFrozenError,
    LiveRecordPlanFrozenError,
    LiveRecordValidationError,
)
from windagent_core.contracts.live_record.ids import LiveExecutionPlanId
from windagent_core.domain.live_record.lifecycle import (
    LiveExecutionPlanStatus,
    PlanStatusStateMachine,
)
from windagent_core.domain.studio.revision import canonical_content_hash

PLAN_HASH_SCHEMA_VERSION = "live_record.plan/v0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Value objects ───────────────────────────────────────────────────────────

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


class ExpectedVisualState(BaseModel):
    """Observable screen/file/test state expected after an action."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_id: str = Field(min_length=1)
    description: str = ""
    url_contains: Optional[str] = None
    file_should_contain_hash: Optional[str] = None
    test_should_pass: Optional[bool] = None
    screenshot_ref: Optional[str] = None


class PreparedAction(BaseModel):
    """One prepared, immutable recording action.

    ``payload_ref`` MUST be an ``artifact://`` URI; real payloads live in the
    plan's prepared bundle store keyed by ``action_id``, never in tool args.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str = Field(min_length=1)
    type: PreparedActionType
    scene_id: str = Field(min_length=1)
    cue_id: Optional[str] = None
    payload_ref: str = Field(min_length=1)
    target_file: Optional[str] = None
    before_hash: Optional[str] = None
    after_hash: Optional[str] = None
    typing_mode: Optional[TypingMode] = None
    chars_per_second: Optional[int] = Field(default=None, ge=1, le=200)
    browser_semantic_target: Optional[str] = None
    command_ref: Optional[str] = None
    expected_after: Optional[ExpectedVisualState] = None
    idempotency_key: str = Field(min_length=1)
    retry_allowed: bool = True

    @field_validator("payload_ref")
    @classmethod
    def _payload_ref_must_be_artifact_uri(cls, v: str) -> str:
        if not v.startswith("artifact://"):
            raise LiveRecordValidationError(
                "PAYLOAD_REF_MUST_BE_ARTIFACT_URI: prepared actions may only "
                f"reference artifact:// payloads, got '{v[:64]}'."
            )
        return v


class RecordingCue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cue_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    title: str = ""
    narration_ref: Optional[str] = None
    action_ids: List[str] = Field(default_factory=list)
    expected_state: Optional[ExpectedVisualState] = None
    recovery_hint: Optional[str] = None


class RecordingScene(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scene_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    title: str = ""
    narration_source: str = ""  # episode_script ref
    narration_text: Optional[str] = None
    cues: List[RecordingCue] = Field(default_factory=list)
    action_ids: List[str] = Field(default_factory=list)
    expected_result: Dict[str, Any] = Field(default_factory=dict)
    duration_sec: float = Field(default=0.0, ge=0)


class RecordingProfile(BaseModel):
    """Recording profile — audio locked OFF in P0 (Principle F)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolution: Literal["1920x1080", "1280x720", "3840x2160"] = "1920x1080"
    fps: Literal[30, 60] = 60
    codec: Literal["H264", "HEVC"] = "H264"
    segment_minutes: Literal[5, 10] = 5
    audio_enabled: Literal[False] = False


# ─── Aggregate ───────────────────────────────────────────────────────────────


class LiveExecutionPlan(BaseModel):
    """Episode -> LiveExecutionPlan -> RecordingTake lineage root.

    Frozen after ``freeze()``; only STALE may be observed onto a frozen plan.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: LiveExecutionPlanId
    episode_id: str = Field(min_length=1)
    episode_revision_id: str = Field(min_length=1)
    preparation_revision: int = Field(default=1, ge=1)
    plan_hash: str = Field(default="", max_length=64)
    status: LiveExecutionPlanStatus = LiveExecutionPlanStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    frozen_at: Optional[datetime] = None
    director_role: Literal["LIVE_DIRECTOR"] = "LIVE_DIRECTOR"
    recording_profile: RecordingProfile = Field(default_factory=RecordingProfile)
    scenes: List[RecordingScene] = Field(default_factory=list)
    actions: List[PreparedAction] = Field(default_factory=list)
    # Prepared payload bundles keyed by action_id — exact content for deterministic
    # playback (Section 6). Stored as JSON in DB (payload_bundles_json) but part
    # of the aggregate so hash covers them. Never exposed via tool args.
    payload_bundles: Dict[str, str] = Field(default_factory=dict)
    source_workspace_hash: str = Field(default="", max_length=64)
    optimistic_version: int = Field(default=0, ge=0)

    # ── Derived views ────────────────────────────────────────────────────

    @property
    def allowed_action_ids(self) -> frozenset:
        return frozenset(action.action_id for action in self.actions)

    @property
    def allowed_state_ids(self) -> frozenset:
        ids = set()
        for scene in self.scenes:
            for cue in scene.cues:
                if cue.expected_state is not None:
                    ids.add(cue.expected_state.state_id)
        for action in self.actions:
            if action.expected_after is not None:
                ids.add(action.expected_after.state_id)
        return frozenset(ids)

    # ── Hashing ──────────────────────────────────────────────────────────

    def compute_plan_hash(self) -> str:
        """Deterministic hash over scenes + actions + profile + lineage + bundles."""
        content = {
            "plan_id": str(self.plan_id),
            "episode_id": self.episode_id,
            "episode_revision_id": self.episode_revision_id,
            "preparation_revision": self.preparation_revision,
            "recording_profile": self.recording_profile.model_dump(),
            "scenes": [scene.model_dump() for scene in self.scenes],
            "actions": [action.model_dump() for action in self.actions],
            "payload_bundles": self.payload_bundles,
        }
        return canonical_content_hash(content=content, schema_version=PLAN_HASH_SCHEMA_VERSION)

    # ── Validation ───────────────────────────────────────────────────────

    def validate_lineage(self) -> None:
        """Fail-closed referential checks across scenes/cues/actions."""
        scene_ids = {scene.scene_id for scene in self.scenes}
        cue_ids = {cue.cue_id for scene in self.scenes for cue in scene.cues}

        seen_actions: set = set()
        for action in self.actions:
            if action.scene_id not in scene_ids:
                raise LiveRecordValidationError(
                    f"ACTION_SCENE_UNKNOWN: action '{action.action_id}' references unknown scene '{action.scene_id}'."
                )
            if action.cue_id is not None and action.cue_id not in cue_ids:
                raise LiveRecordValidationError(
                    f"ACTION_CUE_UNKNOWN: action '{action.action_id}' references unknown cue '{action.cue_id}'."
                )
            if action.action_id in seen_actions:
                raise LiveRecordValidationError(
                    f"ACTION_DUPLICATE: action_id '{action.action_id}' appears twice."
                )
            seen_actions.add(action.action_id)

        for scene in self.scenes:
            unknown = [aid for aid in scene.action_ids if aid not in seen_actions]
            if unknown:
                raise LiveRecordValidationError(
                    f"SCENE_ACTION_UNKNOWN: scene '{scene.scene_id}' lists unknown actions {unknown}."
                )

    # ── Mutations (bump optimistic_version; frozen is immutable) ─────────

    def _bump(self, **changes: Any) -> "LiveExecutionPlan":
        return self.model_copy(
            update={**changes, "optimistic_version": self.optimistic_version + 1}
        )

    def _assert_editable(self) -> None:
        if not PlanStatusStateMachine.is_content_editable(self.status):
            if PlanStatusStateMachine.is_frozen(self.status):
                raise LiveRecordPlanFrozenError(
                    f"Plan '{self.plan_id}' is FROZEN and immutable; derive a new preparation_revision instead.",
                    details={"plan_id": str(self.plan_id)},
                )
            raise LiveRecordValidationError(
                f"Plan '{self.plan_id}' status {self.status.value} is terminal; derive a new plan.",
                details={"plan_id": str(self.plan_id), "status": self.status.value},
            )

    def edit_content(
        self,
        *,
        scenes: Optional[List[RecordingScene]] = None,
        actions: Optional[List[PreparedAction]] = None,
        payload_bundles: Optional[Dict[str, str]] = None,
        source_workspace_hash: Optional[str] = None,
    ) -> "LiveExecutionPlan":
        self._assert_editable()
        changes: Dict[str, Any] = {}
        if scenes is not None:
            changes["scenes"] = scenes
        if actions is not None:
            changes["actions"] = actions
        if payload_bundles is not None:
            changes["payload_bundles"] = payload_bundles
        if source_workspace_hash is not None:
            changes["source_workspace_hash"] = source_workspace_hash
        # Single bump carries both the content change and the status drop
        # (VALIDATED -> PREPARED): content moved, so validation no longer holds.
        if self.status == LiveExecutionPlanStatus.VALIDATED:
            changes["status"] = LiveExecutionPlanStatus.PREPARED
        updated = self._bump(**changes)
        updated.validate_lineage()
        return updated

    def mark_prepared(self) -> "LiveExecutionPlan":
        return self._bump(
            status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.PREPARED)
        )

    def mark_validated(self) -> "LiveExecutionPlan":
        self.validate_lineage()
        for action in self.actions:
            # Fail-closed tamper gate mirrors frontend validatePreparedAction().
            if not action.payload_ref or not action.idempotency_key:
                raise LiveRecordValidationError(
                    f"ACTION_MALFORMED: action '{action.action_id}' missing payload_ref/idempotency_key."
                )
        return self._bump(
            status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.VALIDATED),
            plan_hash=self.compute_plan_hash(),
        )

    def freeze(self) -> "LiveExecutionPlan":
        if self.status != LiveExecutionPlanStatus.VALIDATED:
            raise LiveRecordInvalidTransitionError(
                f"PLAN_NOT_VALIDATED: freeze requires VALIDATED, got {self.status.value}.",
                details={"plan_id": str(self.plan_id), "status": self.status.value},
            )
        plan_hash = self.compute_plan_hash()
        return self._bump(
            status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.FROZEN),
            plan_hash=plan_hash,
            frozen_at=utc_now(),
        )

    def mark_stale(self) -> "LiveExecutionPlan":
        return self._bump(
            status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.STALE)
        )

    def mark_invalid(self) -> "LiveExecutionPlan":
        return self._bump(
            status=PlanStatusStateMachine.transition(self.status, LiveExecutionPlanStatus.INVALID)
        )

    # ── Staleness (Principle A) ──────────────────────────────────────────

    def staleness_reason(self, current_episode_revision_id: str) -> Optional[str]:
        if self.episode_revision_id != current_episode_revision_id:
            return (
                f"RECORDING_PLAN_STALE: plan bound to revision "
                f"'{self.episode_revision_id}', episode currently at "
                f"'{current_episode_revision_id}'."
            )
        return None

    def assert_usable_for_recording(self, current_episode_revision_id: str) -> None:
        if not PlanStatusStateMachine.is_recordable(self.status):
            raise LiveRecordNotFrozenError(
                f"RECORDING_PLAN_NOT_FROZEN: status={self.status.value} plan_id={self.plan_id}.",
                details={"plan_id": str(self.plan_id), "status": self.status.value},
            )
        reason = self.staleness_reason(current_episode_revision_id)
        if reason:
            raise LiveRecordValidationError(reason, details={"plan_id": str(self.plan_id)})


__all__ = [
    "ExpectedVisualState",
    "PreparedAction",
    "PreparedActionType",
    "RecordingCue",
    "RecordingProfile",
    "RecordingScene",
    "TypingMode",
    "LiveExecutionPlan",
    "PLAN_HASH_SCHEMA_VERSION",
]
