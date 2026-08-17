# ADR-FE-004: Task vs Run vs WorkflowDefinition vs WorkflowRun

- **Status**: ACCEPTED
- **Date**: 2026-08-14
- **Phase**: Phase 1 (Canonical Domain Vocabulary)
- **Deciders**: Architecture Council, Orchestration Team

---

## Context and Problem Statement
In `v2_tasks.py`, `v2_runs.py`, and `v2_workflows.py`, the word `run` or `run_id` was reused across studio generation jobs, generic async agent calls, and multi-step workflow executions without namespaces.

## Decision
We define a hierarchical execution ontology:

1. **`Task` (`tsk_*`)**:
   - **Semantic**: A discrete unit of requested work submitted by a user or an orchestrator (e.g. "Generate Character Backstory", "Render Scene 3").
2. **`Run` (`run_*`)**:
   - **Semantic**: A single physical execution attempt of a `Task` or single agent loop. A task may have multiple runs if retried or re-executed.
3. **`WorkflowDefinition` (`wfdef_*`)**:
   - **Semantic**: A reusable declarative DAG (Directed Acyclic Graph) of task steps, dependencies, inputs, outputs, and conditional branches.
4. **`WorkflowRun` (`wfrun_*`)**:
   - **Semantic**: An active or completed execution instance of a `WorkflowDefinition`. It contains and manages multiple `Task` executions and individual `Run` steps.

## Relationship Diagram
```text
WorkflowDefinition (wfdef_*)
       │
       ▼ (instantiated into)
WorkflowRun (wfrun_*)
       │
       ├── Task 1 (tsk_*) ──> Run 1 (run_*), Run 2 (run_* - retry)
       ├── Task 2 (tsk_*) ──> Run 1 (run_*)
       └── Task 3 (tsk_*) ──> Run 1 (run_*)
```

## Consequences
- **Positive**: Exact disambiguation of progress, telemetry, event logs, and status badges in UI.
- **Enforcement**: SSE/WebSocket events must include `workflow_run_id`, `task_id`, and `run_id` in their event envelopes.
