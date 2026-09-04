"""Context compaction engine for Agent Runtime context assembly.

Summarizes long conversation logs and tool outputs while preserving critical
decisions, blockers, errors, invariants, and acceptance criteria.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("windagent.agent_runtime.context.compaction")

PRESERVE_KEYWORDS: tuple[str, ...] = (
    "decision",
    "blocker",
    "error",
    "acceptance criteria",
    "failed",
    "passed",
    "must",
    "warning",
    "policy",
    "rule",
    "invariant",
    "contract",
    "goal",
)


class ContextCompactor:
    def __init__(self, artifact_base_uri: str = "artifact://compaction") -> None:
        self.artifact_base_uri = artifact_base_uri

    def is_critical_message(self, text: str) -> bool:
        t_lower = text.lower()
        return any(kw in t_lower for kw in PRESERVE_KEYWORDS)

    def compact_conversation(
        self,
        messages: list[dict[str, Any]],
        max_keep_recent: int = 4,
    ) -> list[dict[str, Any]]:
        """Compacts older messages while preserving critical decisions and active blockers."""
        if len(messages) <= max_keep_recent:
            return list(messages)

        old_messages = messages[:-max_keep_recent]
        recent_messages = messages[-max_keep_recent:]

        compacted_old: list[dict[str, Any]] = []
        preserved_notes: list[str] = []

        for msg in old_messages:
            content = str(msg.get("content", ""))
            role = msg.get("role", "user")
            if self.is_critical_message(content):
                compacted_old.append(msg)
                preserved_notes.append(f"[{role}]: {content[:100]}...")

        summary_text = (
            f"[SYSTEM SUMMARY: {len(old_messages) - len(compacted_old)} older messages compacted. "
            f"Preserved key items: {len(preserved_notes)}]"
        )

        result: list[dict[str, Any]] = [{"role": "system", "content": summary_text}]
        result.extend(compacted_old)
        result.extend(recent_messages)
        return result

    def compact_tool_result(self, tool_name: str, raw_output: str, max_chars: int = 800) -> tuple[str, str]:
        """Truncates verbose tool output, creating a reversible reference URI."""
        if len(raw_output) <= max_chars:
            return raw_output, ""

        head = raw_output[: max_chars // 2]
        tail = raw_output[-max_chars // 2 :]
        ref_id = f"tool_out_{hash(raw_output) & 0xFFFFFFFF:08x}"
        artifact_ref = f"{self.artifact_base_uri}/{ref_id}.log"

        compacted = (
            f"{head}\n\n"
            f"... [TRUNCATED {len(raw_output) - max_chars} CHARACTERS — Full output preserved at {artifact_ref}] ...\n\n"
            f"{tail}"
        )
        return compacted, artifact_ref

    def create_compaction_checkpoint_payload(
        self,
        messages_before: int,
        messages_after: int,
        preserved_critical_count: int,
        artifact_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Creates a snapshot payload for durable compaction checkpoints."""
        return {
            "stage": "compaction",
            "messages_before": messages_before,
            "messages_after": messages_after,
            "compacted_count": max(0, messages_before - messages_after),
            "preserved_critical_count": preserved_critical_count,
            "artifact_refs": list(artifact_refs or []),
        }
