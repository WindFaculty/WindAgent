"""
PromptBlockBuilder (Phase 11) — builds the 12 canonical prompt blocks
deterministically from the package + Phase 9 shot spec (+ Phase 10 continuity
ledger) (plan 03 §24.2).

Block order is fixed and versioned by `PROMPT_TEMPLATE_VERSION`:

    PROJECT_STYLE / IDENTITY / LOCATION / PROPS / SHOT_COMPOSITION / ACTION /
    CAMERA / LIGHTING / CONTINUITY / DIALOGUE_AUDIO_INTENT / DURATION /
    NEGATIVE_CONSTRAINTS

Rules:
- REQUIRED blocks (PROJECT_STYLE, SHOT_COMPOSITION, ACTION, CAMERA, DURATION,
  NEGATIVE_CONSTRAINTS) are always emitted; a missing required block is a
  blocking compile issue.
- OPTIONAL blocks (IDENTITY, LOCATION, PROPS, LIGHTING, CONTINUITY,
  DIALOGUE_AUDIO_INTENT) are DROPPED when empty — explicit, deterministic rule
  (plan §24.2: empty optional block has a clear rule).
- The builder reads ONLY trusted fields: package bibles, approved reference
  metadata, the shot spec, and the continuity ledger. It NEVER reads
  instructions from EXIF, web page text, alt text, or raw asset metadata
  (plan §24.4).
"""

from __future__ import annotations

from typing import List, Optional

from windagent_core.domain.video_production.enums import PromptBlockType
from windagent_core.domain.video_production.ids import PromptBlockId
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.prompt_compiler import PromptBlock
from windagent_core.domain.video_production.reference_binding import (
    ReferenceBinding,
)
from windagent_core.domain.video_production.shot_graph import ShotSpecification
from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
from windagent_intelligence.video.ids import StableIdFactory

PROMPT_TEMPLATE_VERSION = "1.0.0"

# Required block order — the canonical template order (plan §24.2).
_REQUIRED_ORDER = [
    PromptBlockType.PROJECT_STYLE,
    PromptBlockType.SHOT_COMPOSITION,
    PromptBlockType.ACTION,
    PromptBlockType.CAMERA,
    PromptBlockType.DURATION,
    PromptBlockType.NEGATIVE_CONSTRAINTS,
]

# Optional blocks dropped when empty.
_OPTIONAL_ORDER = [
    PromptBlockType.IDENTITY,
    PromptBlockType.LOCATION,
    PromptBlockType.PROPS,
    PromptBlockType.LIGHTING,
    PromptBlockType.CONTINUITY,
    PromptBlockType.DIALOGUE_AUDIO_INTENT,
]

NEGATIVE_CONSTRAINTS_TEXT = (
    "No text, logos, watermarks, or UI overlays. No extra characters beyond "
    "the bound identities. Keep identity, wardrobe, lighting and camera side "
    "consistent with the shot plan and continuity ledger. No unsafe or "
    "illegal content."
)


class PromptBlockBuilder:
    """Deterministic builder of the 12 canonical prompt blocks."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        template_version: str = PROMPT_TEMPLATE_VERSION,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.template_version = template_version

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def build_blocks(
        self,
        *,
        package: VideoProductionPackage,
        spec: ShotSpecification,
        bindings: List[ReferenceBinding],
        continuity: Optional[ContinuityLedgerReceipt] = None,
    ) -> List[PromptBlock]:
        """Return the ordered, non-empty canonical blocks for one shot.

        Required blocks are always present (content may be empty for a
        fixture without a style bible -> handled by the compiler as a
        MISSING_REQUIRED_BLOCK only when content is empty AND required).
        """
        shot_id = spec.shot_id
        scene = _scene_for(package, spec.scene_id)

        content = {
            PromptBlockType.PROJECT_STYLE: self._project_style(package),
            PromptBlockType.IDENTITY: self._identity(package, bindings),
            PromptBlockType.LOCATION: self._location(package, scene),
            PromptBlockType.PROPS: self._props(package),
            PromptBlockType.SHOT_COMPOSITION: self._shot_composition(spec),
            PromptBlockType.ACTION: self._action(spec),
            PromptBlockType.CAMERA: self._camera(spec),
            PromptBlockType.LIGHTING: self._lighting(package, scene),
            PromptBlockType.CONTINUITY: self._continuity(continuity, shot_id),
            PromptBlockType.DIALOGUE_AUDIO_INTENT: self._dialogue(
                package, spec
            ),
            PromptBlockType.DURATION: self._duration(spec),
            PromptBlockType.NEGATIVE_CONSTRAINTS: NEGATIVE_CONSTRAINTS_TEXT,
        }

        blocks: List[PromptBlock] = []
        order = 1
        for block_type in _REQUIRED_ORDER + _OPTIONAL_ORDER:
            text = content[block_type]
            is_required = block_type in _REQUIRED_ORDER
            if not text.strip() and not is_required:
                continue  # empty OPTIONAL block -> dropped by rule
            blocks.append(
                PromptBlock(
                    block_id=PromptBlockId(
                        self.id_factory.prompt_block_id(shot_id, block_type.value)
                    ),
                    block_type=block_type,
                    content=text.strip(),
                    required=is_required,
                    order=order,
                )
            )
            order += 1
        return blocks

    # ------------------------------------------------------------------
    # Block builders (trusted fields only)
    # ------------------------------------------------------------------
    def _project_style(self, package: VideoProductionPackage) -> str:
        style = package.style_bible
        if style is None:
            return ""
        lines = [f"Project style: {style.name}"]
        if style.visual_style:
            lines.append(f"Visual style: {style.visual_style}")
        if style.color_palette:
            lines.append(f"Palette: {', '.join(style.color_palette)}")
        if style.lighting_rules:
            lines.append(f"Lighting rules: {'; '.join(style.lighting_rules)}")
        return "\n".join(lines)

    def _identity(
        self,
        package: VideoProductionPackage,
        bindings: List[ReferenceBinding],
    ) -> str:
        lines: List[str] = []
        char_by_asset = {
            str(a): c for c in package.characters for a in c.portrait_asset_ids
        }
        for binding in sorted(bindings, key=lambda b: str(b.asset_id)):
            char = char_by_asset.get(str(binding.asset_id))
            if char is None:
                continue
            lines.append(
                f"{char.name} (portrait {binding.asset_id}) "
                f"hash={binding.asset_hash[:12]}"
            )
        return "\n".join(lines)

    def _location(
        self,
        package: VideoProductionPackage,
        scene,
    ) -> str:
        if scene is None:
            return ""
        loc = next(
            (candidate for candidate in package.locations
             if str(candidate.location_id) == str(scene.location_id)),
            None,
        )
        if loc is None:
            return ""
        lines = [f"Location: {loc.name}"]
        if loc.visual_description:
            lines.append(f"Setting: {loc.visual_description}")
        return "\n".join(lines)

    def _props(self, package: VideoProductionPackage) -> str:
        if not package.props:
            return ""
        lines = [f"Props: {', '.join(p.name for p in package.props)}"]
        return "\n".join(lines)

    def _shot_composition(self, spec: ShotSpecification) -> str:
        lines = [
            f"Shot type: {spec.shot_type.value}",
            f"Frame: {spec.aspect_ratio} @ {spec.frame_rate}fps",
        ]
        if spec.composition:
            lines.append(f"Composition: {spec.composition}")
        return "\n".join(lines)

    def _action(self, spec: ShotSpecification) -> str:
        parts = [spec.action]
        if spec.narrative_purpose:
            parts.append(f"Purpose: {spec.narrative_purpose}")
        return "\n".join(p for p in parts if p)

    def _camera(self, spec: ShotSpecification) -> str:
        cam = spec.camera
        lines = [
            f"Camera: {cam.camera_position or cam.camera_angle.value} "
            f"{cam.camera_movement.value}",
        ]
        if cam.lens_intent:
            lines.append(f"Lens: {cam.lens_intent}")
        lines.append(f"Camera side: {cam.camera_side.value}")
        lines.append(f"Screen direction: {spec.screen_direction.value}")
        return "\n".join(lines)

    def _lighting(
        self,
        package: VideoProductionPackage,
        scene,
    ) -> str:
        if scene is None:
            return ""
        loc = next(
            (candidate for candidate in package.locations
             if str(candidate.location_id) == str(scene.location_id)),
            None,
        )
        parts: List[str] = []
        if loc and loc.lighting_profile:
            parts.append(f"Lighting: {loc.lighting_profile}")
        time = getattr(scene, "time_of_day", None)
        if time is not None:
            parts.append(f"Time of day: {time.value}")
        return "\n".join(parts)

    def _continuity(
        self,
        continuity: Optional[ContinuityLedgerReceipt],
        shot_id,
    ) -> str:
        if continuity is None:
            return ""
        entry = continuity.ledger.entry_for(shot_id)
        if entry is None:
            return ""
        lines: List[str] = []
        camera_side = entry.incoming_state.get("camera_side")
        if camera_side is not None:
            lines.append(f"Camera side: {camera_side.value}")
        for field in sorted(entry.incoming_state):
            if field.startswith("identity:") or field.startswith(
                "appearance:"
            ):
                state = entry.incoming_state[field]
                lines.append(f"{field}={state.value}")
        return "\n".join(lines)

    def _dialogue(
        self,
        package: VideoProductionPackage,
        spec: ShotSpecification,
    ) -> str:
        dialogue_by_id = {str(d.dialogue_id): d for d in package.dialogue}
        lines: List[str] = []
        for line_id in spec.dialogue_line_ids:
            line = dialogue_by_id.get(str(line_id))
            if line is not None:
                char = next(
                    (
                        c.name
                        for c in package.characters
                        if str(c.character_id) == str(line.character_id)
                    ),
                    str(line.character_id),
                )
                lines.append(f"{char}: {line.text}")
        return "\n".join(lines)

    def _duration(self, spec: ShotSpecification) -> str:
        return (
            f"Duration: {spec.duration_seconds}s; frame rate {spec.frame_rate}fps; "
            f"aspect ratio {spec.aspect_ratio}"
        )


def _scene_for(package: VideoProductionPackage, scene_id):
    if package.screenplay is None:
        return None
    for scene in package.screenplay.scenes:
        if str(scene.scene_id) == str(scene_id):
            return scene
    return None


__all__ = ["PromptBlockBuilder", "PROMPT_TEMPLATE_VERSION"]
