"""Studio orchestration package (Plan A — A4, studio.contract/v0.1).

``StudioRunService`` is the sole new Story orchestration authority. It plans
Studio Story DAGs, persists run/node state BEFORE any durable submission,
dispatches through ``StudioTaskSubmissionPort`` (queue + outbox), and advances
the DAG only through ``StudioCompletionReconciler``.
"""

from windagent_orchestration.studio.service import StudioRunService, StudioCompletionReconciler

__all__ = ["StudioRunService", "StudioCompletionReconciler"]
