"""
Destructive Tool Replay Guard for Orchestration V2 Recovery Engine.
Prevents automatic re-execution of non-idempotent or destructive operations upon crash recovery.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Set

logger = logging.getLogger("windagent.orchestration.recovery.destructive_guard")

DESTRUCTIVE_TOOLS: Set[str] = {
    "write_file", "exec_shell", "git_commit", "git_push",
    "delete_file", "drop_table", "deploy_release"
}


class DestructiveReplayGuard:
    @staticmethod
    def is_destructive(tool_name: str) -> bool:
        return tool_name in DESTRUCTIVE_TOOLS

    @staticmethod
    def is_step_destructive(step_payload: Dict[str, Any]) -> bool:
        tool_name = str(step_payload.get("tool_name", step_payload.get("tool", "")))
        return DestructiveReplayGuard.is_destructive(tool_name)
