"""
PreproductionPort — canonical contract for pre-production capabilities.

Implementation-independent; carries no browser/provider implementation
details (no selectors, cookies, project URLs, or session objects).
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.location import LocationBible
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    Screenplay,
    StoryConcept,
)
from windagent_core.domain.video_production.shot import CinematicPlan
from windagent_core.domain.video_production.project import VideoProject


@runtime_checkable
class PreproductionPort(Protocol):
    """Port for pre-production planning capabilities."""

    async def create_project(self, brief: CreativeBrief) -> VideoProject:
        """Create a VideoProject from a creative brief."""
        ...

    async def generate_screenplay(self, concept: StoryConcept) -> Screenplay:
        """Generate a screenplay from a story concept."""
        ...

    async def generate_cinematic_plan(self, screenplay: Screenplay) -> CinematicPlan:
        """Plan shots from a screenplay (Director capability)."""
        ...

    async def extract_characters(self, screenplay: Screenplay) -> List[CharacterBible]:
        """Extract character bibles from a screenplay."""
        ...

    async def extract_locations(self, screenplay: Screenplay) -> List[LocationBible]:
        """Extract location bibles from a screenplay."""
        ...


__all__ = ["PreproductionPort"]
