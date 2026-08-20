"""Result validation stage for the Production Worker pipeline (Architecture V3 Phase 9).

Fencing validation plus ``StudioTaskResult`` contract validation.  Returns a
typed proposed terminal outcome.  A late/mismatched result reports a fencing
rejection and is never finalized.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from windagent_core.contracts.execution import RuntimeStatusEnum
from windagent_core.errors.exceptions import DomainError
from windagent_execution.results import ExecutionResultHandler

from windagent_worker.pipeline.context import TaskExecutionContext


@dataclass
class ProposedOutcome:
    """Typed proposed terminal outcome produced by the validation stage."""

    terminal_state: str = "failed"
    terminal_error: Optional[str] = None
    result_payload: Dict[str, Any] = field(default_factory=dict)
    studio_result: Optional[Any] = None
    fencing_rejected: bool = False
    rejection_error: Optional[str] = None


class ResultValidatorStage:
    """Fencing + Studio contract validation; never finalizes anything."""

    async def validate(self, ctx: TaskExecutionContext) -> ProposedOutcome:
        """Validate the execution result and propose a terminal outcome.

        A fencing mismatch (late result after lease takeover) returns a
        ``ProposedOutcome`` with ``fencing_rejected=True``; the pipeline must
        release the lease and never call the finalizer.
        """
        try:
            validated_result = ExecutionResultHandler.validate_and_wrap(
                result=ctx.result,
                active_fencing_token=ctx.fencing_token,
                result_fencing_token=ctx.handle.fencing_token,
            )
        except DomainError as err:
            return ProposedOutcome(fencing_rejected=True, rejection_error=str(err))

        result_payload = dict(validated_result.result_data or {})
        terminal_state = (
            "completed"
            if validated_result.status == RuntimeStatusEnum.COMPLETED
            else "failed"
        )
        terminal_error = validated_result.error
        studio_result = None
        if ctx.parameters.get("studio_envelope"):
            try:
                from windagent_core.contracts.studio.models import (
                    StudioTaskResult,
                    StudioTaskStatus,
                )

                studio_result = StudioTaskResult.model_validate(result_payload)
                if studio_result.status != StudioTaskStatus.SUCCEEDED:
                    terminal_state = "failed"
                    terminal_error = studio_result.error
            except Exception as ex:
                terminal_state = "failed"
                terminal_error = (
                    "STUDIO_RESULT_INVALID: successful Studio finalization requires "
                    f"StudioTaskResult ({type(ex).__name__})"
                )
                result_payload = {
                    "error_code": "STUDIO_RESULT_INVALID",
                    "error": terminal_error,
                    "task_id": ctx.task_id,
                }

        return ProposedOutcome(
            terminal_state=terminal_state,
            terminal_error=terminal_error,
            result_payload=result_payload,
            studio_result=studio_result,
        )


__all__ = ["ProposedOutcome", "ResultValidatorStage"]