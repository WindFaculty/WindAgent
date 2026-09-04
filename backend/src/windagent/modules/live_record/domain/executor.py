"""Constrained executor for prepared actions (Phase 17)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ALLOWED_DIRECTOR_TOOLS = frozenset({"advance_cue", "execute_prepared_action", "verify_visual_state", "pause_recording", "resume_recording", "create_marker", "retry_action", "request_operator"})
DENIED_TOOLS = frozenset({"shell", "write_file", "open_url", "click", "powershell", "run_command_raw", "browser_navigate_raw"})
PREPARED_ACTION_TYPES = frozenset({"CODE_PLAYBACK", "BROWSER_NAVIGATION", "BROWSER_ACTION", "RUN_COMMAND", "TOOL_RUN", "OPEN_FILE", "VISUAL_VERIFY", "SCENE_CONTROL", "MARKER"})


@dataclass(frozen=True)
class DirectorToolCall:
    tool: str
    args: dict[str, str]
    idempotency_key: str
    execution_id: str


@dataclass(frozen=True)
class ExecutorResult:
    ok: bool
    reason: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None


def is_allowed_director_tool(name: str) -> bool:
    return name in ALLOWED_DIRECTOR_TOOLS


def validate_tool_call(call: DirectorToolCall, *, allowed_action_ids: frozenset[str], allowed_state_ids: frozenset[str]) -> ExecutorResult:
    if call.tool in DENIED_TOOLS:
        return ExecutorResult(ok=False, reason=f"DIRECTOR_TOOL_DENIED: {call.tool} is explicitly denied")
    if not is_allowed_director_tool(call.tool):
        return ExecutorResult(ok=False, reason=f"TOOL_NOT_ALLOWED: {call.tool} not in constrained manifest")
    if not call.idempotency_key or not call.execution_id:
        return ExecutorResult(ok=False, reason="IDEMPOTENCY_REQUIRED")
    if call.tool in ("execute_prepared_action", "retry_action"):
        aid = call.args.get("action_id") or ""
        if not aid or aid not in allowed_action_ids:
            return ExecutorResult(ok=False, reason="ACTION_NOT_IN_PLAN")
    if call.tool == "verify_visual_state":
        sid = call.args.get("state_id") or ""
        if not sid or sid not in allowed_state_ids:
            return ExecutorResult(ok=False, reason="STATE_NOT_IN_PLAN")
    return ExecutorResult(ok=True)


TypingMode = Literal["TYPE", "PASTE"]


@dataclass(frozen=True)
class CodePlaybackProfile:
    mode: TypingMode = "TYPE"
    chars_per_second: int = 22
    pause_after_line_ms: int | None = None
    pause_after_block_ms: int | None = None

    def is_valid(self) -> bool:
        if self.mode == "TYPE":
            return 15 <= self.chars_per_second <= 40
        return self.mode == "PASTE"


def verify_code_playback_hashes(*, expected_before: str | None, expected_after: str | None, actual_before: str | None, actual_after: str | None) -> ExecutorResult:
    if expected_before is not None and actual_before != expected_before:
        return ExecutorResult(ok=False, reason="BEFORE_HASH_MISMATCH")
    if expected_after is not None and actual_after != expected_after:
        return ExecutorResult(ok=False, reason="AFTER_HASH_MISMATCH")
    return ExecutorResult(ok=True)


@dataclass(frozen=True)
class CodePlaybackRequest:
    action_id: str
    target_file: str
    payload: str
    before_hash: str | None = None
    after_hash: str | None = None
    typing_mode: TypingMode = "TYPE"
    chars_per_second: int = 22
    pause_after_line_ms: int | None = None
    pause_after_block_ms: int | None = None


@dataclass(frozen=True)
class BrowserActionRequest:
    action_id: str
    operation: str
    semantic_target: str | None = None
    url: str | None = None
    expected_after: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolRunRequest:
    action_id: str
    command: str
    expected_after: dict[str, Any] | None = None


def prepare_code_playback(request: CodePlaybackRequest, *, actual_file_content: str | None = None) -> ExecutorResult:
    import hashlib

    profile = CodePlaybackProfile(mode=request.typing_mode, chars_per_second=request.chars_per_second, pause_after_line_ms=request.pause_after_line_ms, pause_after_block_ms=request.pause_after_block_ms)
    if not profile.is_valid():
        return ExecutorResult(ok=False, reason="INVALID_TYPING_PROFILE")
    if not request.payload:
        return ExecutorResult(ok=False, reason="PAYLOAD_EMPTY")
    if request.before_hash is not None and actual_file_content is not None:
        actual_before = hashlib.sha256(actual_file_content.encode("utf-8")).hexdigest()
        if actual_before != request.before_hash:
            return ExecutorResult(ok=False, reason="BEFORE_HASH_MISMATCH")
    if request.after_hash is not None:
        payload_hash = hashlib.sha256(request.payload.encode("utf-8")).hexdigest()
        if payload_hash != request.after_hash:
            return ExecutorResult(ok=False, reason="PAYLOAD_HASH_MISMATCH_AFTER")
    return ExecutorResult(ok=True, before_hash=request.before_hash, after_hash=request.after_hash)


def prepare_browser_action(request: BrowserActionRequest) -> ExecutorResult:
    if not request.action_id:
        return ExecutorResult(ok=False, reason="BROWSER_ACTION_MALFORMED")
    if request.operation not in ("CLICK", "NAVIGATE", "TYPE", "SELECT", "BROWSER_NAVIGATION", "BROWSER_ACTION"):
        return ExecutorResult(ok=False, reason="BROWSER_OPERATION_UNKNOWN")
    if not request.semantic_target and not request.url:
        return ExecutorResult(ok=False, reason="BROWSER_TARGET_MISSING")
    return ExecutorResult(ok=True)


def prepare_tool_run(request: ToolRunRequest) -> ExecutorResult:
    if not request.action_id or not request.command:
        return ExecutorResult(ok=False, reason="TOOL_RUN_MALFORMED")
    if "artifact://" in request.command:
        return ExecutorResult(ok=False, reason="TOOL_COMMAND_IS_REF_NOT_RESOLVED")
    return ExecutorResult(ok=True)


class PreparedActionExecutor:
    def __init__(self, *, payload_bundles: dict[str, str]) -> None:
        self._bundles = payload_bundles

    def execute(self, action: Any, *, actual_file_content: str | None = None) -> ExecutorResult:
        action_type = getattr(action, "type", "")
        action_id = getattr(action, "action_id", "")
        if action_type == "CODE_PLAYBACK":
            payload = self._bundles.get(action_id, "")
            return prepare_code_playback(CodePlaybackRequest(action_id=action_id, target_file=getattr(action, "target_file", "") or "", payload=payload, before_hash=getattr(action, "before_hash", None), after_hash=getattr(action, "after_hash", None), typing_mode=getattr(action, "typing_mode", "TYPE") or "TYPE", chars_per_second=getattr(action, "chars_per_second", 22) or 22), actual_file_content=actual_file_content)
        if action_type in ("BROWSER_NAVIGATION", "BROWSER_ACTION"):
            return prepare_browser_action(BrowserActionRequest(action_id=action_id, operation=action_type, semantic_target=getattr(action, "browser_semantic_target", None), url=getattr(action, "expected_after", None) and getattr(getattr(action, "expected_after", None), "url_contains", None)))
        if action_type in ("RUN_COMMAND", "TOOL_RUN"):
            payload = self._bundles.get(action_id) or getattr(action, "command_ref", "") or ""
            return prepare_tool_run(ToolRunRequest(action_id=action_id, command=payload))
        if action_type in ("OPEN_FILE", "VISUAL_VERIFY", "SCENE_CONTROL", "MARKER"):
            if not action_id:
                return ExecutorResult(ok=False, reason=f"{action_type}_MALFORMED")
            return ExecutorResult(ok=True)
        return ExecutorResult(ok=False, reason=f"UNKNOWN_ACTION_TYPE:{action_type}")


__all__ = ["ALLOWED_DIRECTOR_TOOLS", "BrowserActionRequest", "CodePlaybackProfile", "CodePlaybackRequest", "DENIED_TOOLS", "DirectorToolCall", "ExecutorResult", "PREPARED_ACTION_TYPES", "PreparedActionExecutor", "ToolRunRequest", "is_allowed_director_tool", "prepare_browser_action", "prepare_code_playback", "prepare_tool_run", "validate_tool_call", "verify_code_playback_hashes"]
