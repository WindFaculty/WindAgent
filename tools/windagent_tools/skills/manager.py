"""
Skill Manager for WindAgent Tool Platform.
Handles skill registration, lazy loading, rule matching, token budget accounting, and prompt formatting.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ConflictError, NotFoundError
from windagent_tools.skills.manifest import SkillManifest

logger = logging.getLogger("windagent.tools.skills")


class SkillManager:
    def __init__(self, default_max_token_budget: int = 8000):
        self.default_max_token_budget = default_max_token_budget
        self._skills: Dict[str, SkillManifest] = {}
        self._loaded_templates: Dict[str, str] = {}

    def register_skill(self, manifest: SkillManifest) -> None:
        """Registers a skill manifest lazily."""
        manifest.validate()
        if manifest.id in self._skills:
            raise ConflictError(f"Skill with ID [{manifest.id}] is already registered.")

        self._skills[manifest.id] = manifest
        logger.info(f"Registered skill [{manifest.id}] (token budget: {manifest.token_budget})")

    def get_skill(self, skill_id: str) -> SkillManifest:
        if skill_id not in self._skills:
            raise NotFoundError(f"Skill [{skill_id}] is not registered.")
        return self._skills[skill_id]

    def list_skills(self) -> List[SkillManifest]:
        return list(self._skills.values())

    def find_matching_skills(self, task_description: str) -> List[SkillManifest]:
        """Matches registered skills against task description rules."""
        matched: List[SkillManifest] = []
        desc_lower = task_description.lower()

        for skill in self._skills.values():
            if not skill.activation_rules:
                continue
            for rule in skill.activation_rules:
                if rule.lower() in desc_lower:
                    matched.append(skill)
                    break

        return matched

    def render_skill_prompt(self, skill_id: str, context_vars: Optional[Dict[str, Any]] = None) -> str:
        """Lazy loads and renders the skill prompt template with context variables."""
        skill = self.get_skill(skill_id)
        if skill_id not in self._loaded_templates:
            self._loaded_templates[skill_id] = skill.prompt_template

        raw_template = self._loaded_templates[skill_id]
        if not context_vars:
            return raw_template

        try:
            return raw_template.format(**context_vars)
        except KeyError as e:
            logger.warning(f"Missing variable {e} when rendering skill [{skill_id}] template")
            return raw_template
