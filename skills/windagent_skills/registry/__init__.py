"""Skill registry - async wrapper over SkillManager.

Health checker and composition roots expect async list_skills().
The actual manager (SkillManager) is synchronous; this registry wraps it.
"""
from __future__ import annotations

from typing import Any, List

from windagent_skills.loader.manager import SkillManager
from windagent_skills.manifest.manifest import SkillManifest


class SkillRegistry:
    """Async registry facade over SkillManager."""

    def __init__(self, manager: SkillManager | None = None) -> None:
        self._manager = manager or SkillManager()

    async def list_skills(self) -> List[SkillManifest]:
        return self._manager.list_skills()

    async def install(self, source: str) -> Any:
        return self._manager.install(source)

    async def uninstall(self, skill_id: str) -> bool:
        return self._manager.uninstall(skill_id)

    async def close(self) -> None:
        """Closes the skill registry facade."""
        if hasattr(self._manager, "close") and callable(getattr(self._manager, "close")):
            await self._manager.close()  # type: ignore[misc]



__all__ = ["SkillRegistry"]
