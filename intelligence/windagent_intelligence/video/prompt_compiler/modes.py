"""
ModeCompiler (Phase 11) — mode-specific required inputs (plan 03 §24.3).

Each generation mode has a compiler contract that validates the shot has
everything the mode needs BEFORE the request is published:

| Mode               | Required inputs                                       |
|---|---|
| TEXT_TO_VIDEO      | none (independent shot, text-only)                    |
| IMAGE_TO_VIDEO     | >= 1 identity or location reference                   |
| FRAMES_TO_VIDEO    | first frame + last frame assets                       |
| INGREDIENTS_TO_VIDEO| >= 1 ingredient reference                             |
| VIDEO_EXTENSION    | predecessor clip (tail frame dependency)              |
| VIDEO_TO_VIDEO     | source clip (transformation input)                    |
| TEXT_TO_IMAGE      | >= 1 identity / style reference (Phase 14 image gen)  |

A mode missing a required input produces a BLOCKING `MODE_MISSING_INPUT`
issue: the request never compiles (fail closed). The mode must also be inside
the provider capability set chosen at runtime; the Director only records
preferred mode + fallbacks and never calls the provider (plan §14.3).
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from windagent_core.domain.video_production.enums import (
    GenerationMode,
    IssueSeverity,
    PromptCompilerIssueCode,
    ReferenceBindingRole,
)
from windagent_core.domain.video_production.ids import PromptCompilerIssueId
from windagent_core.domain.video_production.prompt_compiler import (
    PromptCompilerIssue,
)
from windagent_core.domain.video_production.reference_binding import (
    ReferenceBinding,
)

MODE_REQUIRED_INPUTS: Dict[GenerationMode, str] = {
    GenerationMode.TEXT_TO_VIDEO: "none",
    GenerationMode.IMAGE_TO_VIDEO: "at least one identity or location reference",
    GenerationMode.FRAMES_TO_VIDEO: "first frame and last frame assets",
    GenerationMode.INGREDIENTS_TO_VIDEO: "at least one ingredient reference",
    GenerationMode.VIDEO_EXTENSION: "a predecessor clip (tail frame)",
    GenerationMode.VIDEO_TO_VIDEO: "a source clip to transform",
    GenerationMode.TEXT_TO_IMAGE: "at least one identity or style reference",
}


class ModeCompiler:
    """Deterministic mode-specific required-input validation."""

    def __init__(self, *, id_factory=None) -> None:
        self._id_factory = id_factory

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def validate(
        self,
        *,
        mode: GenerationMode,
        shot_id,
        bindings: List[ReferenceBinding],
        reference_binding_ids: List[str],
        first_frame: bool = False,
        last_frame: bool = False,
        predecessor_clip: bool = False,
        source_clip: bool = False,
        ingredient: bool = False,
    ) -> List[PromptCompilerIssue]:
        """Return blocking MODE_MISSING_INPUT issues (empty == mode valid)."""
        roles = {b.role for b in bindings}
        has_identity_location = bool(
            roles & {ReferenceBindingRole.IDENTITY, ReferenceBindingRole.LOCATION}
        )
        has_style = ReferenceBindingRole.STYLE in roles
        has_ingredient = ingredient or ReferenceBindingRole.INGREDIENT in roles

        issues: List[PromptCompilerIssue] = []
        needs = _required_for_mode(mode)
        if needs is None:
            return issues

        ok = False
        if mode == GenerationMode.TEXT_TO_VIDEO:
            ok = True
        elif mode in (GenerationMode.IMAGE_TO_VIDEO, GenerationMode.INGREDIENTS_TO_VIDEO):
            ok = has_identity_location or has_ingredient
        elif mode == GenerationMode.FRAMES_TO_VIDEO:
            ok = first_frame and last_frame
        elif mode == GenerationMode.VIDEO_EXTENSION:
            ok = predecessor_clip
        elif mode == GenerationMode.VIDEO_TO_VIDEO:
            ok = source_clip
        elif mode == GenerationMode.TEXT_TO_IMAGE:
            ok = has_identity_location or has_style

        if not ok:
            issues.append(
                PromptCompilerIssue(
                    issue_id=PromptCompilerIssueId(
                        self._new_issue_id(mode, shot_id)
                    ),
                    code=PromptCompilerIssueCode.MODE_MISSING_INPUT,
                    severity=IssueSeverity.BLOCKING,
                    message=(
                        f"Mode {mode.value} requires {needs} but the compiled "
                        f"request for shot {shot_id} does not provide it."
                    ),
                    blocking=True,
                    shot_id=shot_id,
                    details={
                        "generation_mode": mode.value,
                        "required_inputs": needs,
                        "has_identity_location": has_identity_location,
                        "has_ingredient": has_ingredient,
                        "has_style": has_style,
                        "first_frame": first_frame,
                        "last_frame": last_frame,
                        "predecessor_clip": predecessor_clip,
                        "source_clip": source_clip,
                        "binding_ids": list(reference_binding_ids),
                    },
                )
            )
        return issues

    def _new_issue_id(self, mode: GenerationMode, shot_id) -> str:
        seed = f"{mode.value}:{shot_id}"
        if self._id_factory is not None:
            return self._id_factory.prompt_issue_id(seed)
        return "pci_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def required_inputs_for(cls, mode: GenerationMode) -> str:
        return MODE_REQUIRED_INPUTS.get(mode, "none")


def _required_for_mode(mode: GenerationMode) -> Optional[str]:
    return MODE_REQUIRED_INPUTS.get(mode)


__all__ = ["ModeCompiler", "MODE_REQUIRED_INPUTS"]
