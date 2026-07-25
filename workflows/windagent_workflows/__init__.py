"""
WindAgent Workflows Package (V2 Architecture — Phase 23).
Predefined workflow definitions, versioned DAG workflow packs, artifact contracts,
completion predicates, workflow migration, and version pinning.
"""

from windagent_workflows.base import WorkflowPackDefinition, BaseWorkflowPack
from windagent_workflows.models import (
    ImmutableWorkflowDefinition, WorkflowNodeSpec, WorkflowEdgeSpec,
    ArtifactContract, CompletionPredicate, NodeType, EdgeType,
)
from windagent_workflows.migration import (
    WorkflowMigrationManager, MigrationImpact, PinnedDefinition, VersionChange,
)
from windagent_workflows.registry import WorkflowRegistry, VersionedPackEntry
from windagent_workflows.packs.bugfix import BugfixWorkflowPack
from windagent_workflows.packs.ci_fix import CIFixWorkflowPack
from windagent_workflows.packs.code_review import CodeReviewWorkflowPack
from windagent_workflows.packs.feature import FeatureWorkflowPack
from windagent_workflows.packs.refactor import RefactorWorkflowPack
from windagent_workflows.packs.research import ResearchWorkflowPack
from windagent_workflows.packs.scientific_eval import ScientificEvalWorkflowPack
from windagent_workflows.packs.release import ReleaseWorkflowPack

__version__ = "0.4.0"

__all__ = [
    "WorkflowPackDefinition", "BaseWorkflowPack",
    "ImmutableWorkflowDefinition", "WorkflowNodeSpec", "WorkflowEdgeSpec",
    "ArtifactContract", "CompletionPredicate", "NodeType", "EdgeType",
    "WorkflowMigrationManager", "MigrationImpact", "PinnedDefinition", "VersionChange",
    "WorkflowRegistry", "VersionedPackEntry",
    "BugfixWorkflowPack", "CIFixWorkflowPack", "CodeReviewWorkflowPack",
    "FeatureWorkflowPack", "RefactorWorkflowPack", "ResearchWorkflowPack",
    "ScientificEvalWorkflowPack", "ReleaseWorkflowPack",
]
