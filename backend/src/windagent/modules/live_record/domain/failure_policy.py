"""Failure policy for Live Record (Phase 17)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureClass(StrEnum):
    RECOVERABLE = "RECOVERABLE"
    OPERATOR_REQUIRED = "OPERATOR_REQUIRED"
    FATAL = "FATAL"


class RecoveryAction(StrEnum):
    RETRY_RESUME = "RETRY_RESUME"
    PAUSE_REQUEST_OPERATOR = "PAUSE_REQUEST_OPERATOR"
    STOP_FINALIZE = "STOP_FINALIZE"


@dataclass(frozen=True)
class FailurePolicy:
    failure: str
    failure_class: FailureClass
    action: RecoveryAction


FAILURE_POLICIES: tuple[FailurePolicy, ...] = (
    FailurePolicy("Gemini network disconnect", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("Browser page slow", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("Visual verification timeout", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("Tool command timeout", FailureClass.RECOVERABLE, RecoveryAction.RETRY_RESUME),
    FailurePolicy("UI changed", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR),
    FailurePolicy("VS Code unexpected dialog", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR),
    FailurePolicy("Website requires login", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR),
    FailurePolicy("disk full", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("NVENC failure", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("capture device destroyed", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("plan tampered", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
    FailurePolicy("workspace hash mismatch", FailureClass.FATAL, RecoveryAction.STOP_FINALIZE),
)

FAILURE_CODES: dict[str, FailurePolicy] = {
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

UNKNOWN_FAILURE_POLICY: FailurePolicy = FailurePolicy("unknown failure", FailureClass.OPERATOR_REQUIRED, RecoveryAction.PAUSE_REQUEST_OPERATOR)

_KEYWORD_MATCHERS: tuple[tuple[frozenset[str], FailurePolicy], ...] = (
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

PROPOSED_TRANSITIONS: dict[RecoveryAction, str] = {
    RecoveryAction.RETRY_RESUME: "keep_take_and_resume_session: reconnect via sessionResumption handle, replay nothing (idempotency_key per action), take returns to RECORDING",
    RecoveryAction.PAUSE_REQUEST_OPERATOR: "pause_take_and_request_operator: take enters PAUSED, recorder keeps segments flushed, operator resolves then resumes or stops manually",
    RecoveryAction.STOP_FINALIZE: "stop_and_finalize_take: flush final segment, write manifest + timeline.jsonl, mark take outcome FAILED with failure evidence attached",
}


def classify_failure(failure: str) -> FailurePolicy:
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
    return PROPOSED_TRANSITIONS[policy.action]


__all__ = ["FAILURE_CODES", "FAILURE_POLICIES", "FailureClass", "FailurePolicy", "RecoveryAction", "UNKNOWN_FAILURE_POLICY", "classify_failure", "proposed_transition"]
