"""
VP3D Phase 3 — Blender execution receipts (plan Stage B §3 backlog item 7).

`BlenderExecutionReceipt` captures everything needed to audit a job without
re-running it: exact argv (secrets redacted), blender version, timing, exit
code, stdout/stderr SHA-256, output artifact hashes and a typed failure
classification. Receipts are immutable and JSON-serializable.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.security.redaction import redact_text

MAX_ARGV_RECORD = 64  # cap recorded argv entries defensively


class BlenderFailureClassification:
    """Typed failure classifications for a blender job."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    PROCESS_CRASH = "PROCESS_CRASH"
    START_FAILED = "START_FAILED"
    INVALID_WORKSPACE = "INVALID_WORKSPACE"
    ADDON_BLOCKED = "ADDON_BLOCKED"
    VERSION_NOT_READY = "VERSION_NOT_READY"
    UNKNOWN = "UNKNOWN"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def sha256_file(path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""


def redact_argv(argv) -> List[str]:
    """Redact secrets from an argv list before persisting it in a receipt."""
    redacted = []
    for arg in list(argv)[:MAX_ARGV_RECORD]:
        redacted.append(redact_text(str(arg)))
    return redacted


@dataclass(frozen=True)
class BlenderExecutionReceipt:
    """Immutable audit record of one blender job execution."""

    job_id: str
    kind: str
    executable_path: str
    redacted_argv: List[str] = field(default_factory=list)
    blender_version: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: float = 0.0
    exit_code: Optional[int] = None
    pid: Optional[int] = None
    stdout_hash: str = ""
    stderr_hash: str = ""
    output_hashes: Dict[str, str] = field(default_factory=dict)
    failure_classification: str = BlenderFailureClassification.UNKNOWN
    cancel_requested: bool = False
    error_snippet: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_process_result(
        cls,
        *,
        job_id: str,
        kind: str,
        executable_path: str,
        argv,
        result,
        blender_version: str = "",
        started_at: float,
        output_hashes: Optional[Dict[str, str]] = None,
        error_snippet: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlenderExecutionReceipt":
        finished_at = time.time()
        if result.timed_out:
            classification = BlenderFailureClassification.TIMEOUT
        elif result.cancelled:
            classification = BlenderFailureClassification.CANCELLED
        elif result.start_failed:
            classification = BlenderFailureClassification.START_FAILED
        elif result.returncode != 0:
            classification = BlenderFailureClassification.PROCESS_CRASH
        else:
            classification = BlenderFailureClassification.SUCCESS

        return cls(
            job_id=job_id,
            kind=kind,
            executable_path=executable_path,
            redacted_argv=redact_argv(argv),
            blender_version=blender_version,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(finished_at - started_at) * 1000.0,
            exit_code=result.returncode,
            pid=result.pid,
            stdout_hash=sha256_text(result.stdout),
            stderr_hash=sha256_text(result.stderr),
            output_hashes=output_hashes or {},
            failure_classification=classification,
            cancel_requested=result.cancelled,
            error_snippet=(error_snippet or result.stderr[:500])[:500],
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "executable_path": self.executable_path,
            "redacted_argv": self.redacted_argv,
            "blender_version": self.blender_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": round(self.duration_ms, 3),
            "exit_code": self.exit_code,
            "pid": self.pid,
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "output_hashes": self.output_hashes,
            "failure_classification": self.failure_classification,
            "cancel_requested": self.cancel_requested,
            "error_snippet": self.error_snippet,
            "metadata": self.metadata,
        }


__all__ = [
    "BlenderFailureClassification",
    "sha256_text",
    "sha256_file",
    "redact_argv",
    "BlenderExecutionReceipt",
]
