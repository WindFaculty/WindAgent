"""
Durable Execution Result and Fencing Token Validation for WindAgent Execution V2 (Phase 18).
Ensures late result commits with stale fencing tokens or reclaimed worker leases are strictly rejected.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.contracts.execution import RuntimeStatusEnum, ExecutionResult
from windagent_core.errors.exceptions import DomainError


@dataclass
class FencingValidatedResult:
    handle_id: str
    step_run_id: str
    fencing_token: str
    lease_generation: int
    status: RuntimeStatusEnum
    result_data: Optional[Dict[str, Any]] = None
    result_ref: Optional[str] = None
    error: Optional[str] = None
    error_metadata: Optional[Dict[str, Any]] = None
    committed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionResultHandler:
    """Validates execution results against active fencing tokens before committing to durable state."""

    @staticmethod
    def validate_and_wrap(
        result: ExecutionResult,
        active_fencing_token: str,
        result_fencing_token: str,
        lease_generation: int = 1,
    ) -> FencingValidatedResult:
        if active_fencing_token != result_fencing_token:
            raise DomainError(
                message=f"Fencing token mismatch for step [{result.step_run_id}]: expected '{active_fencing_token}', got '{result_fencing_token}'",
                code="WINDAGENT_ERR_FENCING_TOKEN_STALE",
                details={
                    "step_run_id": result.step_run_id,
                    "expected_fencing_token": active_fencing_token,
                    "provided_fencing_token": result_fencing_token,
                    "lease_generation": lease_generation,
                },
            )

        return FencingValidatedResult(
            handle_id=result.handle_id,
            step_run_id=result.step_run_id,
            fencing_token=result_fencing_token,
            lease_generation=lease_generation,
            status=result.status,
            result_data=result.result_data,
            result_ref=result.result_ref,
            error=result.error,
            error_metadata=result.error_metadata,
        )
