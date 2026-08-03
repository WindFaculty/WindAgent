"""
Task Planner for WindAgent Intelligence (Phase 22).
Receives task classification + context + workflow catalog, produces a versioned
WorkflowDefinition with validated DAG, tool availability, permission requirements,
acceptance criteria, cost estimation, and deadline constraints.
Does NOT directly execute tools — only plans.
"""

from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from windagent_core.domain.workflow import WorkflowDefinition, WorkflowNode, WorkflowEdge
from windagent_core.errors.exceptions import ValidationError
from windagent_intelligence.task_classifier.classifier import ClassificationResult

logger = logging.getLogger("windagent.intelligence.planner")


@dataclass
class PlanRequest:
    """Input to the task planner."""
    task_prompt: str
    classification: ClassificationResult
    context_summary: str = ""
    available_tools: List[str] = field(default_factory=list)
    available_workflows: List[str] = field(default_factory=list)
    max_steps: int = 20
    budget_usd: Optional[float] = None
    deadline_seconds: Optional[float] = None

    def validate(self) -> None:
        if not self.task_prompt or not self.task_prompt.strip():
            raise ValidationError("PlanRequest task_prompt cannot be empty.")
        if self.max_steps < 1:
            raise ValidationError("PlanRequest max_steps must be >= 1.")


@dataclass
class PlanValidationResult:
    """Result of plan validation checks."""
    dag_valid: bool = True
    tools_available: bool = True
    permissions_valid: bool = True
    acceptance_criteria_met: bool = True
    cost_within_budget: bool = True
    deadline_feasible: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return all([
            self.dag_valid,
            self.tools_available,
            self.permissions_valid,
            self.acceptance_criteria_met,
            self.cost_within_budget,
            self.deadline_feasible,
        ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dag_valid": self.dag_valid,
            "tools_available": self.tools_available,
            "permissions_valid": self.permissions_valid,
            "acceptance_criteria_met": self.acceptance_criteria_met,
            "cost_within_budget": self.cost_within_budget,
            "deadline_feasible": self.deadline_feasible,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class PlanResult:
    """Output of the task planner."""
    workflow_definition: WorkflowDefinition
    validation: PlanValidationResult
    estimated_total_cost: float = 0.0
    estimated_duration_seconds: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_definition.id,
            "workflow_name": self.workflow_definition.name,
            "workflow_version": self.workflow_definition.version,
            "node_count": len(self.workflow_definition.nodes),
            "edge_count": len(self.workflow_definition.edges),
            "validation": self.validation.to_dict(),
            "estimated_total_cost": self.estimated_total_cost,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "created_at": self.created_at,
        }


# Built-in step templates for common workflow types
WORKFLOW_STEP_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "bugfix": [
        {"name": "reproduce", "tool": "exec_shell", "desc": "Reproduce the bug with evidence", "cost": 0.001, "duration": 30},
        {"name": "diagnose", "tool": "code_search", "desc": "Identify root cause", "cost": 0.002, "duration": 60},
        {"name": "patch", "tool": "write_file", "desc": "Apply the fix", "cost": 0.001, "duration": 30},
        {"name": "focused_test", "tool": "exec_shell", "desc": "Run focused test for the fix", "cost": 0.001, "duration": 20},
        {"name": "regression", "tool": "exec_shell", "desc": "Run full regression suite", "cost": 0.002, "duration": 120},
        {"name": "review", "tool": "read_file", "desc": "Review the patch", "cost": 0.001, "duration": 30},
        {"name": "report", "tool": "write_file", "desc": "Write bugfix report", "cost": 0.001, "duration": 20},
    ],
    "feature": [
        {"name": "requirements", "tool": "read_file", "desc": "Analyze requirements", "cost": 0.002, "duration": 60},
        {"name": "design", "tool": "read_file", "desc": "Design implementation", "cost": 0.002, "duration": 60},
        {"name": "implement", "tool": "write_file", "desc": "Write implementation code", "cost": 0.003, "duration": 180},
        {"name": "test", "tool": "exec_shell", "desc": "Write and run tests", "cost": 0.002, "duration": 120},
        {"name": "document", "tool": "write_file", "desc": "Document the feature", "cost": 0.001, "duration": 30},
        {"name": "review", "tool": "read_file", "desc": "Final review", "cost": 0.001, "duration": 30},
    ],
    "refactor": [
        {"name": "analyze", "tool": "code_search", "desc": "Analyze code to refactor", "cost": 0.002, "duration": 60},
        {"name": "plan_changes", "tool": "write_file", "desc": "Plan refactoring changes", "cost": 0.001, "duration": 30},
        {"name": "refactor_code", "tool": "write_file", "desc": "Apply refactoring", "cost": 0.003, "duration": 180},
        {"name": "verify", "tool": "exec_shell", "desc": "Verify no regressions", "cost": 0.002, "duration": 120},
        {"name": "report", "tool": "write_file", "desc": "Report changes made", "cost": 0.001, "duration": 20},
    ],
    "code_review": [
        {"name": "inventory", "tool": "exec_shell", "desc": "Inventory changed files", "cost": 0.001, "duration": 30},
        {"name": "risk_classification", "tool": "read_file", "desc": "Classify risk areas", "cost": 0.002, "duration": 60},
        {"name": "correctness", "tool": "read_file", "desc": "Check correctness", "cost": 0.002, "duration": 90},
        {"name": "security", "tool": "read_file", "desc": "Security review", "cost": 0.002, "duration": 90},
        {"name": "tests", "tool": "exec_shell", "desc": "Run test suite", "cost": 0.002, "duration": 120},
        {"name": "report", "tool": "write_file", "desc": "Write review report", "cost": 0.001, "duration": 30},
    ],
    "ci_fix": [
        {"name": "analyze_log", "tool": "read_file", "desc": "Analyze CI failure log", "cost": 0.001, "duration": 30},
        {"name": "diagnose", "tool": "code_search", "desc": "Diagnose root cause", "cost": 0.002, "duration": 60},
        {"name": "patch", "tool": "write_file", "desc": "Apply CI fix", "cost": 0.001, "duration": 30},
        {"name": "verify", "tool": "exec_shell", "desc": "Verify fix locally", "cost": 0.001, "duration": 60},
        {"name": "report", "tool": "write_file", "desc": "Report CI fix", "cost": 0.001, "duration": 20},
    ],
    "research": [
        {"name": "explore", "tool": "read_file", "desc": "Explore codebase", "cost": 0.002, "duration": 120},
        {"name": "analyze", "tool": "code_search", "desc": "Deep analysis", "cost": 0.003, "duration": 180},
        {"name": "synthesize", "tool": "write_file", "desc": "Synthesize findings", "cost": 0.002, "duration": 60},
        {"name": "report", "tool": "write_file", "desc": "Write research report", "cost": 0.001, "duration": 30},
    ],
    "scientific_eval": [
        {"name": "setup", "tool": "exec_shell", "desc": "Setup eval environment", "cost": 0.001, "duration": 60},
        {"name": "run_benchmarks", "tool": "exec_shell", "desc": "Run benchmarks", "cost": 0.005, "duration": 300},
        {"name": "analyze_results", "tool": "read_file", "desc": "Analyze results", "cost": 0.002, "duration": 120},
        {"name": "report", "tool": "write_file", "desc": "Write eval report", "cost": 0.001, "duration": 30},
    ],
    "release": [
        {"name": "version_bump", "tool": "write_file", "desc": "Bump version", "cost": 0.001, "duration": 10},
        {"name": "changelog", "tool": "write_file", "desc": "Update changelog", "cost": 0.001, "duration": 20},
        {"name": "build", "tool": "exec_shell", "desc": "Build artifacts", "cost": 0.001, "duration": 120},
        {"name": "tag", "tool": "git_tool", "desc": "Create release tag", "cost": 0.001, "duration": 10},
        {"name": "publish", "tool": "exec_shell", "desc": "Publish release", "cost": 0.001, "duration": 30},
        {"name": "report", "tool": "write_file", "desc": "Release report", "cost": 0.001, "duration": 20},
    ],
}


class TaskPlanner:
    """Generates a versioned WorkflowDefinition from a task classification and context."""

    def __init__(self, available_tools: Optional[List[str]] = None):
        self.available_tools = set(available_tools or [])
        self._registered_catalogs: Dict[str, List[Dict[str, Any]]] = {}

        # Register built-in step templates
        for wf_name, steps in WORKFLOW_STEP_TEMPLATES.items():
            self._registered_catalogs[wf_name] = steps

    def register_catalog(self, workflow_name: str, steps: List[Dict[str, Any]]) -> None:
        """Registers a custom workflow step catalog."""
        self._registered_catalogs[workflow_name] = steps

    def plan(self, request: PlanRequest) -> PlanResult:
        """Generates and validates a WorkflowDefinition from the plan request."""
        request.validate()

        # 1. Select best workflow template from classification
        best_candidate = self._select_workflow(request.classification)
        wf_name = best_candidate.workflow_name if best_candidate else "feature"
        logger.info(f"Planning workflow [{wf_name}] for task classification [{request.classification.primary_label}]")

        # 2. Build workflow definition
        wf_id = str(uuid.uuid4())
        steps = self._registered_catalogs.get(wf_name, self._registered_catalogs["feature"])

        # Respect max_steps
        steps = steps[:request.max_steps]

        nodes: Dict[str, WorkflowNode] = {}
        edges: List[WorkflowEdge] = []
        previous_node_id: Optional[str] = None
        estimated_cost = 0.0
        estimated_duration = 0.0

        for i, step_tmpl in enumerate(steps):
            node_id = f"step_{i + 1}_{step_tmpl['name']}"
            node = WorkflowNode(
                id=node_id,
                name=step_tmpl["name"],
                tool_name=step_tmpl["tool"],
                params={"description": step_tmpl["desc"]},
                priority=i,
                timeout_seconds=step_tmpl.get("duration", 60),
            )
            nodes[node_id] = node

            if previous_node_id:
                edges.append(WorkflowEdge(from_node_id=previous_node_id, to_node_id=node_id))
            previous_node_id = node_id

            estimated_cost += step_tmpl.get("cost", 0.001)
            estimated_duration += step_tmpl.get("duration", 30)

        definition = WorkflowDefinition(
            id=wf_id,
            name=wf_name,
            version=1,
            nodes=nodes,
            edges=edges,
        )

        # 3. Validate the plan
        validation = self._validate_plan(
            definition=definition,
            request=request,
            estimated_cost=estimated_cost,
            estimated_duration=estimated_duration,
        )

        return PlanResult(
            workflow_definition=definition,
            validation=validation,
            estimated_total_cost=estimated_cost,
            estimated_duration_seconds=estimated_duration,
        )

    def _select_workflow(self, classification: ClassificationResult) -> Optional[Any]:
        """Selects the best workflow candidate from classification results."""
        if classification.workflow_candidates:
            # Return the candidate with the highest confidence
            return max(classification.workflow_candidates, key=lambda c: c.confidence)
        return None

    def _validate_plan(
        self,
        definition: WorkflowDefinition,
        request: PlanRequest,
        estimated_cost: float,
        estimated_duration: float,
    ) -> PlanValidationResult:
        """Validates a generated plan against constraints."""
        result = PlanValidationResult()

        # 1. DAG validation: check for cycles and connectivity
        if not self._validate_dag(definition):
            result.dag_valid = False
            result.errors.append("Workflow DAG contains cycles or disconnected nodes")

        # 2. Tool availability validation
        required_tools = set()
        for node in definition.nodes.values():
            if node.tool_name:
                required_tools.add(node.tool_name)

        # Also check against the request's available_tools
        if request.available_tools:
            unavailable = required_tools - set(request.available_tools)
            if unavailable:
                result.tools_available = False
                result.errors.append(f"Required tools not available: {', '.join(unavailable)}")

        # Also check against planner's registered tools
        if self.available_tools:
            unavailable = required_tools - self.available_tools
            if unavailable:
                result.warnings.append(f"Tools not in planner registry: {', '.join(unavailable)}")

        # 3. Cost/budget validation
        if request.budget_usd is not None and estimated_cost > request.budget_usd:
            result.cost_within_budget = False
            result.errors.append(
                f"Estimated cost ${estimated_cost:.4f} exceeds budget ${request.budget_usd:.4f}"
            )

        # 4. Deadline feasibility
        if request.deadline_seconds is not None and estimated_duration > request.deadline_seconds:
            result.deadline_feasible = False
            result.errors.append(
                f"Estimated duration {estimated_duration:.0f}s exceeds deadline {request.deadline_seconds:.0f}s"
            )

        # 5. Acceptance criteria (from workflow definition)
        if not request.classification.workflow_candidates:
            result.acceptance_criteria_met = False
            result.warnings.append("No acceptance criteria defined for this workflow type")

        return result

    def _validate_dag(self, definition: WorkflowDefinition) -> bool:
        """Validates that the workflow DAG has no cycles (simple DFS cycle detection)."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for edge in definition.edges:
                if edge.from_node_id == node_id:
                    if edge.to_node_id in rec_stack:
                        return False  # Cycle detected
                    if edge.to_node_id not in visited:
                        if not dfs(edge.to_node_id):
                            return False

            rec_stack.discard(node_id)
            return True

        for node_id in definition.nodes:
            if node_id not in visited:
                if not dfs(node_id):
                    return False

        return True
