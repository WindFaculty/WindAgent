"""Controllable external-boundary doubles for Phase 8 integration scenarios.

These fakes model the two external execution boundaries.  The orchestrator,
repository, scheduler, recovery manager and provider coordinator remain real.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable
from uuid import uuid4

from windagent_core.contracts.execution import (
    ExecutionHandle,
    ExecutionRequest,
    ExecutionResult,
    ExecutionRuntimePort,
    RuntimeStatus,
    RuntimeStatusEnum,
)


class ControlledHermesRuntime(ExecutionRuntimePort):
    """Hermes-like runtime whose runs can complete, fail, cancel or crash on demand."""

    def __init__(self) -> None:
        self.handles: dict[str, ExecutionHandle] = {}
        self.requests: list[ExecutionRequest] = []
        self.cancelled: list[str] = []
        self._statuses: dict[str, RuntimeStatusEnum] = {}
        self._results: dict[str, ExecutionResult] = {}
        self._crashed: set[str] = set()

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        runtime_run_id = f"hermes-{uuid4().hex}"
        handle = ExecutionHandle(
            handle_id=f"handle-{uuid4().hex}",
            runtime_run_id=runtime_run_id,
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token,
            runtime_session_id=request.workflow_run_id,
        )
        self.requests.append(request)
        self.handles[runtime_run_id] = handle
        self._statuses[runtime_run_id] = RuntimeStatusEnum.RUNNING
        return handle

    def complete(self, runtime_run_id: str, result: dict[str, Any] | None = None) -> None:
        self._set_terminal(runtime_run_id, RuntimeStatusEnum.COMPLETED, result_data=result or {})

    def fail(self, runtime_run_id: str, error: str = "scripted Hermes failure") -> None:
        self._set_terminal(runtime_run_id, RuntimeStatusEnum.FAILED, error=error)

    def crash(self, runtime_run_id: str) -> None:
        """Make status lost and deliberately refuse a later reattach."""
        self._crashed.add(runtime_run_id)
        self._set_terminal(
            runtime_run_id,
            RuntimeStatusEnum.LOST,
            error="scripted Hermes runtime crash",
        )

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        return RuntimeStatus(
            handle_id=handle.handle_id,
            status=self._statuses.get(handle.runtime_run_id, RuntimeStatusEnum.UNKNOWN),
        )

    async def cancel(self, handle: ExecutionHandle) -> None:
        self.cancelled.append(handle.runtime_run_id)
        self._set_terminal(
            handle.runtime_run_id,
            RuntimeStatusEnum.CANCELLED,
            error="cancelled by orchestrator",
        )

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        return self._results.get(
            handle.runtime_run_id,
            ExecutionResult(
                handle_id=handle.handle_id,
                step_run_id=handle.step_run_id,
                status=self._statuses.get(handle.runtime_run_id, RuntimeStatusEnum.UNKNOWN),
            ),
        )

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        return None if runtime_run_id in self._crashed else self.handles.get(runtime_run_id)

    def _set_terminal(
        self,
        runtime_run_id: str,
        status: RuntimeStatusEnum,
        *,
        result_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        handle = self.handles[runtime_run_id]
        self._statuses[runtime_run_id] = status
        self._results[runtime_run_id] = ExecutionResult(
            handle_id=handle.handle_id,
            step_run_id=handle.step_run_id,
            status=status,
            result_data=result_data,
            error=error,
        )


class ScriptedProviderAdapter:
    """Provider double which consumes a response/error script one request at a time."""

    def __init__(self, outcomes: Iterable[Any]) -> None:
        self._outcomes = deque(outcomes)
        self.calls = 0

    async def generate(self, *_: Any, **__: Any) -> Any:
        self.calls += 1
        if not self._outcomes:
            raise AssertionError("provider script exhausted")
        outcome = self._outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
