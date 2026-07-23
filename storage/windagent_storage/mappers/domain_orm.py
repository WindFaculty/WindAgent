"""
Bi-directional Mappers between windagent_core Domain Objects and windagent_storage ORM Models.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone

from windagent_core.domain.types import (
    SessionId, TaskId, WorkflowId, StepId, RunId, EventId, ArtifactId
)
from windagent_core.domain.models import (
    Session, SessionStatus, Task, WorkflowRun, WorkflowStep, WorkflowStatus, StepStatus, ArtifactRef
)
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import (
    SessionORM, TaskORM, WorkflowRunORM, WorkflowStepORM, ExecutionEventORM, ArtifactRefORM
)


def orm_to_domain_session(orm: SessionORM) -> Session:
    meta = json.loads(orm.metadata_json) if orm.metadata_json else {}
    status_str = str(orm.status).lower()
    try:
        status = SessionStatus(status_str)
    except ValueError:
        status = SessionStatus.IDLE

    return Session(
        id=SessionId(orm.id),
        created_at=orm.created_at or datetime.now(timezone.utc),
        updated_at=orm.updated_at or datetime.now(timezone.utc),
        status=status,
        title=orm.title,
        agent_id=orm.agent_id,
        workspace_root=orm.workspace_root,
        metadata=meta,
    )


def domain_to_orm_session(domain: Session) -> SessionORM:
    meta_json = json.dumps(domain.metadata) if domain.metadata else None
    return SessionORM(
        id=str(domain.id),
        title=domain.title,
        status=domain.status.value,
        agent_id=domain.agent_id,
        workspace_root=domain.workspace_root,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        metadata_json=meta_json,
    )


def orm_to_domain_task(orm: TaskORM) -> Task:
    tags = json.loads(orm.tags_json) if orm.tags_json else []
    status_str = str(orm.status).lower()
    try:
        status = SessionStatus(status_str)
    except ValueError:
        status = SessionStatus.PENDING

    return Task(
        id=TaskId(orm.id),
        prompt=orm.prompt,
        session_id=SessionId(orm.session_id),
        created_at=orm.created_at or datetime.now(timezone.utc),
        status=status,
        tags=tags,
    )


def domain_to_orm_task(domain: Task) -> TaskORM:
    tags_json = json.dumps(domain.tags) if domain.tags else None
    return TaskORM(
        id=str(domain.id),
        prompt=domain.prompt,
        session_id=str(domain.session_id),
        status=domain.status.value,
        tags_json=tags_json,
        created_at=domain.created_at,
    )


def orm_to_domain_step(orm: WorkflowStepORM) -> WorkflowStep:
    params = json.loads(orm.params_json) if orm.params_json else {}
    result = json.loads(orm.result_json) if orm.result_json else None
    status_str = str(orm.status).lower()
    try:
        status = StepStatus(status_str)
    except ValueError:
        status = StepStatus.PENDING

    return WorkflowStep(
        id=StepId(orm.id),
        order=orm.step_order,
        name=orm.name,
        tool_name=orm.tool_name,
        params=params,
        status=status,
        result=result,
        error=orm.error,
    )


def domain_to_orm_step(domain: WorkflowStep, run_id: RunId) -> WorkflowStepORM:
    params_json = json.dumps(domain.params) if domain.params else None
    result_json = json.dumps(domain.result) if domain.result is not None else None
    return WorkflowStepORM(
        id=str(domain.id),
        run_id=str(run_id),
        step_order=domain.order,
        name=domain.name,
        tool_name=domain.tool_name,
        params_json=params_json,
        status=domain.status.value,
        result_json=result_json,
        error=domain.error,
    )


def orm_to_domain_workflow(orm: WorkflowRunORM) -> WorkflowRun:
    status_str = str(orm.status).lower()
    try:
        status = WorkflowStatus(status_str)
    except ValueError:
        status = WorkflowStatus.PENDING

    steps = [orm_to_domain_step(s) for s in (orm.steps or [])]
    steps.sort(key=lambda s: s.order)

    return WorkflowRun(
        run_id=RunId(orm.run_id),
        workflow_id=WorkflowId(orm.workflow_id),
        session_id=SessionId(orm.session_id),
        created_at=orm.created_at or datetime.now(timezone.utc),
        status=status,
        steps=steps,
    )


def domain_to_orm_workflow(domain: WorkflowRun) -> WorkflowRunORM:
    orm_steps = [domain_to_orm_step(s, domain.run_id) for s in domain.steps]
    return WorkflowRunORM(
        run_id=str(domain.run_id),
        workflow_id=str(domain.workflow_id),
        session_id=str(domain.session_id),
        status=domain.status.value,
        created_at=domain.created_at,
        steps=orm_steps,
    )


def orm_to_domain_event(orm: ExecutionEventORM) -> EventEnvelope:
    payload = json.loads(orm.data_json) if orm.data_json else {}
    sid = SessionId(orm.session_id) if orm.session_id else SessionId.generate()
    return EventEnvelope(
        event_id=EventId(orm.id),
        event_type=orm.event_type,
        session_id=sid,
        sequence=orm.event_seq,
        payload=payload,
        occurred_at=orm.created_at or datetime.now(timezone.utc),
    )


def domain_to_orm_event(domain: EventEnvelope) -> ExecutionEventORM:
    data_json = json.dumps(domain.payload) if domain.payload else "{}"
    return ExecutionEventORM(
        id=str(domain.event_id),
        session_id=str(domain.session_id),
        event_type=domain.event_type,
        data_json=data_json,
        event_seq=domain.sequence,
        created_at=domain.occurred_at,
    )


def orm_to_domain_artifact(orm: ArtifactRefORM) -> ArtifactRef:
    meta = json.loads(orm.metadata_json) if orm.metadata_json else {}
    return ArtifactRef(
        id=ArtifactId(orm.id),
        name=orm.name,
        mime_type=orm.mime_type,
        uri=orm.uri,
        size_bytes=orm.size_bytes,
        created_at=orm.created_at or datetime.now(timezone.utc),
        metadata=meta,
    )


def domain_to_orm_artifact(domain: ArtifactRef) -> ArtifactRefORM:
    meta_json = json.dumps(domain.metadata) if domain.metadata else None
    return ArtifactRefORM(
        id=str(domain.id),
        name=domain.name,
        mime_type=domain.mime_type,
        uri=domain.uri,
        size_bytes=domain.size_bytes,
        created_at=domain.created_at,
        metadata_json=meta_json,
    )
