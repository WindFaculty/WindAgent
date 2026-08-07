"""
VP3D Phase 4 — Job idempotency & artifact reuse policy (plan Stage B §4 items 2,5).

Each job kind (COMPILE, SAVE, INSPECT, RENDER_CHUNK, ASSEMBLE, VERIFY) carries
an idempotency key built from:

- the IR inputs (input/content hash),
- the locked config (frame range, fps, resolution, color management, samples,
  denoise, device),
- the tool identity (compiler + trusted script + ffmpeg/ffprobe version pins).

Reuse policy (item 5):

- a COMPLETED job whose key equals the requested key is REUSED (artifact is
  served from disk — no re-execution);
- a COMPLETED job whose key differs is INVALIDATED (its outputs are stale and
  must be recomputed; stale artifacts are removed so they are never served);
- a job in any non-terminal state is neither reused nor invalidated — it must
  be reconciled first (supervisor reattach/quarantine policy).

Determinism (item 7): the same key implies the same inputs/config/tools, so a
reused artifact is structurally identical to a fresh render (pixel hash is
only asserted when the hardware/driver profile is identical).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REUSE = "REUSE"
INVALIDATE = "INVALIDATE"
FRESH = "FRESH"
NON_TERMINAL = "NON_TERMINAL"

TERMINAL_COMPLETED = "COMPLETED"
TERMINAL_FAILED = "FAILED"
TERMINAL_CANCELLED = "CANCELLED"
NON_TERMINAL_STATES = ("STARTING", "RUNNING", "CANCELLING", "SUBMITTED")


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def job_idempotency_key(
    *,
    kind: str,
    input_hash: str,
    config_hash: str,
    tool_hash: str,
) -> str:
    """Stable idempotency key for one job kind + inputs + config + tools."""
    return _stable_hash(f"kind:{kind}", input_hash, config_hash, tool_hash)


@dataclass(frozen=True)
class ReuseDecision:
    """Outcome of checking a completed job against the requested key."""

    decision: str  # REUSE | INVALIDATE | FRESH | NON_TERMINAL
    job_id: Optional[str] = None
    reason: str = ""

    @property
    def can_serve(self) -> bool:
        return self.decision == REUSE


class ArtifactReusePolicy:
    """Decides reuse vs invalidation from a completed job's recorded key."""

    def decide(
        self,
        *,
        requested_key: str,
        recorded_job_id: Optional[str],
        recorded_state: Optional[str],
        recorded_key: Optional[str],
    ) -> ReuseDecision:
        """Inspect a durable job record and decide what to do with its artifacts.

        Parameters mirror the fields a durable receipt/locator carries:
        requested_key (the key we want), recorded_job_id/state/key (what the
        completed job recorded). `recorded_job_id=None` means "no completed
        job exists" -> FRESH.
        """
        if recorded_job_id is None:
            return ReuseDecision(FRESH, reason="no prior completed job for this scene")

        if recorded_state in NON_TERMINAL_STATES:
            return ReuseDecision(
                NON_TERMINAL,
                job_id=recorded_job_id,
                reason=f"prior job {recorded_job_id} is {recorded_state}; "
                "must reconcile before reuse or retry",
            )
        if recorded_state not in (TERMINAL_COMPLETED,):
            return ReuseDecision(
                INVALIDATE,
                job_id=recorded_job_id,
                reason=f"prior job {recorded_job_id} is {recorded_state}; "
                "no reusable artifact",
            )

        if recorded_key == requested_key:
            return ReuseDecision(
                REUSE,
                job_id=recorded_job_id,
                reason="inputs/config/tools unchanged — artifact is reused",
            )
        return ReuseDecision(
            INVALIDATE,
            job_id=recorded_job_id,
            reason="idempotency key changed — prior artifact is stale and invalidated",
        )

    # ------------------------------------------------------------------
    def invalidate_outputs(self, workspace: Path, keep: tuple[str, ...] = ()) -> None:
        """Remove stale derived outputs from a job workspace.

        `keep` is a tuple of filenames to preserve (e.g. job_spec.json,
        cancel token). Invalidation deletes render outputs so a stale artifact
        can never be served (item 5: hash khác phải invalidate).
        """
        if not workspace.is_dir():
            return
        stale_patterns = ("*.png", "*.exr", "*.blend", "*.mp4", "frame_manifest.json")
        for pattern in stale_patterns:
            for path in workspace.glob(pattern):
                if path.name in keep:
                    continue
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "REUSE",
    "INVALIDATE",
    "FRESH",
    "NON_TERMINAL",
    "TERMINAL_COMPLETED",
    "TERMINAL_FAILED",
    "TERMINAL_CANCELLED",
    "NON_TERMINAL_STATES",
    "job_idempotency_key",
    "ReuseDecision",
    "ArtifactReusePolicy",
]
