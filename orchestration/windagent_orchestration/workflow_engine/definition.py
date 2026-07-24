"""
Workflow Definition Alias for WindAgent Orchestration (Phase 8 Adoption).
Re-exports canonical Graph WorkflowDefinition models directly from windagent_core.domain.workflow.
"""

from windagent_core.domain.workflow import WorkflowDefinition, WorkflowNode, WorkflowEdge

__all__ = ["WorkflowDefinition", "WorkflowNode", "WorkflowEdge"]
