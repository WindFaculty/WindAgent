"""
TaskState Canonical Alias for WindAgent Orchestration (Phase 8 Adoption).
Re-exports canonical TaskState and TaskLifecycle directly from windagent_core.domain.lifecycle.
"""

from windagent_core.domain.lifecycle import TaskState, TaskLifecycle

__all__ = ["TaskState", "TaskLifecycle"]
