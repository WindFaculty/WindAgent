"""
WindAgent Workflows Package (V2 Architecture).
Predefined workflow definitions, step DAG sequences, and workflow pack registry.
"""

from windagent_workflows.base import WorkflowPackDefinition, BaseWorkflowPack
from windagent_workflows.registry import WorkflowRegistry
from windagent_workflows.packs.bugfix import BugfixWorkflowPack
from windagent_workflows.packs.ci_fix import CIFixWorkflowPack
from windagent_workflows.packs.code_review import CodeReviewWorkflowPack
from windagent_workflows.packs.feature import FeatureWorkflowPack
from windagent_workflows.packs.refactor import RefactorWorkflowPack
from windagent_workflows.packs.research import ResearchWorkflowPack
from windagent_workflows.packs.scientific_eval import ScientificEvalWorkflowPack
from windagent_workflows.packs.release import ReleaseWorkflowPack

__version__ = "0.3.0"

__all__ = [
    "WorkflowPackDefinition", "BaseWorkflowPack",
    "WorkflowRegistry",
    "BugfixWorkflowPack",
    "CIFixWorkflowPack",
    "CodeReviewWorkflowPack",
    "FeatureWorkflowPack",
    "RefactorWorkflowPack",
    "ResearchWorkflowPack",
    "ScientificEvalWorkflowPack",
    "ReleaseWorkflowPack",
]
