"""Read-only shadow orchestration comparisons.

The runner accepts a durable primary-plan snapshot and calls a planner that has
no runtime, tool, or dispatcher capability.  It records fingerprints only, so
comparison records cannot become another persistence path for prompts or tools.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ShadowComparison:
    operation_name: str
    primary_fingerprint: str
    shadow_fingerprint: str
    matched: bool


class ShadowOrchestrationRunner:
    """Compare plan intent without dispatching an agent or a tool."""

    def __init__(self, telemetry: Any | None = None) -> None:
        self._telemetry = telemetry

    def compare_plan(
        self,
        operation_name: str,
        primary_plan: Mapping[str, Any],
        shadow_planner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> ShadowComparison:
        if not operation_name.strip():
            raise ValueError("operation_name must not be empty")
        primary = _fingerprint(primary_plan)
        shadow = _fingerprint(shadow_planner(dict(primary_plan)))
        comparison = ShadowComparison(
            operation_name=operation_name,
            primary_fingerprint=primary,
            shadow_fingerprint=shadow,
            matched=primary == shadow,
        )
        if self._telemetry is not None:
            self._telemetry.record_shadow_comparison(matched=comparison.matched)
        return comparison


def _fingerprint(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
