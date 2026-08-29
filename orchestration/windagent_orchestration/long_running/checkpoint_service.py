"""Durable checkpoint service — all mandated Phase 5 boundaries (Phase 5).

Creates opaque JSON-serializable checkpoints atomically within the caller
session's UoW. Snapshot is deep-copied and host-authority stripped on write
and on read. Sequence is deterministic (per-agent count within transaction).
Every checkpoint carries fencing_token + loop_version for stale-write
protection. Orchestrator remains the authority; this service only persists
the observation.

Boundaries (§10): turn_boundary, tool_boundary, child_admission,
child_completion, compaction, external_wait, terminal_state plus
manual/auto. Caller selects explicit kind.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Mapping

from windagent_core.domain.durable_checkpoint import (
    CheckpointKind,
    assert_no_host_authority,
    ensure_json_serializable,
    sanitize_snapshot,
)


def _new_id(prefix: str = "ckpt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class CheckpointError(RuntimeError):
    pass


_VALID_KINDS = {k.value for k in CheckpointKind}


class CheckpointService:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        checkpoint_repo_factory: Callable[[Any], Any],
        multi_repo_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._checkpoint_repo_factory = checkpoint_repo_factory
        self._multi_repo_factory = multi_repo_factory

    def _checkpoint_repo(self, session: Any) -> Any:
        return self._checkpoint_repo_factory(session)

    def _multi_repo(self, session: Any) -> Any | None:
        if self._multi_repo_factory is not None:
            return self._multi_repo_factory(session)
        return None

    def _validate_kind(self, kind: str) -> CheckpointKind:
        kv = str(kind).strip().lower()
        if kv not in _VALID_KINDS:
            raise CheckpointError(f"unknown checkpoint kind '{kind}'; expected one of {sorted(_VALID_KINDS)}")
        return CheckpointKind(kv)

    def _validate_snapshot(self, snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
        snap = dict(snapshot or {})
        assert_no_host_authority(snap, "checkpoint snapshot")
        cleaned = sanitize_snapshot(snap)
        ensure_json_serializable(cleaned, "checkpoint snapshot")
        # also ensure deep-copy immutability at service layer: never store caller-owned ref
        return dict(cleaned)

    async def checkpoint(
        self,
        *,
        agent_run_id: str,
        kind: str,
        snapshot: Mapping[str, Any] | None = None,
        checkpoint_id: str | None = None,
        session_id: str | None = None,
        step_run_id: str | None = None,
        tool_name: str | None = None,
        fencing_token: str | None = None,
    ) -> dict[str, Any]:
        agent_run_id = str(agent_run_id).strip()
        if not agent_run_id:
            raise CheckpointError("agent_run_id must not be empty")
        ck_kind = self._validate_kind(kind)
        snap = self._validate_snapshot(snapshot)
        cid = str(checkpoint_id or _new_id("ckpt")).strip()
        async with self._session_factory() as session:
            repo = self._checkpoint_repo(session)
            multi = self._multi_repo(session)
            row = await repo.create_checkpoint(
                checkpoint_id=cid,
                agent_run_id=agent_run_id,
                kind=ck_kind.value,
                snapshot=snap,
                session_id=session_id,
                step_run_id=step_run_id,
                tool_name=tool_name,
                fencing_token=fencing_token or "",
            )
            if multi is not None:
                try:
                    # best-effort durable event for trajectory correlation
                    conv_id = None
                    try:
                        if hasattr(multi, "conversation_id_for_agent"):
                            conv_id = await multi.conversation_id_for_agent(agent_run_id)
                    except Exception:
                        conv_id = None
                    if conv_id:
                        await multi.append_event(
                            event_id=str(uuid.uuid4()),
                            conversation_id=str(conv_id),
                            event_type=f"agent_checkpoint_{ck_kind.value}",
                            data={
                                "checkpoint_id": cid,
                                "agent_run_id": agent_run_id,
                                "kind": ck_kind.value,
                                "sequence": int(row.get("sequence", 0)),
                                "step_run_id": step_run_id,
                                "tool_name": tool_name,
                            },
                            agent_instance_id=agent_run_id,
                        )
                except Exception:
                    pass
            await session.commit()
            return row

    # convenience entrypoints for each mandated boundary ---------------
    async def at_turn_boundary(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.TURN_BOUNDARY.value, snapshot=snapshot, **kw)

    async def at_tool_boundary(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, tool_name: str | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.TOOL_BOUNDARY.value, snapshot=snapshot, tool_name=tool_name, **kw)

    async def at_child_admission(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.CHILD_ADMISSION.value, snapshot=snapshot, **kw)

    async def at_child_completion(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.CHILD_COMPLETION.value, snapshot=snapshot, **kw)

    async def at_compaction(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.COMPACTION.value, snapshot=snapshot, **kw)

    async def at_external_wait(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.EXTERNAL_WAIT.value, snapshot=snapshot, **kw)

    async def at_terminal_state(self, agent_run_id: str, snapshot: Mapping[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self.checkpoint(agent_run_id=agent_run_id, kind=CheckpointKind.TERMINAL_STATE.value, snapshot=snapshot, **kw)

    async def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            repo = self._checkpoint_repo(session)
            return await repo.get_checkpoint(str(checkpoint_id))

    async def list_checkpoints(self, agent_run_id: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            repo = self._checkpoint_repo(session)
            return await repo.list_checkpoints(str(agent_run_id), kind=kind)

    async def latest_checkpoint(self, agent_run_id: str) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            repo = self._checkpoint_repo(session)
            return await repo.latest_checkpoint(str(agent_run_id))
