"""
Workflow Migration Support for WindAgent Workflow Packs (Phase 23).
Handles version-aware workflow definition changes:
- Detects version differences between definitions
- Ensures old runs continue using the definition version they started with
- Provides upgrade impact analysis
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from windagent_core.errors.exceptions import ValidationError
from windagent_workflows.models import ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec

logger = logging.getLogger("windagent.workflows.migration")


@dataclass
class VersionChange:
    """A single change between two workflow definition versions."""
    change_type: str  # added, removed, modified, unchanged
    path: str  # JSON path to the changed element
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_type": self.change_type,
            "path": self.path,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


@dataclass
class MigrationImpact:
    """Impact analysis result for a workflow definition change."""
    is_backward_compatible: bool
    breaking_changes: List[str]
    added_nodes: List[str]
    removed_nodes: List[str]
    modified_nodes: List[str]
    added_edges: List[str]
    removed_edges: List[str]
    version_changes: List[VersionChange]
    recommended_action: str = "upgrade"  # upgrade, warn, block

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_backward_compatible": self.is_backward_compatible,
            "breaking_changes": self.breaking_changes,
            "added_nodes": self.added_nodes,
            "removed_nodes": self.removed_nodes,
            "modified_nodes": self.modified_nodes,
            "added_edges": self.added_edges,
            "removed_edges": self.removed_edges,
            "recommended_action": self.recommended_action,
        }


@dataclass
class PinnedDefinition:
    """A workflow definition pinned to a specific version for a run."""
    definition: ImmutableWorkflowDefinition
    pinned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "definition": self.definition.to_dict(),
            "pinned_at": self.pinned_at,
            "run_id": self.run_id,
        }


class WorkflowMigrationManager:
    """Manages workflow definition versioning and migration.
    Ensures old runs keep using the definition version they started with.
    """

    def __init__(self):
        # Pinned definitions: run_id -> PinnedDefinition
        self._pinned_definitions: Dict[str, PinnedDefinition] = {}
        # Version history: workflow_name -> { version -> ImmutableWorkflowDefinition }
        self._version_history: Dict[str, Dict[str, ImmutableWorkflowDefinition]] = {}

    @staticmethod
    def compare_versions(
        old: ImmutableWorkflowDefinition,
        new: ImmutableWorkflowDefinition,
    ) -> MigrationImpact:
        """Compares two workflow definitions and produces a migration impact analysis."""
        breaking_changes: List[str] = []
        added_nodes: List[str] = []
        removed_nodes: List[str] = []
        modified_nodes: List[str] = []
        added_edges: List[str] = []
        removed_edges: List[str] = []
        version_changes: List[VersionChange] = []

        # Compare nodes
        old_node_ids = set(old.nodes.keys())
        new_node_ids = set(new.nodes.keys())

        for nid in new_node_ids - old_node_ids:
            added_nodes.append(nid)
            version_changes.append(VersionChange(
                change_type="added", path=f"nodes/{nid}", new_value=nid,
            ))

        for nid in old_node_ids - new_node_ids:
            removed_nodes.append(nid)
            version_changes.append(VersionChange(
                change_type="removed", path=f"nodes/{nid}", old_value=nid,
            ))
            breaking_changes.append(f"Node [{nid}] was removed")

        for nid in old_node_ids & new_node_ids:
            if old.nodes[nid] != new.nodes[nid]:
                modified_nodes.append(nid)
                version_changes.append(VersionChange(
                    change_type="modified", path=f"nodes/{nid}",
                    old_value=old.nodes[nid].tool_name,
                    new_value=new.nodes[nid].tool_name,
                ))

        # Compare edges
        old_edge_set = {(e.from_node_id, e.to_node_id) for e in old.edges}
        new_edge_set = {(e.from_node_id, e.to_node_id) for e in new.edges}

        for edge in new.edges:
            key = (edge.from_node_id, edge.to_node_id)
            if key not in old_edge_set:
                added_edges.append(f"{edge.from_node_id} -> {edge.to_node_id}")
                version_changes.append(VersionChange(
                    change_type="added", path=f"edges/{key}", new_value=str(key),
                ))

        for edge in old.edges:
            key = (edge.from_node_id, edge.to_node_id)
            if key not in new_edge_set:
                removed_edges.append(f"{edge.from_node_id} -> {edge.to_node_id}")
                version_changes.append(VersionChange(
                    change_type="removed", path=f"edges/{key}", old_value=str(key),
                ))
                breaking_changes.append(f"Edge [{edge.from_node_id} -> {edge.to_node_id}] was removed")

        # Determine backward compatibility
        is_backward_compatible = len(breaking_changes) == 0
        recommended_action = "upgrade" if is_backward_compatible else "block"

        return MigrationImpact(
            is_backward_compatible=is_backward_compatible,
            breaking_changes=breaking_changes,
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            modified_nodes=modified_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
            version_changes=version_changes,
            recommended_action=recommended_action,
        )

    def record_version(self, definition: ImmutableWorkflowDefinition) -> None:
        """Records a workflow definition version in the history."""
        if definition.name not in self._version_history:
            self._version_history[definition.name] = {}
        self._version_history[definition.name][definition.semantic_version] = definition
        logger.info(f"Recorded workflow [{definition.name}] version [{definition.semantic_version}]")

    def get_version(self, workflow_name: str, version: str) -> Optional[ImmutableWorkflowDefinition]:
        """Retrieves a specific version of a workflow definition."""
        history = self._version_history.get(workflow_name, {})
        return history.get(version)

    def list_versions(self, workflow_name: str) -> List[str]:
        """Lists all available versions for a workflow."""
        history = self._version_history.get(workflow_name, {})
        return sorted(history.keys())

    # ------------------------------------------------------------------
    # Version Pinning
    # ------------------------------------------------------------------

    def pin_definition(self, run_id: str, definition: ImmutableWorkflowDefinition) -> PinnedDefinition:
        """Pins a workflow definition for a specific run.
        The run will always use this exact definition, even if the workflow is later updated.
        """
        pinned = PinnedDefinition(
            definition=definition,
            run_id=run_id,
        )
        self._pinned_definitions[run_id] = pinned
        logger.info(f"Pinned workflow [{definition.name}] v{definition.semantic_version} for run [{run_id}]")
        return pinned

    def get_pinned_definition(self, run_id: str) -> Optional[ImmutableWorkflowDefinition]:
        """Retrieves the pinned definition for a run.
        Returns None if no definition is pinned (run should use latest).
        """
        pinned = self._pinned_definitions.get(run_id)
        if pinned:
            return pinned.definition
        return None

    def release_pin(self, run_id: str) -> bool:
        """Releases the pin on a run's definition."""
        if run_id in self._pinned_definitions:
            del self._pinned_definitions[run_id]
            return True
        return False

    def get_pinned_stats(self) -> Dict[str, Any]:
        """Returns statistics about pinned definitions."""
        return {
            "total_pinned": len(self._pinned_definitions),
            "pinned_runs": list(self._pinned_definitions.keys()),
            "version_history_entries": sum(len(v) for v in self._version_history.values()),
        }

    # ------------------------------------------------------------------
    # Upgrade Analysis
    # ------------------------------------------------------------------

    def analyze_upgrade_path(
        self,
        workflow_name: str,
        current_version: str,
        target_version: str,
    ) -> MigrationImpact:
        """Analyzes the migration path between two versions."""
        old_def = self.get_version(workflow_name, current_version)
        new_def = self.get_version(workflow_name, target_version)

        if old_def is None:
            raise ValidationError(f"Workflow [{workflow_name}] version [{current_version}] not found")
        if new_def is None:
            raise ValidationError(f"Workflow [{workflow_name}] version [{target_version}] not found")

        return self.compare_versions(old_def, new_def)
