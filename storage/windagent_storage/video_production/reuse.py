"""
Artifact reuse policy (plan 05 §14.4, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

Reuse is allowed ONLY when ALL of the following hold (§14.4):

1. artifact key/version matches (full content key incl. version prefix);
2. the stored file hash/validation is still valid (content file present AND
   its bytes re-hash to the record's content_sha256 — never \"file exists\"
   alone as the deciding evidence);
3. approval is appropriate for the project/revision;
4. the artifact is not stale/revoked (status == VALID, not SUPERSEDED);
5. the policy allows cross-run / cross-project reuse.

Fail-closed: any violated rule returns a REUSE_BLOCKED decision with the
specific reason; reuse never mutates state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from windagent_storage.video_production.key import key_matches
from windagent_storage.video_production.model import (
    ArtifactApprovalStatus,
    ArtifactRecord,
    ArtifactStatus,
)
from windagent_storage.video_production.store import ContentAddressedStore


class ReuseVerdict(str, Enum):
    REUSE_ALLOWED = "REUSE_ALLOWED"
    REUSE_BLOCKED = "REUSE_BLOCKED"


@dataclass(frozen=True)
class ReuseDecision:
    verdict: ReuseVerdict
    reason: str = ""


class ArtifactReusePolicy:
    """Deterministic reuse decision over a record + optional content store."""

    def __init__(
        self,
        *,
        content_store: Optional[ContentAddressedStore] = None,
        require_approval: bool = True,
        allow_cross_project: bool = False,
        allow_cross_run: bool = True,
    ) -> None:
        self.content_store = content_store
        self.require_approval = require_approval
        self.allow_cross_project = allow_cross_project
        self.allow_cross_run = allow_cross_run

    # -- main entry --------------------------------------------------------
    def can_reuse(
        self,
        record: ArtifactRecord,
        *,
        expected_key: str,
        project_id: Optional[str] = None,
        allow_cross_project: Optional[bool] = None,
        allow_cross_run: Optional[bool] = None,
    ) -> ReuseDecision:
        """Evaluate all §14.4 reuse rules against a candidate record."""
        # Rule 1 — full content key match (incl. version prefix).
        if not key_matches(record.artifact_key, expected_key):
            return ReuseDecision(
                ReuseVerdict.REUSE_BLOCKED,
                reason=f"key mismatch: record={record.artifact_key[:24]}… expected={expected_key[:24]}…",
            )

        # Rule 2 — file hash/validation still valid (never \"file exists\" alone).
        if self.content_store is not None:
            stored = self.content_store.read(record.content_sha256)
            if stored is None:
                return ReuseDecision(
                    ReuseVerdict.REUSE_BLOCKED,
                    reason="content file missing from content-addressed store",
                )
            if self.content_store.content_hash(stored) != record.content_sha256:
                return ReuseDecision(
                    ReuseVerdict.REUSE_BLOCKED,
                    reason="content file tampered: stored bytes do not re-hash to record content_sha256",
                )

        # Rule 4 — not stale/revoked.
        if record.status != ArtifactStatus.VALID:
            return ReuseDecision(
                ReuseVerdict.REUSE_BLOCKED,
                reason=f"artifact is {record.status.value} (only VALID is reusable)",
            )

        # Rule 3 — approval appropriate for the project/revision.
        if self.require_approval and record.approval_status != ArtifactApprovalStatus.APPROVED:
            return ReuseDecision(
                ReuseVerdict.REUSE_BLOCKED,
                reason=f"approval required but record is {record.approval_status.value}",
            )

        # Rule 5 — policy allows cross-run/cross-project reuse.
        if project_id is not None and project_id != record.project_id:
            cross_project = allow_cross_project if allow_cross_project is not None else self.allow_cross_project
            if not cross_project:
                return ReuseDecision(
                    ReuseVerdict.REUSE_BLOCKED,
                    reason=f"cross-project reuse disallowed by policy: record project {record.project_id} != requested {project_id}",
                )
        run_policy = allow_cross_run if allow_cross_run is not None else self.allow_cross_run
        if not run_policy:
            return ReuseDecision(ReuseVerdict.REUSE_BLOCKED, reason="cross-run reuse disallowed by policy")

        return ReuseDecision(ReuseVerdict.REUSE_ALLOWED, reason="all §14.4 reuse rules satisfied")


__all__ = ["ReuseVerdict", "ReuseDecision", "ArtifactReusePolicy"]
