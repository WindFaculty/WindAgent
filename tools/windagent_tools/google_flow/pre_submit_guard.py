"""
Phase 14 — Pre-submit guard (plan 04 §18.1).

Before the generator ever clicks submit, `PreSubmitGuard` verifies every
condition in plan 04 §18.1:

- request schema / request hash are valid;
- references are approved and their upload hash matches the store;
- project / session mapping is healthy;
- the operation is supported by the provider capability matrix;
- the candidate limit is defined and bounded;
- cost/quota policy allows it (or an explicit test approval is granted);
- pre-submit screenshot / evidence exists.

The guard fails CLOSED: every condition must pass; a single failure returns
a typed `PreSubmitVerdict` with the blocking reasons and the generator raises
`FlowPreSubmitBlockedError` — no submit click is ever issued.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from windagent_tools.google_flow.image_operations import (
    FlowImageRequest,
    ImageOperationMapper,
)

_REQUEST_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

MAX_CANDIDATES_DEFAULT = 8
MAX_COST_CREDITS_DEFAULT = 0.0  # 0 => cost disabled unless test-approved


class PreSubmitGuardError(RuntimeError):
    """Base error for pre-submit guard failures."""


class FlowPreSubmitBlockedError(PreSubmitGuardError):
    """Raised when the guard refuses to allow a submit click."""

    def __init__(self, message: str = "", *, reasons: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.reasons = reasons


@dataclass(frozen=True)
class PreSubmitVerdict:
    """Result of the pre-submit guard (fail closed)."""

    ok: bool
    reasons: tuple[str, ...] = ()


class PreSubmitGuard:
    """Fail-closed gate before any submit click (plan 04 §18.1)."""

    def __init__(
        self,
        *,
        mapper: Optional[ImageOperationMapper] = None,
        max_candidates: int = MAX_CANDIDATES_DEFAULT,
        max_cost_credits: float = MAX_COST_CREDITS_DEFAULT,
    ) -> None:
        self.mapper = mapper or ImageOperationMapper()
        self.max_candidates = max_candidates
        self.max_cost_credits = max_cost_credits

    # ------------------------------------------------------------------
    def check(
        self,
        request: FlowImageRequest,
        *,
        mapping_healthy: bool,
        session_healthy: bool,
        references_approved: bool,
        upload_hash_matches: bool,
        pre_submit_evidence_hash: str,
        operation_supported: bool,
        cost_allowed: bool,
    ) -> PreSubmitVerdict:
        """Evaluate all §18.1 conditions; fail closed on any failure."""
        reasons: list[str] = []

        if not _REQUEST_HASH_RE.match(request.request_hash or ""):
            reasons.append("request_hash invalid (expected 64-hex sha256)")
        if not request.project_id or not request.revision_id:
            reasons.append("project_id/revision_id missing")
        if not mapping_healthy:
            reasons.append("project mapping not healthy")
        if not session_healthy:
            reasons.append("browser session not healthy")
        if not operation_supported:
            reasons.append(f"operation {request.operation.value} not supported")
        # Reference-required ops AND source-image ops (edit/upscale) consume
        # an approved asset whose upload hash must match (plan 04 §18.1).
        needs_asset = self.mapper.requires_reference(
            request.operation
        ) or self.mapper.requires_source_image(request.operation)
        if needs_asset and not references_approved:
            reasons.append("required reference not approved")
        if needs_asset and not upload_hash_matches:
            reasons.append("reference upload hash mismatch")
        if not (1 <= request.candidate_limit <= self.max_candidates):
            reasons.append(
                f"candidate_limit {request.candidate_limit} outside "
                f"[1, {self.max_candidates}]"
            )
        if not cost_allowed:
            reasons.append("cost/quota policy blocks submission")
        if not pre_submit_evidence_hash:
            reasons.append("pre-submit evidence missing")

        return PreSubmitVerdict(ok=not reasons, reasons=tuple(reasons))


__all__ = [
    "FlowPreSubmitBlockedError",
    "PreSubmitGuard",
    "PreSubmitGuardError",
    "PreSubmitVerdict",
]
