"""
ContinuationService (Phase 6 slice 7) — plot continuation and revision proposal.

Creates a REVISION PROPOSAL (new draft) for continuing a locked screenplay
with new episodes. It never mutates the locked screenplay, never renumbers
prior episodes, and preserves existing facts/IDs. Downstream invalidation
intent is declared so schedulers invalidate correctly.

Provider-neutral: builds a versioned/hashed PromptSpec, calls the model port,
and parses the returned continuation deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from windagent_core.domain.video_production.enums import InvalidationIntent
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    Screenplay,
)

from windagent_intelligence.video.errors import (
    EmptyResponseError,
    LockedScreenplayMutationError,
    ResponseParseError,
)
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.parsing import (
    CanonicalEpisode,
    split_episodes,
)
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    PreproductionModelPort,
)
from windagent_intelligence.video.prompts import PromptSpec

CONTINUATION_PROMPT_V1 = PromptSpec(
    capability="continuation",
    version="1.0.0",
    description="Continue a screenplay with new episodes (revision proposal).",
    template=(
        "You are a screenwriter continuing an existing story.\n"
        "Write the NEXT episode(s) in the canonical screenplay format "
        "(## Episode <N>, ## Scene <N> | <TIME> | <SPACE> | <Location>, "
        "Characters: ..., Name: dialogue, <action>narration</action>).\n"
        "Do NOT renumber or rewrite the existing episodes.\n\n"
        "EXISTING EPISODE COUNT: {existing_episode_count}\n"
        "CONTINUATION BRIEF: {continuation_brief}\n"
        "EXISTING CHARACTERS: {existing_characters}"
    ),
)


@dataclass(frozen=True)
class ContinuationResult:
    """Revision proposal for continuing a locked screenplay."""

    proposal: Screenplay
    added_episodes: List[CanonicalEpisode]
    invalidation_intent: InvalidationIntent
    existing_episode_count: int
    prompt_version: str
    prompt_hash: str


class ContinuationService:
    """Builds a revision proposal without mutating the locked screenplay."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        id_factory: Optional[StableIdFactory] = None,
        canonical_model: str = "canonical-default",
        prompt_spec: PromptSpec = CONTINUATION_PROMPT_V1,
    ) -> None:
        self.model_port = model_port
        self.id_factory = id_factory or StableIdFactory()
        self.canonical_model = canonical_model
        self.prompt_spec = prompt_spec

    async def continue_screenplay(
        self,
        screenplay: Screenplay,
        brief: CreativeBrief,
        *,
        project_id: str,
        parent_revision_id: str,
        created_by: str,
        require_locked: bool = True,
        invalidation_intent: InvalidationIntent = InvalidationIntent.INVALIDATE_SHOT_PLAN,
    ) -> ContinuationResult:
        """Return a revision proposal; never mutates the locked screenplay.

        A locked screenplay requires an explicit downstream invalidation
        intent (RevisionService.derive_revision semantics). If
        `require_locked=False` the caller may use this for drafts.
        """
        if require_locked and screenplay.status.value != "LOCKED":
            raise LockedScreenplayMutationError(
                "Continuation requires a locked screenplay; status="
                f"{screenplay.status.value}.",
                details={"status": screenplay.status.value},
            )
        existing_count = int(screenplay.metadata.get("episode_count", 0) or 0)
        existing_characters = ", ".join(sorted(screenplay.metadata.get("characters", []) or []))

        rendered = self.prompt_spec.render(
            existing_episode_count=existing_count,
            continuation_brief=brief.title,
            existing_characters=existing_characters,
        )
        result = await self.model_port.complete(
            ModelCompletionRequest(
                capability="continuation",
                system="You are the WindAgent screenwriter (continuation).",
                user=rendered,
                canonical_model=self.canonical_model,
                temperature=0.7,
                max_tokens=3000,
                prompt_spec=self.prompt_spec,
            )
        )
        if not result.content or not result.content.strip():
            raise EmptyResponseError("Continuation received an empty response.")
        episodes = split_episodes(result.content)
        if not episodes:
            raise ResponseParseError(
                "Continuation text did not contain a parseable episode.",
                details={"raw": result.content[:200]},
            )
        # New proposal copy: preserve existing scenes, append new episode scenes
        from windagent_core.domain.video_production.enums import ScreenplayStatus
        from windagent_core.domain.video_production.ids import ScreenplayId
        from windagent_core.domain.video_production.scene import Scene

        max_order = max((s.order for s in screenplay.scenes), default=0)
        new_scenes = list(screenplay.scenes)
        for ep in episodes:
            for scene in ep.scenes:
                max_order += 1
                new_scenes.append(
                    Scene(
                        scene_id=_next_scene_id(self.id_factory, screenplay, max_order),
                        order=max_order,
                        title=scene.header.location or f"Scene {max_order}",
                        location_id=_continuation_loc(self.id_factory, scene.header.location),
                        character_ids=[],
                        dialogue_line_ids=[],
                        action_description="\n".join(u.text for u in scene.units if not u.is_dialogue),
                        metadata={
                            "episode_number": ep.episode_number,
                            "scene_number": scene.scene_number,
                            "scene_time": scene.header.time_of_day,
                            "scene_space": scene.header.space,
                            "continuation": True,
                        },
                    )
                )
        proposal = Screenplay(
            screenplay_id=ScreenplayId(str(screenplay.screenplay_id)),
            title=screenplay.title,
            logline=screenplay.logline,
            status=ScreenplayStatus.DRAFT,
            scenes=new_scenes,
            metadata={
                **screenplay.metadata,
                "prompt_version": self.prompt_spec.version,
                "prompt_hash": self.prompt_spec.content_hash,
                "continuation_parent_revision": parent_revision_id,
                "project_id": project_id,
                "created_by": created_by,
                "invalidation_intent": invalidation_intent.value,
            },
        )
        return ContinuationResult(
            proposal=proposal,
            added_episodes=episodes,
            invalidation_intent=invalidation_intent,
            existing_episode_count=existing_count,
            prompt_version=self.prompt_spec.version,
            prompt_hash=self.prompt_spec.content_hash,
        )


def _next_scene_id(id_factory: StableIdFactory, screenplay: Screenplay, order: int):
    from windagent_core.domain.video_production.ids import SceneId

    return SceneId(id_factory.scene_id(str(screenplay.screenplay_id), order))


def _continuation_loc(id_factory: StableIdFactory, location: str):
    from windagent_core.domain.video_production.ids import LocationId

    name = location or "unspecified"
    return LocationId(id_factory.location_id(name, 0))


__all__ = ["ContinuationService", "ContinuationResult", "CONTINUATION_PROMPT_V1"]
