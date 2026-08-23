"""
SQLAlchemy ORM Models for Orchestration Subsystem V2.
Additive durable storage tables for task runs, workflow runs, leases, checkpoints, workers, outbox, cancellations, runtime executions, and recovery leader lease.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
)
from windagent_storage.orm.models import BaseORM, default_utc_now


class TaskRunORM(BaseORM):
    __tablename__ = "task_runs"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)
    state = Column(String(32), nullable=False, default="received")
    version = Column(Integer, nullable=False, default=1)
    priority = Column(Integer, nullable=False, default=2)
    current_step = Column(Integer, nullable=False, default=0)
    total_steps = Column(Integer, nullable=False, default=0)
    pending_permission = Column(Boolean, nullable=False, default=False)
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    project_id = Column(String(64), nullable=True)
    worktree_id = Column(String(64), nullable=True)
    facts_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_task_runs_session_state", "session_id", "state"),
        Index("ix_task_runs_state_priority_created", "state", "priority", "created_at"),
    )


class WorkflowRunV2ORM(BaseORM):
    __tablename__ = "v2_workflow_runs_v2"

    run_id = Column(String(36), primary_key=True)
    workflow_id = Column(String(36), nullable=False)
    session_id = Column(String(36), nullable=False, index=True)
    task_run_id = Column(String(36), ForeignKey("task_runs.id"), nullable=True)
    state = Column(String(32), nullable=False, default="pending")
    version = Column(Integer, nullable=False, default=1)
    checkpoint_cursor = Column(Integer, nullable=False, default=0)
    definition_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_v2_workflow_runs_task_state", "task_run_id", "state"),
    )


class WorkflowStepRunORM(BaseORM):
    __tablename__ = "workflow_step_runs"

    id = Column(String(36), primary_key=True)
    workflow_run_id = Column(String(36), ForeignKey("v2_workflow_runs_v2.run_id"), nullable=False)
    step_order = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    tool_name = Column(String(64), nullable=False)
    params_json = Column(Text, nullable=True)
    state = Column(String(32), nullable=False, default="pending")
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    ready_at = Column(DateTime(timezone=True), nullable=True)
    priority = Column(Integer, nullable=False, default=2)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_workflow_step_runs_run_state", "workflow_run_id", "state"),
        Index("ix_workflow_step_runs_state_ready_priority", "state", "ready_at", "priority"),
    )


class ExecutionLeaseORM(BaseORM):
    __tablename__ = "execution_leases"

    lease_id = Column(String(64), primary_key=True)
    step_run_id = Column(String(36), ForeignKey("workflow_step_runs.id"), nullable=False)
    run_id = Column(String(36), nullable=False)
    worker_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="active")  # active | expired | released | completed
    expires_at = Column(DateTime(timezone=True), nullable=False)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    lease_generation = Column(Integer, nullable=False, default=1)
    fencing_token = Column(String(128), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_execution_leases_status_expires", "status", "expires_at"),
        Index("ix_execution_leases_step_status", "step_run_id", "status"),
    )


class RuntimeExecutionORM(BaseORM):
    __tablename__ = "runtime_executions"

    id = Column(String(64), primary_key=True)
    runtime_run_id = Column(String(64), nullable=False, index=True)
    runtime_session_id = Column(String(64), nullable=True)
    attempt_id = Column(String(64), nullable=False)
    step_run_id = Column(String(36), ForeignKey("workflow_step_runs.id"), nullable=False, index=True)
    lease_generation = Column(Integer, nullable=False, default=1)
    fencing_token = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="dispatched")  # dispatched | running | completed | failed | cancelled | timeout | lost | unknown
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    result_ref = Column(String(256), nullable=True)
    error_metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_runtime_executions_status_heartbeat", "status", "heartbeat_at"),
        Index("ix_runtime_executions_step_fencing", "step_run_id", "fencing_token"),
    )


class RecoveryLeaderLeaseORM(BaseORM):
    __tablename__ = "recovery_leader_leases"

    lease_name = Column(String(64), primary_key=True, default="recovery_leader")
    leader_id = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class ExecutionAttemptORM(BaseORM):
    __tablename__ = "execution_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_run_id = Column(String(36), ForeignKey("workflow_step_runs.id"), nullable=False)
    attempt_index = Column(Integer, nullable=False, default=1)
    worker_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_execution_attempts_step_attempt", "step_run_id", "attempt_index"),
    )


class WorkflowCheckpointORM(BaseORM):
    __tablename__ = "workflow_checkpoints"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(36), ForeignKey("v2_workflow_runs_v2.run_id"), nullable=False)
    step_id = Column(String(36), nullable=False)
    cursor = Column(Integer, nullable=False)
    state_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    __table_args__ = (
        Index("ix_workflow_checkpoints_run_cursor", "run_id", "cursor"),
    )


class CancellationRequestORM(BaseORM):
    __tablename__ = "cancellation_requests"

    id = Column(String(64), primary_key=True)
    target_id = Column(String(64), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, default="task")  # task | workflow | step
    reason = Column(Text, nullable=False)
    requested_by = Column(String(64), nullable=False, default="user")
    status = Column(String(32), nullable=False, default="pending")  # pending | processed
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class WorkerRegistrationORM(BaseORM):
    __tablename__ = "worker_registrations"

    worker_id = Column(String(64), primary_key=True)
    runtime_type = Column(String(32), nullable=False, default="local")
    health = Column(String(32), nullable=False, default="healthy")  # healthy | degraded | unhealthy
    active_leases = Column(Integer, nullable=False, default=0)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("ix_worker_registrations_type_health", "runtime_type", "health"),
    )


class WorkflowEdgeORM(BaseORM):
    __tablename__ = "workflow_edges"

    id = Column(String(64), primary_key=True)
    workflow_id = Column(String(36), nullable=False, index=True)
    source_step_id = Column(String(36), nullable=False)
    target_step_id = Column(String(36), nullable=False)
    condition_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class MemoryRecordORM(BaseORM):
    __tablename__ = "memory_records"

    id = Column(String(64), primary_key=True)
    session_id = Column(String(36), nullable=True, index=True)
    memory_type = Column(String(32), nullable=False, default="short_term")  # short_term | long_term | working
    key = Column(String(128), nullable=False)
    value_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class PluginInstallationORM(BaseORM):
    __tablename__ = "plugin_installations"

    plugin_id = Column(String(64), primary_key=True)
    version = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="active")  # active | disabled | quarantined
    manifest_json = Column(Text, nullable=False, default="{}")
    installed_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class SkillInstallationORM(BaseORM):
    __tablename__ = "skill_installations"

    skill_id = Column(String(64), primary_key=True)
    version = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    manifest_json = Column(Text, nullable=False, default="{}")
    installed_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)


class TaskExecutionResultORM(BaseORM):
    __tablename__ = "task_execution_results_v2"

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), nullable=False, index=True)
    worker_id = Column(String(64), nullable=False)
    execution_status = Column(String(32), nullable=False, default="completed")
    result_data_json = Column(Text, nullable=False, default="{}")
    artifacts_data_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, default=default_utc_now)

    @property
    def result_data(self) -> dict:
        import json
        return json.loads(self.result_data_json) if self.result_data_json else {}

    @result_data.setter
    def result_data(self, val: dict):
        import json
        self.result_data_json = json.dumps(val or {})

    @property
    def artifacts_data(self) -> list:
        import json
        return json.loads(self.artifacts_data_json) if self.artifacts_data_json else []

    @artifacts_data.setter
    def artifacts_data(self, val: list):
        import json
        self.artifacts_data_json = json.dumps(val or [])


