"""
Concrete Repository Implementations for WindAgent Storage Layer.
Implements TaskRepository, SessionRepository, WorkflowRepository, EventStore, ArtifactRepository.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.types import (
    TaskId, SessionId, RunId, StepId, ArtifactId
)
from windagent_core.domain.models import (
    Task, Session, WorkflowRun, ArtifactRef
)
from windagent_core.events.envelope import EventEnvelope
from windagent_storage.orm.models import (
    SessionORM, TaskORM, WorkflowRunORM, WorkflowStepORM, ExecutionEventORM, ArtifactRefORM, ProviderConfigORM
)
from windagent_storage.mappers.domain_orm import (
    orm_to_domain_session, domain_to_orm_session,
    orm_to_domain_task, domain_to_orm_task,
    orm_to_domain_workflow, domain_to_orm_workflow,
    orm_to_domain_event, domain_to_orm_event,
    orm_to_domain_artifact, domain_to_orm_artifact
)


class SqlSessionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, session_id: SessionId) -> Optional[Session]:
        stmt = select(SessionORM).where(SessionORM.id == str(session_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return orm_to_domain_session(orm) if orm else None

    async def save(self, session: Session) -> None:
        orm = domain_to_orm_session(session)
        await self._session.merge(orm)

    async def delete(self, session_id: SessionId) -> bool:
        stmt = delete(SessionORM).where(SessionORM.id == str(session_id))
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        stmt = select(SessionORM).order_by(SessionORM.created_at.desc()).limit(limit).offset(offset)
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [orm_to_domain_session(o) for o in orms]


class SqlTaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, task_id: TaskId) -> Optional[Task]:
        stmt = select(TaskORM).where(TaskORM.id == str(task_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return orm_to_domain_task(orm) if orm else None

    async def save(self, task: Task) -> None:
        orm = domain_to_orm_task(task)
        await self._session.merge(orm)

    async def list_by_session(self, session_id: SessionId) -> List[Task]:
        stmt = select(TaskORM).where(TaskORM.session_id == str(session_id)).order_by(TaskORM.created_at.asc())
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [orm_to_domain_task(o) for o in orms]


class SqlWorkflowRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, run_id: RunId) -> Optional[WorkflowRun]:
        stmt = select(WorkflowRunORM).where(WorkflowRunORM.run_id == str(run_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return orm_to_domain_workflow(orm) if orm else None

    async def save(self, run: WorkflowRun) -> None:
        orm = domain_to_orm_workflow(run)
        await self._session.merge(orm)


class SqlEventStore:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def append_event(self, event: EventEnvelope) -> None:
        orm = domain_to_orm_event(event)
        self._session.add(orm)

    async def get_events(self, session_id: SessionId, after_sequence: int = 0, limit: int = 100) -> List[EventEnvelope]:
        stmt = (
            select(ExecutionEventORM)
            .where(ExecutionEventORM.session_id == str(session_id))
            .where(ExecutionEventORM.event_seq > after_sequence)
            .order_by(ExecutionEventORM.event_seq.asc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        orms = res.scalars().all()
        return [orm_to_domain_event(o) for o in orms]


class FileArtifactRepository:
    def __init__(self, session: AsyncSession, storage_dir: str = "artifacts"):
        self._session = session
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def store(self, name: str, data: bytes, mime_type: str) -> ArtifactRef:
        aid = ArtifactId.generate()
        file_path = self.storage_dir / f"{aid}_{name}"
        file_path.write_bytes(data)

        ref = ArtifactRef(
            id=aid,
            name=name,
            mime_type=mime_type,
            uri=str(file_path.resolve()),
            size_bytes=len(data),
        )
        orm = domain_to_orm_artifact(ref)
        self._session.add(orm)
        return ref

    async def get_by_id(self, artifact_id: ArtifactId) -> Optional[ArtifactRef]:
        stmt = select(ArtifactRefORM).where(ArtifactRefORM.id == str(artifact_id))
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return orm_to_domain_artifact(orm) if orm else None


class SqlProviderConfigurationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def set_config(self, provider_name: str, enabled: bool, config: Dict[str, Any]) -> None:
        stmt = select(ProviderConfigORM).where(ProviderConfigORM.provider_name == provider_name)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        
        cfg_json = json.dumps(config)
        if orm:
            orm.enabled = enabled
            orm.config_json = cfg_json
        else:
            orm = ProviderConfigORM(
                id=provider_name,
                provider_name=provider_name,
                enabled=enabled,
                config_json=cfg_json,
            )
            self._session.add(orm)

    async def get_config(self, provider_name: str) -> Optional[Dict[str, Any]]:
        stmt = select(ProviderConfigORM).where(ProviderConfigORM.provider_name == provider_name)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if orm and orm.config_json:
            return json.loads(orm.config_json)
        return None
