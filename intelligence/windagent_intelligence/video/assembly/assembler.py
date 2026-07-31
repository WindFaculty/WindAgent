"""
PackageAssembler (Phase 6 slice 9) — assemble VideoProductionPackage v1.

Takes the canonical pre-production parts (brief, concept, screenplay,
characters, locations, props, style bible, dialogue, asset prompt specs) and
assembles a validated, immutable `VideoProductionPackage v1`. The package is
validated with the Phase 3 canonical validator before publish; any failure is
a typed ValidationFailureError (never a partial package).

The assembler itself is pure/offline — it never calls a model. Deterministic
content hash comes from the canonical package serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.domain.video_production.location import (
    LocationBible,
    PropBible,
    StyleBible,
)
from windagent_core.domain.video_production.package import (
    PackageProvenance,
    VideoProductionPackage,
)
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    DialogueLine,
    Screenplay,
    StoryConcept,
)
from windagent_core.domain.video_production.validation import (
    ValidationIssue,
    VideoProductionPackageValidator,
)

from windagent_intelligence.video.asset_prompts.builder import (
    AssetPromptSpecResult,
)
from windagent_intelligence.video.errors import ValidationFailureError


@dataclass(frozen=True)
class PackageAssemblyReceipt:
    """Evidence that a package was assembled and validated."""

    package: VideoProductionPackage
    content_hash: str
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)


class PackageAssembler:
    """Assembles and validates a canonical VideoProductionPackage v1."""

    def __init__(self) -> None:
        self.validator = VideoProductionPackageValidator

    def assemble(
        self,
        *,
        project_id: str,
        revision_id: str,
        created_by: str,
        brief: Optional[CreativeBrief] = None,
        concept: Optional[StoryConcept] = None,
        screenplay: Optional[Screenplay] = None,
        characters: Optional[List[CharacterBible]] = None,
        locations: Optional[List[LocationBible]] = None,
        props: Optional[List[PropBible]] = None,
        style_bible: Optional[StyleBible] = None,
        dialogue: Optional[List[DialogueLine]] = None,
        asset_prompts: Optional[List[AssetPromptSpecResult]] = None,
        source_commit: Optional[str] = None,
    ) -> PackageAssemblyReceipt:
        """Assemble and validate; returns a receipt (never a partial package)."""
        package = VideoProductionPackage(
            schema_version="1.0.0",
            project_id=VideoProjectId(project_id),
            revision_id=ProductionRevisionId(revision_id),
            creative_brief=brief,
            story_concept=concept,
            screenplay=screenplay,
            characters=list(characters or []),
            locations=list(locations or []),
            props=list(props or []),
            style_bible=style_bible,
            dialogue=list(dialogue or []),
            provenance=PackageProvenance(
                created_by=created_by,
                source_commit=source_commit,
                metadata={
                    "asset_prompt_specs": [
                        {
                            "capability": r.capability,
                            "target_id": r.target_id,
                            "prompt_version": r.prompt_spec.version,
                            "prompt_hash": r.prompt_spec.content_hash,
                        }
                        for r in (asset_prompts or [])
                    ]
                },
            ),
        )
        issues = self.validator.validate(package)
        if issues:
            raise ValidationFailureError(
                "Assembled package failed canonical validation.",
                details={
                    "issue_count": len(issues),
                    "first": [i.code for i in issues[:5]],
                },
            )
        return PackageAssemblyReceipt(
            package=package,
            content_hash=package.content_hash(),
            valid=True,
            issues=[],
        )


__all__ = ["PackageAssembler", "PackageAssemblyReceipt"]
