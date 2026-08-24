"""Live Record failure policy (live_record.contract/v0.1).

Mirrors ``FAILURE_POLICIES`` in
frontend/app/src/features/live-record/domain/stateMachine.ts (Phase 0 frozen)
and implements Section 18 of ban_ke_hoach_v1.md: every runtime failure is
classified into exactly one of three classes with a deterministic recovery
action — the director loop never improvises.

Classes:
- RECOVERABLE        → RETRY_RESUME (session resumption handle, same take)
- OPERATOR_REQUIRED  → PAUSE_REQUEST_OPERATOR (take pauses, human decides)
- FATAL              → STOP_FINALIZE (finalize the take, evidence preserved)

Unknown/unmapped failures fail-closed to OPERATOR_REQUIRED: automation stops
but the take is kept for a human — never silently retried, never discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Tuple


class FailureClass(str, Enum):
    RECOVERABLE = "RECOVERABLE"
    OPERATOR_REQUIRED = "OPERATOR_REQUIRED"
    FATAL = "FATAL"


class RecoveryAction(str, Enum):
    RETRY_RESUME = "RETRY_RESUME"
    PAUSE_REQUEST_OPERATOR = "PAUSE_REQUEST_OPERATOR"
    STOP_FINALIZE = "STOP_FINALIZE"


@dataclass(frozen=True)
class FailurePolicy:
    """One frozen policy row — mirrors TS ``FailurePolicy``."""

    failure: str
    failure_class: FailureClass
    action: RecoveryAction


#: Frozen table — order and wording mirror the TS source of truth.
FAILURE_POLICIES: Tuple[FailurePolicy, ...] = (
    FailurePolicy("Gemini network disconnect", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("Browser page slow", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("Visual verification timeout", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("Tool command timeout", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("UI changed", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR),
    FailurePolicy(
        "VS Code unexpected dialog", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR
    ),
    FailurePolicy(
        "Website requires login", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR
    ),
    FailurePolicy("disk full", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("NVENC failure", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("capture device destroyed", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("plan tampered", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("workspace hash mismatch", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
)

#: Canonical machine codes accepted by :func:`classify_failure`.
FAILURE_CODES: Dict[str, FailurePolicy] = {
    "GEMINI_DISCONNECT": FAILURE_POLICIES[0],
    "BROWSER_PAGE_SLOW": FAILURE_POLICIES[1],
    "VISUAL_VERIFY_TIMEOUT": FAILURE_POLICIES[2],
    "TOOL_COMMAND_TIMEOUT": FAILURE_POLICIES[3],
    "UI_CHANGED": FAILURE_POLICIES[4],
    "UNEXPECTED_DIALOG": FAILURE_POLICIES[5],
    "LOGIN_REQUIRED": FAILURE_POLICIES[6],
    "DISK_FULL": FAILURE_POLICIES[7],
    "NVENC_FAILURE": FAILURE_POLICIES[8],
    "CAPTURE_DEVICE_DESTROYED": FAILURE_POLICIES[9],
    "PLAN_TAMPERED": FAILURE_POLICIES[10],
    "WORKSPACE_HASH_MISMATCH": FAILURE_POLICIES[11],
}

#: Fail-closed default: stop automation, keep the take, ask a human.
UNKNOWN_FAILURE_POLICY: FailurePolicy = FailurePolicy(
    "unknown failure", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR
)

# Substring matchers applied after exact-code lookup (case-insensitive).
_KEYWORD_MATCHERS: Tuple[Tuple[FrozenSet[str], FailurePolicy], ...] = (
    (frozenset({"gemini", "network disconnect", "websocket", "connection lost"}), FAILURE_POLICIES[0]),
    (frozenset({"browser page slow", "page slow", "navigation timeout"}), FAILURE_POLICIES[1]),
    (frozenset({"visual verification timeout", "visual verify timeout"}), FAILURE_POLICIES[2]),
    (frozenset({"tool command timeout", "command timeout", "tool timeout"}), FAILURE_POLICIES[3]),
    (frozenset({"ui changed", "selector not found", "element not found"}), FAILURE_POLICIES[4]),
    (frozenset({"unexpected dialog", "modal appeared"}), FAILURE_POLICIES[5]),
    (frozenset({"requires login", "login required", "sign in"}), FAILURE_POLICIES[6]),
    (frozenset({"disk full", "no space left", "insufficient disk"}), FAILURE_POLICIES[7]),
    (frozenset({"nvenc"}), FAILURE_POLICIES[8]),
    (frozenset({"capture device", "ddagrab", "duplicate output"}), FAILURE_POLICIES[9]),
    (frozenset({"plan tampered", "plan_hash mismatch", "hash tamper"}), FAILURE_POLICIES[10]),
    (frozenset({"workspace hash"}), FAILURE_POLICIES[11]),
)

#: Proposed take transition per recovery action (descriptive contract; the
#: authoritative take state machine lives in the Rust engine's state.rs).
PROPOSED_TRANSITIONS: Dict[RecoveryAction, str] = {
    RecoveryAction.RETRY_RESUME: (
        "keep_take_and_resume_session: reconnect via sessionResumption handle, "
        "replay nothing (idempotency_key per action), take returns to RECORDING"
    ),
    RecoveryAction.PAUSE_REQUEST_OPERATOR: (
        "pause_take_and_request_operator: take enters PAUSED, recorder keeps "
        "segments flushed, operator resolves then resumes or stops manually"
    ),
    RecoveryAction.STOP_FINALIZE: (
        "stop_and_finalize_take: flush final segment, write manifest + "
        "timeline.jsonl, mark take outcome FAILED with failure evidence attached"
    ),
}


def classify_failure(failure: str) -> FailurePolicy:
    """Classify a failure by canonical code or free-text description.

    Lookup order: exact canonical code (case-insensitive) → keyword substring
    over the description → fail-closed ``UNKNOWN_FAILURE_POLICY``.
    """
    if not failure:
        return UNKNOWN_FAILURE_POLICY

    policy = FAILURE_CODES.get(failure.strip().upper())
    if policy is not None:
        return policy

    lowered = failure.lower()
    for keywords, matched in _KEYWORD_MATCHERS:
        if any(keyword in lowered for keyword in keywords):
            return matched
    return UNKNOWN_FAILURE_POLICY


def proposed_transition(policy: FailurePolicy) -> str:
    """Return the proposed take transition description for a classified failure."""
    return PROPOSED_TRANSITIONS[policy.action]


__all__ = [
    "FailureClass",
    "FailurePolicy",
    "RecoveryAction",
    "FAILURE_POLICIES",
    "FAILURE_CODES",
    "UNKNOWN_FAILURE_POLICY",
    "PROPOSED_TRANSITIONS",
    "classify_failure",
    "proposed_transition",
]
