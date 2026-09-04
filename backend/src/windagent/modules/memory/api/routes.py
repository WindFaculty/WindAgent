"""HTTP surface of the Memory bounded context (mounted under /api/v4)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field

from windagent.kernel.time import utc_now
from windagent.platform.observability import current_operation_context
from windagent.platform.security import (
    AuditEvent,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
)

from ..application import queries as app_queries
from ..application.commands import (
    DeleteMemory,
    EvictExpiredMemories,
    ForgetMemoryByPattern,
    SaveManyMemories,
    SaveMemory,
    SetMemoryTtl,
)
from ..application.runtime import MemoryServices, bind_services
from ..infrastructure.repository import sql_scope_factory

MODULE_ID = "memory"
MODULE_VERSION = "1.0.0"
PREFIX = "/memory"

POLICY_UNCONFIGURED_POLICY_ID = "policy-unconfigured"
PRINCIPAL_ATTR = "windagent_principal"

READ_ACTION = "memory.read"
WRITE_ACTION = "memory.write"
RESOURCE_TYPE = "memory"


# --------------------------------------------------------------------------- #
# DTOs
# --------------------------------------------------------------------------- #


class SaveMemoryIn(BaseModel):
    key: str = Field(min_length=1, max_length=256)
    value: Any
    scope: str = Field(default="working")
    provenance_source: str = Field(default="unknown")
    project_id: str | None = None
    session_id: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    ttl_seconds: int | None = Field(default=None, ge=0)
    learning_metadata: dict[str, Any] | None = None
    expected_version: int | None = Field(default=None, ge=1)
    memory_id: str | None = None


class BatchRecordItem(BaseModel):
    key: str = Field(min_length=1, max_length=256)
    value: Any
    scope: str = Field(default="working")
    provenance_source: str = Field(default="unknown")
    project_id: str | None = None
    session_id: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    ttl_seconds: int | None = Field(default=None, ge=0)
    learning_metadata: dict[str, Any] | None = None
    expected_version: int | None = Field(default=None, ge=1)
    memory_id: str | None = None


class SaveManyMemoriesIn(BaseModel):
    records: list[BatchRecordItem]


class DeleteMemoryIn(BaseModel):
    scope: str = Field(max_length=32)
    key: str = Field(max_length=256)
    project_id: str | None = None
    session_id: str | None = None


class ForgetPatternIn(BaseModel):
    scope: str
    key_prefix: str
    project_id: str | None = None
    session_id: str | None = None


class SetMemoryTtlIn(BaseModel):
    scope: str
    key: str
    ttl_seconds: int = Field(ge=0)
    project_id: str | None = None
    session_id: str | None = None


class EvictExpiredIn(BaseModel):
    scope: str | None = None


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #


def _principal_actor_id(request: Request) -> object | None:
    principal = getattr(request.state, PRINCIPAL_ATTR, None)
    if principal is None:
        return None
    return getattr(principal, "actor_id", None)


async def _check_permission(
    request: Request,
    action: str,
    resource_type: str = RESOURCE_TYPE,
) -> PolicyDecision:
    engine = getattr(request.app.state, "policy_engine", None)
    if engine is None:
        return PolicyDecision(
            effect=PolicyEffect.ALLOW,
            reason="no policy engine is configured",
            policy_id=POLICY_UNCONFIGURED_POLICY_ID,
        )
    decision = await cast(PolicyEngine, engine).decide(
        PolicyRequest(
            action=action,
            resource_type=resource_type,
            actor_id=_principal_actor_id(request),  # type: ignore[arg-type]
        )
    )
    await _record_audit(request, decision, action, resource_type)
    if decision.effect is not PolicyEffect.ALLOW:
        from windagent.kernel.errors import DomainError

        raise DomainError(
            decision.reason or "denied by policy",
            code="forbidden",
            context={"policy_id": decision.policy_id},
        )
    return decision


async def _record_audit(
    request: Request,
    decision: PolicyDecision,
    action: str,
    resource_type: str,
) -> None:
    sink = getattr(request.app.state, "audit_sink", None)
    if sink is None:
        return
    operation = current_operation_context()
    await sink.record(
        AuditEvent(
            action=action,
            resource_type=resource_type,
            outcome=decision.effect.value,
            actor_id=_principal_actor_id(request),  # type: ignore[arg-type]
            correlation_id=operation.correlation_id if operation else None,
            causation_id=operation.causation_id if operation else None,
            trace_id=operation.trace_id if operation else None,
            reason=decision.reason,
            details={"policy_id": decision.policy_id} if decision.policy_id else {},
            occurred_at=utc_now(),
        )
    )


# --------------------------------------------------------------------------- #
# Dependencies
# --------------------------------------------------------------------------- #


async def _runtime_services(request: Request) -> AsyncIterator[MemoryServices]:
    override = getattr(request.app.state, "memory_services_override", None)
    if override is not None:
        with bind_services(override):
            yield override
        return

    db = getattr(request.app.state, "database", None)
    if db is None:
        from ..infrastructure.memory import memory_scope_factory

        services = MemoryServices(scope_factory=memory_scope_factory())
    else:
        services = MemoryServices(scope_factory=sql_scope_factory(db))

    with bind_services(services):
        yield services


# --------------------------------------------------------------------------- #
# Router factory
# --------------------------------------------------------------------------- #


def create_memory_router() -> APIRouter:
    router = APIRouter(prefix=PREFIX, tags=["memory"])

    # -- Commands ------------------------------------------------------------

    @router.post("")
    async def save_memory(
        body: SaveMemoryIn,
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, WRITE_ACTION)
        cb: Callable[[Any], Awaitable[Any]] = request.app.state.command_bus.dispatch
        cmd = SaveMemory(
            key=body.key,
            value=body.value,
            scope=body.scope,
            provenance_source=body.provenance_source,
            project_id=body.project_id,
            session_id=body.session_id,
            tags=body.tags,
            ttl_seconds=body.ttl_seconds,
            learning_metadata=body.learning_metadata or {},
            expected_version=body.expected_version,
            memory_id=body.memory_id,
        )
        view = await cb(cmd)
        return {"data": view.to_payload()}

    @router.post("/batch")
    async def save_many_memories(
        body: SaveManyMemoriesIn,
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, WRITE_ACTION)
        cb: Callable[[Any], Awaitable[Any]] = request.app.state.command_bus.dispatch
        raw_records = [r.model_dump() for r in body.records]
        cmd = SaveManyMemories(records=raw_records)
        views = await cb(cmd)
        return {"data": [v.to_payload() for v in views]}

    @router.delete("")
    async def delete_memory(
        scope: str,
        key: str,
        request: Request,
        project_id: str | None = None,
        session_id: str | None = None,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, WRITE_ACTION)
        cb: Callable[[Any], Awaitable[Any]] = request.app.state.command_bus.dispatch
        cmd = DeleteMemory(
            scope=scope,
            key=key,
            project_id=project_id,
            session_id=session_id,
        )
        success = await cb(cmd)
        return {"deleted": bool(success)}

    @router.post("/forget-pattern")
    async def forget_pattern(
        body: ForgetPatternIn,
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, WRITE_ACTION)
        cb: Callable[[Any], Awaitable[Any]] = request.app.state.command_bus.dispatch
        cmd = ForgetMemoryByPattern(
            scope=body.scope,
            key_prefix=body.key_prefix,
            project_id=body.project_id,
            session_id=body.session_id,
        )
        count = await cb(cmd)
        return {"forgotten_count": count}

    @router.post("/ttl")
    async def set_ttl(
        body: SetMemoryTtlIn,
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, WRITE_ACTION)
        cb: Callable[[Any], Awaitable[Any]] = request.app.state.command_bus.dispatch
        cmd = SetMemoryTtl(
            scope=body.scope,
            key=body.key,
            ttl_seconds=body.ttl_seconds,
            project_id=body.project_id,
            session_id=body.session_id,
        )
        success = await cb(cmd)
        return {"success": bool(success)}

    @router.post("/evict")
    async def evict_expired(
        body: EvictExpiredIn,
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, WRITE_ACTION)
        cb: Callable[[Any], Awaitable[Any]] = request.app.state.command_bus.dispatch
        cmd = EvictExpiredMemories(scope=body.scope)
        count = await cb(cmd)
        return {"evicted_count": count}

    # -- Queries -------------------------------------------------------------

    @router.get("/stats")
    async def get_stats(
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        view = await qb(app_queries.GetMemoryStats())
        return {"data": view.to_payload()}

    @router.get("/lookup")
    async def lookup_memory(
        scope: str,
        key: str,
        request: Request,
        project_id: str | None = None,
        session_id: str | None = None,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        view = await qb(
            app_queries.GetMemory(
                scope=scope,
                key=key,
                project_id=project_id,
                session_id=session_id,
            )
        )
        return {"data": view.to_payload() if view is not None else None}

    @router.get("/validated")
    async def list_validated(
        request: Request,
        scope: str | None = None,
        min_confidence: float = QueryParam(0.0, ge=0.0, le=1.0),
        project_id: str | None = None,
        limit: int = QueryParam(100, ge=1, le=500),
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        views = await qb(
            app_queries.ListValidatedKnowledge(
                scope=scope,
                min_confidence=min_confidence,
                project_id=project_id,
                limit=limit,
            )
        )
        return {"data": [v.to_payload() for v in views]}

    @router.get("/policies")
    async def list_policies(
        request: Request,
        validated_only: bool = True,
        project_id: str | None = None,
        limit: int = QueryParam(100, ge=1, le=500),
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        views = await qb(
            app_queries.ListPolicies(
                validated_only=validated_only,
                project_id=project_id,
                limit=limit,
            )
        )
        return {"data": [v.to_payload() for v in views]}

    @router.get("/procedural")
    async def list_procedural(
        request: Request,
        project_id: str | None = None,
        limit: int = QueryParam(100, ge=1, le=500),
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        views = await qb(
            app_queries.ListProceduralMemories(
                project_id=project_id,
                limit=limit,
            )
        )
        return {"data": [v.to_payload() for v in views]}

    @router.get("/episodic")
    async def list_episodic(
        request: Request,
        session_id: str | None = None,
        limit: int = QueryParam(100, ge=1, le=500),
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        views = await qb(
            app_queries.ListEpisodicMemories(
                session_id=session_id,
                limit=limit,
            )
        )
        return {"data": [v.to_payload() for v in views]}

    @router.get("/search-tag")
    async def search_by_tag(
        tag_key: str,
        tag_value: str,
        request: Request,
        scope: str | None = None,
        limit: int = QueryParam(100, ge=1, le=500),
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        views = await qb(
            app_queries.SearchMemoriesByTag(
                tag_key=tag_key,
                tag_value=tag_value,
                scope=scope,
                limit=limit,
            )
        )
        return {"data": [v.to_payload() for v in views]}

    @router.get("/{id}")
    async def get_by_id(
        id: str,
        request: Request,
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        view = await qb(app_queries.GetMemoryById(memory_id=id))
        return {"data": view.to_payload() if view is not None else None}

    @router.get("")
    async def list_memories(
        request: Request,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = QueryParam(100, ge=1, le=500),
        offset: int = QueryParam(0, ge=0),
        _services: MemoryServices = Depends(_runtime_services),
    ) -> dict[str, Any]:
        await _check_permission(request, READ_ACTION)
        qb: Callable[[Any], Awaitable[Any]] = request.app.state.query_bus.ask
        views = await qb(
            app_queries.ListMemories(
                scope=scope,
                project_id=project_id,
                session_id=session_id,
                limit=limit,
                offset=offset,
            )
        )
        return {"data": [v.to_payload() for v in views]}

    return router
