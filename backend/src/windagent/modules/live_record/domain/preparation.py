"""Recording Preparation builder (Phase 17).

Deterministic builder from ``EpisodePreparationInput`` → ``LiveExecutionPlan``.
Payloads are frozen into ``payload_bundles`` keyed by ``action_id``; the plan
itself only carries ``artifact://`` refs (Principle C).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .plan import (
    ExpectedVisualState,
    LiveExecutionPlan,
    PreparedAction,
    RecordingCue,
    RecordingProfile,
    RecordingScene,
)


def _sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScenePreparationInput:
    title: str
    narration_source: str = ""
    narration_text: str | None = None
    duration_sec: float = 0.0
    expected_result: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EpisodePreparationInput:
    episode_id: str
    episode_revision_id: str
    source_workspace_hash: str = ""
    recording_profile: dict[str, Any] | None = None
    scenes: list[ScenePreparationInput] = field(default_factory=list)


class RecordingPreparationBuilder:
    @staticmethod
    def _action_defaults(
        raw: dict[str, Any],
        scene_id: str,
        cue_id: str,
        index: int,
    ) -> tuple[PreparedAction, str | None]:
        raw_type: str = (raw.get("type") or "CODE_PLAYBACK").upper()
        type_map = {
            "OPEN_FILE": "OPEN_FILE",
            "CODE_PLAYBACK": "CODE_PLAYBACK",
            "BROWSER_NAVIGATION": "BROWSER_NAVIGATION",
            "BROWSER_ACTION": "BROWSER_ACTION",
            "RUN_COMMAND": "RUN_COMMAND",
            "TOOL_RUN": "TOOL_RUN",
            "VISUAL_VERIFY": "VISUAL_VERIFY",
            "SCENE_CONTROL": "SCENE_CONTROL",
            "MARKER": "MARKER",
        }
        action_type = type_map.get(raw_type, "CODE_PLAYBACK")
        action_id = raw.get("action_id") or f"{scene_id}-a{index:03d}"
        payload_content: str | None = raw.get("content") or raw.get("payload") or raw.get("command")
        target_file = raw.get("target_file") or raw.get("file")
        browser_target = raw.get("browser_semantic_target") or raw.get("semantic_text")
        command_ref = raw.get("command_ref") or (raw.get("command") if action_type == "RUN_COMMAND" else None)
        typing_mode = raw.get("typing_mode") or ("TYPE" if action_type == "CODE_PLAYBACK" else None)
        cps = raw.get("chars_per_second")
        retry_allowed = raw.get("retry_allowed", True)
        before_hash = raw.get("before_hash")
        after_hash = raw.get("after_hash")
        if payload_content is not None and after_hash is None and action_type == "CODE_PLAYBACK":
            after_hash = _sha256_hex(payload_content)
        if payload_content is not None and before_hash is None and action_type == "CODE_PLAYBACK":
            before_hash = raw.get("before_hash") or _sha256_hex("")
        expected_after = None
        if raw.get("expected_after"):
            expected_after = ExpectedVisualState.model_validate(raw["expected_after"])
        elif raw.get("expected_result"):
            expected_after = ExpectedVisualState.model_validate(
                {"state_id": raw["expected_result"].get("visual_state_id", f"st_{action_id}"), **raw["expected_result"]}
            )
        payload_ref = raw.get("payload_ref") or f"artifact://live-record/{action_id}"
        idempotency_key = raw.get("idempotency_key") or f"idem_{action_id}"
        action = PreparedAction.model_validate({
            "action_id": action_id,
            "type": action_type,
            "scene_id": scene_id,
            "cue_id": cue_id,
            "payload_ref": payload_ref,
            "target_file": target_file,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "typing_mode": typing_mode,
            "chars_per_second": cps,
            "browser_semantic_target": browser_target,
            "command_ref": command_ref,
            "expected_after": expected_after.model_dump() if expected_after else None,
            "idempotency_key": idempotency_key,
            "retry_allowed": retry_allowed,
        })
        return action, payload_content

    @classmethod
    def build_plan(
        cls,
        inp: EpisodePreparationInput,
        *,
        plan_id: str | None = None,
        preparation_revision: int = 1,
    ) -> LiveExecutionPlan:
        scenes: list[RecordingScene] = []
        actions: list[PreparedAction] = []
        payload_bundles: dict[str, str] = {}
        for s_idx, s_inp in enumerate(inp.scenes):
            scene_id = f"scene-{s_idx+1:02d}"
            cue_id = f"{scene_id}-cue-01"
            expected_state = None
            if s_inp.expected_result.get("visual_state_id"):
                expected_state = ExpectedVisualState(
                    state_id=s_inp.expected_result["visual_state_id"],
                    description=s_inp.expected_result.get("description", ""),
                    url_contains=s_inp.expected_result.get("url_contains"),
                    test_should_pass=s_inp.expected_result.get("test"),
                )
            cue = RecordingCue(
                cue_id=cue_id,
                scene_id=scene_id,
                index=0,
                title=s_inp.title,
                narration_ref=s_inp.narration_source or f"episode://{inp.episode_id}/scene/{s_idx}",
                action_ids=[],
                expected_state=expected_state,
            )
            scene_action_ids: list[str] = []
            cue_action_ids: list[str] = []
            for a_idx, raw in enumerate(s_inp.actions):
                action, payload_content = cls._action_defaults(raw, scene_id, cue_id, a_idx)
                actions.append(action)
                scene_action_ids.append(action.action_id)
                cue_action_ids.append(action.action_id)
                if payload_content is not None:
                    payload_bundles[action.action_id] = payload_content
            cue = cue.model_copy(update={"action_ids": cue_action_ids})
            scene = RecordingScene(
                scene_id=scene_id,
                index=s_idx,
                title=s_inp.title,
                narration_source=s_inp.narration_source,
                narration_text=s_inp.narration_text,
                cues=[cue],
                action_ids=scene_action_ids,
                expected_result=s_inp.expected_result,
                duration_sec=s_inp.duration_sec,
            )
            scenes.append(scene)
        resolved_plan_id = plan_id or f"plan_{inp.episode_id}_r{preparation_revision}"
        profile = RecordingProfile.model_validate(inp.recording_profile or {})
        plan = LiveExecutionPlan.model_validate({
            "plan_id": resolved_plan_id,
            "episode_id": inp.episode_id,
            "episode_revision_id": inp.episode_revision_id,
            "preparation_revision": preparation_revision,
            "recording_profile": profile.model_dump(),
            "scenes": [s.model_dump() for s in scenes],
            "actions": [a.model_dump() for a in actions],
            "payload_bundles": payload_bundles,
            "source_workspace_hash": inp.source_workspace_hash,
        })
        plan.validate_lineage()
        return plan

    @classmethod
    def build_from_api_payload(cls, payload: dict[str, Any]) -> LiveExecutionPlan:
        scenes: list[ScenePreparationInput] = []
        for raw_scene in payload.get("scenes", []):
            scenes.append(ScenePreparationInput(
                title=raw_scene.get("title", ""),
                narration_source=raw_scene.get("narration_source", ""),
                narration_text=raw_scene.get("narration_text"),
                duration_sec=float(raw_scene.get("duration_sec", 0) or 0),
                expected_result=raw_scene.get("expected_result", {}),
                actions=list(raw_scene.get("actions", [])),
            ))
        inp = EpisodePreparationInput(
            episode_id=payload["episode_id"],
            episode_revision_id=payload["episode_revision_id"],
            source_workspace_hash=payload.get("source_workspace_hash", ""),
            recording_profile=payload.get("recording_profile"),
            scenes=scenes,
        )
        return cls.build_plan(inp, plan_id=payload.get("plan_id"), preparation_revision=int(payload.get("preparation_revision", 1)))


__all__ = ["EpisodePreparationInput", "RecordingPreparationBuilder", "ScenePreparationInput"]
