"""
Phase 12 — Redacted evidence capture (plan 04 §8.5).

Every bounded browser action records a structured evidence record:

    action_id, session_id, operation, target_semantics,
    started_at / finished_at, result_state,
    redacted_screenshot_hash, snapshot_hash, error_class

The recorder never stores raw screenshots, page text, URLs with credentials or
any secret material — only hashes of the captured content, plus sanitized
semantics via the existing audit redaction helpers.
"""

from __future__ import annotations

import contextlib
import hashlib
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from windagent_tools.browser.agent_browser import BrowserAuditLogger


class BrowserActionResultState(str, Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


@dataclass(frozen=True)
class BrowserActionEvidence:
    """One immutable bounded-action evidence record (plan 04 §8.5)."""

    action_id: str
    session_id: str
    operation: str
    target_semantics: str
    started_at: float
    finished_at: float
    result_state: BrowserActionResultState
    redacted_screenshot_hash: str = ""
    snapshot_hash: str = ""
    error_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "session_id": self.session_id,
            "operation": self.operation,
            "target_semantics": self.target_semantics,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result_state": self.result_state.value,
            "redacted_screenshot_hash": self.redacted_screenshot_hash,
            "snapshot_hash": self.snapshot_hash,
            "error_class": self.error_class,
        }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BrowserEvidenceRecorder:
    """Records deterministic, redacted evidence for every bounded action.

    `redact_screenshot` is a hook so tests can inject a fake redactor (e.g.
    always returns a fixed hash) — the recorder itself never inspects
    screenshot content.
    """

    def __init__(
        self,
        *,
        session_id: str,
        clock: Optional[callable] = None,
        redact_screenshot: Optional[callable] = None,
    ) -> None:
        self.session_id = session_id
        self._clock = clock or time.time
        self._audit = BrowserAuditLogger()
        self._redact_screenshot = redact_screenshot or _sha256_file
        self._records: dict[str, BrowserActionEvidence] = {}

    # ------------------------------------------------------------------
    def begin(
        self,
        operation: str,
        *,
        target: Optional[str] = None,
    ) -> str:
        """Open an action and return its action_id."""
        action_id = f"act_{uuid.uuid4().hex[:16]}"
        sanitized_target = (
            self._audit.sanitize_url_string(str(target)) if target else ""
        )
        record = {
            "action_id": action_id,
            "session_id": self.session_id,
            "operation": str(operation),
            "target_semantics": sanitized_target[:512],
            "started_at": self._clock(),
            "finished_at": 0.0,
            "result_state": BrowserActionResultState.SUCCESS,
            "redacted_screenshot_hash": "",
            "snapshot_hash": "",
            "error_class": "",
        }
        self._records[action_id] = BrowserActionEvidence(**record)
        return action_id

    def finish(
        self,
        action_id: str,
        result_state: BrowserActionResultState,
        *,
        screenshot_path: Optional[str] = None,
        snapshot: Optional[str] = None,
        error_class: str = "",
    ) -> BrowserActionEvidence:
        """Close an action, attaching redacted content hashes only."""
        record = self._records.get(action_id)
        if record is None:
            raise KeyError(f"unknown action_id {action_id}")
        redacted_screenshot_hash = ""
        if screenshot_path:
            with contextlib.suppress(OSError):
                redacted_screenshot_hash = self._redact_screenshot(
                    Path(screenshot_path)
                )
        snapshot_hash = _sha256_bytes(snapshot.encode("utf-8")) if snapshot else ""
        updated = BrowserActionEvidence(
            action_id=record.action_id,
            session_id=record.session_id,
            operation=record.operation,
            target_semantics=record.target_semantics,
            started_at=record.started_at,
            finished_at=self._clock(),
            result_state=result_state,
            redacted_screenshot_hash=redacted_screenshot_hash,
            snapshot_hash=snapshot_hash,
            error_class=error_class[:128],
        )
        self._records[action_id] = updated
        return updated

    def get(self, action_id: str) -> Optional[BrowserActionEvidence]:
        return self._records.get(action_id)

    def recent(self, limit: int = 50) -> list[BrowserActionEvidence]:
        return sorted(
            self._records.values(), key=lambda r: r.started_at, reverse=True
        )[:limit]

    def records(self) -> list[BrowserActionEvidence]:
        return sorted(self._records.values(), key=lambda r: r.started_at)


__all__ = [
    "BrowserActionEvidence",
    "BrowserActionResultState",
    "BrowserEvidenceRecorder",
]
