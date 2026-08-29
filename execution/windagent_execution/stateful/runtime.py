from __future__ import annotations
import asyncio
import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from windagent_core.errors.exceptions import DomainError, NotFoundError
from .host_guard import assert_host_authority_isolation
from .types import Checkpoint, InspectResult, SessionDescriptor, StatefulCheckpointKind, StatefulExecuteRequest, StatefulExecuteResult, StatefulSessionStatus
@runtime_checkable
class StatefulExecutionRuntime(Protocol):
    async def create_session(self, *, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, runtime_kind: str = "v1", owner_id: Optional[str] = None) -> SessionDescriptor: ...
    async def attach_session(self, session_id: str) -> SessionDescriptor: ...
    async def execute(self, session_id: str, request: StatefulExecuteRequest) -> StatefulExecuteResult: ...
    async def checkpoint(self, session_id: str, *, kind: StatefulCheckpointKind = StatefulCheckpointKind.MANUAL) -> Checkpoint: ...
    async def restore(self, checkpoint_id: str) -> SessionDescriptor: ...
    async def inspect(self, session_id: str) -> InspectResult: ...
    async def cancel(self, session_id: str) -> SessionDescriptor: ...
    async def terminate(self, session_id: str) -> SessionDescriptor: ...
class InMemoryStatefulRuntimeBase:
    def __init__(self, *, runtime_kind: str = "v1", backing_store: Optional[Dict[str, Any]] = None, sandbox=None, stream_manager=None, worktree_manager=None) -> None:
        self._runtime_kind = runtime_kind
        if backing_store is None:
            backing_store = {"sessions": {}, "states": {}, "checkpoints": {}, "history": {}}
        for k in ("sessions", "states", "checkpoints", "history"):
            backing_store.setdefault(k, {})
        self._store = backing_store
        self._sessions: Dict[str, SessionDescriptor] = self._store["sessions"]
        self._states: Dict[str, Dict[str, Any]] = self._store["states"]
        self._checkpoints: Dict[str, Checkpoint] = self._store["checkpoints"]
        self._history: Dict[str, List[Dict[str, Any]]] = self._store["history"]
        self._seq_by_session: Dict[str, int] = {}
        for cp in self._checkpoints.values():
            self._seq_by_session[cp.session_id] = max(self._seq_by_session.get(cp.session_id, 0), cp.sequence)
        self._locks: Dict[str, asyncio.Lock] = {}
        self.sandbox = sandbox
        self.stream_manager = stream_manager
        self.worktree_manager = worktree_manager
    async def create_session(self, *, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, runtime_kind: Optional[str] = None, owner_id: Optional[str] = None) -> SessionDescriptor:
        assert_host_authority_isolation(metadata=metadata)
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        if sid in self._sessions:
            raise DomainError(message=f"Session already exists: {sid}", code="WINDAGENT_ERR_SESSION_EXISTS", details={"session_id": sid})
        now = datetime.now(timezone.utc)
        kind = runtime_kind or self._runtime_kind
        desc = SessionDescriptor(session_id=sid, status=StatefulSessionStatus.ACTIVE, created_at=now, updated_at=now, runtime_kind=kind, fencing_token=f"fence_{uuid.uuid4().hex[:12]}", metadata=copy.deepcopy(metadata or {}), owner_id=owner_id, execution_count=0, checkpoint_count=0)
        self._sessions[sid] = desc
        self._states[sid] = {}
        self._history[sid] = []
        self._seq_by_session[sid] = 0
        return desc
    async def attach_session(self, session_id: str) -> SessionDescriptor:
        desc = self._sessions.get(session_id)
        if desc is None:
            raise NotFoundError(message=f"Session not found: {session_id}", details={"session_id": session_id})
        if desc.status == StatefulSessionStatus.TERMINATED:
            raise DomainError(message=f"Cannot attach terminated session: {session_id}", code="WINDAGENT_ERR_SESSION_TERMINATED", details={"session_id": session_id})
        if desc.status == StatefulSessionStatus.CANCELLED:
            raise DomainError(message=f"Cannot attach cancelled session: {session_id}", code="WINDAGENT_ERR_SESSION_CANCELLED", details={"session_id": session_id})
        return desc
    async def execute(self, session_id: str, request: StatefulExecuteRequest) -> StatefulExecuteResult:
        assert_host_authority_isolation(parameters=request.parameters, code=request.code)
        desc = self._sessions.get(session_id)
        if desc is None:
            raise NotFoundError(message=f"Session not found: {session_id}", details={"session_id": session_id})
        if desc.status in (StatefulSessionStatus.TERMINATED, StatefulSessionStatus.CANCELLED):
            raise DomainError(message=f"Cannot execute on {desc.status.value} session: {session_id}", code="WINDAGENT_ERR_SESSION_NOT_EXECUTABLE", details={"session_id": session_id, "status": desc.status.value})
        await self._update_status(session_id, StatefulSessionStatus.RUNNING)
        started = datetime.now(timezone.utc)
        result = await self._do_execute(session_id, request, started)
        finished = datetime.now(timezone.utc)
        self._history[session_id].append({"execution_id": request.execution_id, "request": request.to_dict(), "result": {"status": result.status, "output": result.output, "error": result.error}, "started_at": started.isoformat(), "finished_at": finished.isoformat()})
        current = self._sessions[session_id]
        if current.status == StatefulSessionStatus.RUNNING:
            await self._update_status(session_id, StatefulSessionStatus.ACTIVE, increment_execution=True)
        else:
            await self._update_status(session_id, current.status, increment_execution=True)
        return StatefulExecuteResult(session_id=session_id, execution_id=request.execution_id, status=result.status, output=result.output, error=result.error, started_at=started, finished_at=finished)
    async def _do_execute(self, session_id: str, request: StatefulExecuteRequest, started: datetime) -> StatefulExecuteResult:
        state = self._states[session_id]
        try:
            if request.code is not None:
                local_ns: Dict[str, Any] = {}
                exec_globals = dict(state)
                import io
                import contextlib
                buf = io.StringIO()
                safe_builtins = {"print": lambda *a, **kw: print(*a, file=buf, **kw), "len": len, "range": range, "str": str, "int": int, "float": float, "dict": dict, "list": list, "sum": sum, "min": min, "max": max}
                exec_globals["__builtins__"] = safe_builtins
                with contextlib.redirect_stdout(buf):
                    exec(request.code, exec_globals, local_ns)
                for k, v in exec_globals.items():
                    if k == "__builtins__":
                        continue
                    state[k] = v
                for k, v in local_ns.items():
                    state[k] = v
                out = buf.getvalue()
                output: Dict[str, Any] = {"stdout": out, "state_keys": list(state.keys())}
                if request.parameters:
                    output["parameters"] = copy.deepcopy(request.parameters)
                return StatefulExecuteResult(session_id=session_id, execution_id=request.execution_id, status="completed", output=output, started_at=started, finished_at=datetime.now(timezone.utc))
            elif request.tool_name:
                return StatefulExecuteResult(session_id=session_id, execution_id=request.execution_id, status="completed", output={"tool": request.tool_name, "params": copy.deepcopy(request.parameters), "state_keys": list(state.keys())}, started_at=started, finished_at=datetime.now(timezone.utc))
            else:
                return StatefulExecuteResult(session_id=session_id, execution_id=request.execution_id, status="failed", error="No code or tool_name provided", started_at=started, finished_at=datetime.now(timezone.utc))
        except Exception as ex:
            return StatefulExecuteResult(session_id=session_id, execution_id=request.execution_id, status="failed", error=str(ex), started_at=started, finished_at=datetime.now(timezone.utc))
    async def checkpoint(self, session_id: str, *, kind: StatefulCheckpointKind = StatefulCheckpointKind.MANUAL) -> Checkpoint:
        desc = self._sessions.get(session_id)
        if desc is None:
            raise NotFoundError(message=f"Session not found: {session_id}", details={"session_id": session_id})
        if desc.status in (StatefulSessionStatus.TERMINATED, StatefulSessionStatus.CANCELLED):
            raise DomainError(message=f"Cannot checkpoint {desc.status.value} session: {session_id}", code="WINDAGENT_ERR_SESSION_NOT_CHECKPOINTABLE", details={"session_id": session_id, "status": desc.status.value})
        seq = self._seq_by_session.get(session_id, 0) + 1
        self._seq_by_session[session_id] = seq
        cp_id = f"ckpt_{uuid.uuid4().hex[:12]}"
        snap = copy.deepcopy(self._states[session_id])
        cp = Checkpoint(checkpoint_id=cp_id, session_id=session_id, created_at=datetime.now(timezone.utc), sequence=seq, kind=kind, state_snapshot=snap, execution_count_at_checkpoint=desc.execution_count)
        self._checkpoints[cp_id] = cp
        await self._update_status(session_id, desc.status, increment_checkpoint=True)
        return cp
    async def restore(self, checkpoint_id: str) -> SessionDescriptor:
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise NotFoundError(message=f"Checkpoint not found: {checkpoint_id}", details={"checkpoint_id": checkpoint_id})
        sid = cp.session_id
        desc = self._sessions.get(sid)
        if desc is None:
            raise NotFoundError(message=f"Session for checkpoint not found: {sid}", details={"session_id": sid})
        if desc.status == StatefulSessionStatus.TERMINATED:
            raise DomainError(message=f"Cannot restore terminated session: {sid}", code="WINDAGENT_ERR_SESSION_TERMINATED", details={"session_id": sid})
        self._states[sid] = copy.deepcopy(cp.state_snapshot)
        now = datetime.now(timezone.utc)
        restored = SessionDescriptor(session_id=desc.session_id, status=StatefulSessionStatus.ACTIVE, created_at=desc.created_at, updated_at=now, runtime_kind=desc.runtime_kind, fencing_token=desc.fencing_token, metadata=copy.deepcopy(desc.metadata), owner_id=desc.owner_id, execution_count=cp.execution_count_at_checkpoint, checkpoint_count=desc.checkpoint_count)
        self._sessions[sid] = restored
        self._history[sid].append({"restored_from": checkpoint_id, "at": now.isoformat(), "sequence": cp.sequence})
        return restored
    async def inspect(self, session_id: str) -> InspectResult:
        desc = self._sessions.get(session_id)
        if desc is None:
            raise NotFoundError(message=f"Session not found: {session_id}", details={"session_id": session_id})
        state = copy.deepcopy(self._states.get(session_id, {}))
        hist = copy.deepcopy(self._history.get(session_id, []))
        cps = [cid for cid, cp in self._checkpoints.items() if cp.session_id == session_id]
        cps_sorted = sorted(cps, key=lambda cid: self._checkpoints[cid].sequence)
        return InspectResult(session_id=session_id, status=desc.status, state_vars=state, history=hist, checkpoint_ids=cps_sorted, fencing_token=desc.fencing_token, runtime_kind=desc.runtime_kind, created_at=desc.created_at, updated_at=desc.updated_at)
    async def cancel(self, session_id: str) -> SessionDescriptor:
        desc = self._sessions.get(session_id)
        if desc is None:
            raise NotFoundError(message=f"Session not found: {session_id}", details={"session_id": session_id})
        if desc.status == StatefulSessionStatus.TERMINATED:
            raise DomainError(message=f"Cannot cancel terminated session: {session_id}", code="WINDAGENT_ERR_SESSION_TERMINATED", details={"session_id": session_id})
        if desc.status == StatefulSessionStatus.CANCELLED:
            return desc
        return await self._update_status(session_id, StatefulSessionStatus.CANCELLED)
    async def terminate(self, session_id: str) -> SessionDescriptor:
        desc = self._sessions.get(session_id)
        if desc is None:
            raise NotFoundError(message=f"Session not found: {session_id}", details={"session_id": session_id})
        if desc.status == StatefulSessionStatus.TERMINATED:
            return desc
        result = await self._update_status(session_id, StatefulSessionStatus.TERMINATED)
        return result
    async def _update_status(self, session_id: str, new_status: StatefulSessionStatus, *, increment_execution: bool = False, increment_checkpoint: bool = False) -> SessionDescriptor:
        desc = self._sessions[session_id]
        now = datetime.now(timezone.utc)
        updated = SessionDescriptor(session_id=desc.session_id, status=new_status, created_at=desc.created_at, updated_at=now, runtime_kind=desc.runtime_kind, fencing_token=desc.fencing_token, metadata=copy.deepcopy(desc.metadata), owner_id=desc.owner_id, execution_count=desc.execution_count + (1 if increment_execution else 0), checkpoint_count=desc.checkpoint_count + (1 if increment_checkpoint else 0))
        self._sessions[session_id] = updated
        return updated
