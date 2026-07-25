"""
Workflow Registry for WindAgent Workflow Packs (Phase 23).
Manages workflow pack registration, version pinning, version-aware task classification,
and definition version history. Supports semantic versioning for all registered packs.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

from windagent_core.errors.exceptions import ConflictError, NotFoundError, ValidationError
from windagent_workflows.base import BaseWorkflowPack
from windagent_workflows.models import ImmutableWorkflowDefinition
from windagent_workflows.migration import WorkflowMigrationManager

logger = logging.getLogger("windagent.workflows.registry")


class VersionedPackEntry:
    """A registered workflow pack with optional version pinning."""
    def __init__(self, pack: BaseWorkflowPack):
        self.pack = pack
        self._version_definitions: Dict[str, ImmutableWorkflowDefinition] = {}

    @property
    def name(self) -> str:
        return self.pack.name

    @property
    def version(self) -> str:
        return self.pack.version

    def record_definition(self, definition: ImmutableWorkflowDefinition) -> None:
        """Records a generated workflow definition version."""
        self._version_definitions[definition.semantic_version] = definition

    def get_definition(self, version: Optional[str] = None) -> Optional[ImmutableWorkflowDefinition]:
        """Gets a specific definition version, or latest if None."""
        if version:
            return self._version_definitions.get(version)
        # Return latest
        versions = sorted(self._version_definitions.keys())
        if versions:
            return self._version_definitions[versions[-1]]
        return None

    def list_versions(self) -> List[str]:
        return sorted(self._version_definitions.keys())


class WorkflowRegistry:
    def __init__(self):
        self._packs: Dict[str, VersionedPackEntry] = {}
        self.migration_manager = WorkflowMigrationManager()

    def register_pack(self, pack: BaseWorkflowPack) -> None:
        """Registers a workflow pack with version tracking."""
        name = pack.name
        if name in self._packs:
            raise ConflictError(f"Workflow pack [{name}] is already registered.")

        entry = VersionedPackEntry(pack)
        self._packs[name] = entry
        logger.info(f"Registered workflow pack [{name}] v{pack.version}")

    def get_pack(self, name: str) -> BaseWorkflowPack:
        """Gets the latest version of a workflow pack."""
        if name not in self._packs:
            raise NotFoundError(f"Workflow pack [{name}] is not registered.")
        return self._packs[name].pack

    def get_pack_at_version(self, name: str, version: str) -> Optional[BaseWorkflowPack]:
        """Gets a specific version of a workflow pack (if versioned)."""
        entry = self._packs.get(name)
        if entry is None:
            raise NotFoundError(f"Workflow pack [{name}] is not registered.")
        return entry.pack

    def list_packs(self) -> List[BaseWorkflowPack]:
        return [entry.pack for entry in self._packs.values()]

    async def close(self) -> None:
        """Closes registered workflow packs and releases resources."""
        return None


    def list_packs_with_versions(self) -> List[Dict[str, str]]:
        """Lists all registered packs with their versions."""
        return [
            {"name": entry.name, "version": entry.version}
            for entry in self._packs.values()
        ]

    def classify_task(self, prompt: str) -> Optional[BaseWorkflowPack]:
        """Classifies a user task prompt to matching workflow pack by keyword rules."""
        prompt_lower = prompt.lower()
        for entry in self._packs.values():
            pack = entry.pack
            for rule in pack.definition.classification_rules:
                if rule.lower() in prompt_lower:
                    logger.info(f"Classified prompt to workflow pack [{pack.name}] v{pack.version} (matched rule: '{rule}')")
                    return pack
        return None

    # ------------------------------------------------------------------
    # Version pinning
    # ------------------------------------------------------------------

    def pin_workflow(self, run_id: str, workflow_name: str, params: Dict[str, Any]) -> ImmutableWorkflowDefinition:
        """Generates a workflow definition and pins it for a specific run.
        The run will always use this exact definition, even if the pack is later updated.
        """
        pack = self.get_pack(workflow_name)
        definition = pack.build_workflow_definition(params)

        # Record in version history
        entry = self._packs[workflow_name]
        entry.record_definition(definition)
        self.migration_manager.record_version(definition)

        # Pin for this run
        self.migration_manager.pin_definition(run_id, definition)

        return definition

    def get_pinned_workflow(self, run_id: str) -> Optional[ImmutableWorkflowDefinition]:
        """Gets the pinned workflow definition for a run, or None if not pinned."""
        return self.migration_manager.get_pinned_definition(run_id)

    def release_pin(self, run_id: str) -> bool:
        """Releases the version pin on a run."""
        return self.migration_manager.release_pin(run_id)

    def get_version_stats(self) -> Dict[str, Any]:
        """Returns version statistics for all registered packs."""
        stats = {}
        for name, entry in self._packs.items():
            stats[name] = {
                "current_version": entry.version,
                "available_versions": entry.list_versions(),
            }
        stats["pinned"] = self.migration_manager.get_pinned_stats()
        return stats
