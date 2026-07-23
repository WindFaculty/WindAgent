"""
Shadow Execution Comparator for WindAgent Read-Only Operations (Phase 14).
Executes V1 and V2 operations in shadow mode to verify output parity before cutover.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("windagent.shadow_comparator")


@dataclass
class ParityComparisonResult:
    """Outcome of read-only shadow comparison between V1 and V2."""
    operation_name: str
    v1_result: Any
    v2_result: Any
    parity_matched: bool
    diff_details: Optional[str] = None


class ShadowExecutionEngine:
    """Executes read-only shadow comparisons to guarantee V1/V2 parity before cutover."""

    def __init__(self) -> None:
        self.comparison_history: Dict[str, ParityComparisonResult] = {}

    def compare_read_only(
        self,
        op_name: str,
        v1_fn: Callable[..., Any],
        v2_fn: Callable[..., Any],
        *args: Any,
        is_destructive: bool = False,
        **kwargs: Any
    ) -> ParityComparisonResult:
        """Runs read-only operation against V1 and V2, comparing results. Never shadows destructive operations."""
        if is_destructive:
            logger.warning(f"Shadow comparison skipped for destructive operation '{op_name}'")
            return ParityComparisonResult(
                operation_name=op_name,
                v1_result=None,
                v2_result=None,
                parity_matched=True,
                diff_details="Skipped destructive operation"
            )

        v1_res = v1_fn(*args, **kwargs)
        v2_res = v2_fn(*args, **kwargs)

        matched = v1_res == v2_res
        diff = None if matched else f"V1={v1_res} != V2={v2_res}"

        result = ParityComparisonResult(
            operation_name=op_name,
            v1_result=v1_res,
            v2_result=v2_res,
            parity_matched=matched,
            diff_details=diff
        )
        self.comparison_history[op_name] = result
        return result
