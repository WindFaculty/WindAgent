"""
Workflow Registry for WindAgent Workflow Packs.
Manages workflow pack registration and task classification.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional

from windagent_core.errors.exceptions import ConflictError, NotFoundError
from windagent_workflows.base import BaseWorkflowPack

logger = logging.getLogger("windagent.workflows.registry")


class WorkflowRegistry:
    def __init__(self):
        self._packs: Dict[str, BaseWorkflowPack] = {}

    def register_pack(self, pack: BaseWorkflowPack) -> None:
        name = pack.name
        if name in self._packs:
            raise ConflictError(f"Workflow pack [{name}] is already registered.")
        self._packs[name] = pack
        logger.info(f"Registered workflow pack [{name}]")

    def get_pack(self, name: str) -> BaseWorkflowPack:
        if name not in self._packs:
            raise NotFoundError(f"Workflow pack [{name}] is not registered.")
        return self._packs[name]

    def list_packs(self) -> List[BaseWorkflowPack]:
        return list(self._packs.values())

    def classify_task(self, prompt: str) -> Optional[BaseWorkflowPack]:
        """Classifies a user task prompt to matching workflow pack by keyword rules."""
        prompt_lower = prompt.lower()
        for pack in self._packs.values():
            for rule in pack.definition.classification_rules:
                if rule.lower() in prompt_lower:
                    logger.info(f"Classified prompt to workflow pack [{pack.name}] (matched rule: '{rule}')")
                    return pack
        return None
