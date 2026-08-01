"""
AssetProvenanceService (plan 02 §21.3) — provenance and license.

Every asset record carries:
    asset_id, content_sha256, source_type, source_url/provider, retrieved_at,
    original_license, license_evidence, creator/attribution,
    transformation_history, validation_receipt, approval_state

Fail-closed rules:
- LICENSE_UNKNOWN never becomes APPROVED on its own (requires human review);
- real-person likeness requires human approval + usage evidence;
- a REJECTED asset cannot be re-selected (no silent REJECTED -> APPROVED).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.asset_lifecycle import (
    AssetLifecycleState,
    AssetStateMachine,
)
from windagent_core.domain.video_production.enums import (
    AssetSourceType,
    LicenseState,
)

from windagent_tools.media_assets.errors import (
    LicenseUnknownError,
    LikenessRequiresApprovalError,
    RejectedAssetError,
)


@dataclass(frozen=True)
class AssetProvenanceRecord:
    """Complete provenance + lifecycle record for one asset."""

    asset_id: str
    content_sha256: str
    source_type: AssetSourceType
    source_url: Optional[str] = None
    source_provider: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    original_license: LicenseState = LicenseState.UNKNOWN
    license_evidence: List[str] = field(default_factory=list)
    creator_attribution: str = ""
    transformation_history: List[str] = field(default_factory=list)
    validation_receipt: Optional[dict] = None
    lifecycle_state: AssetLifecycleState = AssetLifecycleState.DISCOVERED
    approval_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "content_sha256": self.content_sha256,
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "source_provider": self.source_provider,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "original_license": self.original_license.value,
            "license_evidence": self.license_evidence,
            "creator_attribution": self.creator_attribution,
            "transformation_history": self.transformation_history,
            "validation_receipt": self.validation_receipt,
            "lifecycle_state": self.lifecycle_state.value,
            "approval_state": self.approval_state,
        }


class AssetProvenanceService:
    """Builds and advances provenance records through the lifecycle."""

    def __init__(self, *, seed: str = "windagent-asset-provenance") -> None:
        self._seed = seed

    def _asset_id(self, content_hash: str) -> str:
        import hashlib

        digest = hashlib.sha256(f"{self._seed}::{content_hash}".encode("utf-8")).hexdigest()[:16]
        return f"ast_{digest}"

    def build_record(
        self,
        *,
        content_hash: str,
        source_type: AssetSourceType,
        source_url: Optional[str] = None,
        source_provider: Optional[str] = None,
        original_license: LicenseState = LicenseState.UNKNOWN,
        license_evidence: Optional[List[str]] = None,
        creator_attribution: str = "",
        validation_receipt: Optional[dict] = None,
    ) -> AssetProvenanceRecord:
        """Create a new record from a validated content hash (VALIDATED)."""
        return AssetProvenanceRecord(
            asset_id=self._asset_id(content_hash),
            content_sha256=content_hash,
            source_type=source_type,
            source_url=source_url,
            source_provider=source_provider,
            retrieved_at=datetime.now(timezone.utc),
            original_license=original_license,
            license_evidence=list(license_evidence or []),
            creator_attribution=creator_attribution,
            validation_receipt=validation_receipt,
            lifecycle_state=AssetLifecycleState.VALIDATED,
        )

    def advance_license(
        self,
        record: AssetProvenanceRecord,
        *,
        new_license: LicenseState,
        evidence: Optional[List[str]] = None,
        real_person_likeness: bool = False,
        human_approved: bool = False,
    ) -> AssetProvenanceRecord:
        """Move VALIDATED -> LICENSE_UNKNOWN | APPROVED | REJECTED.

        Fail-closed:
        - LICENSE_UNKNOWN stays blocked until a human approves with evidence;
        - real-person likeness requires human approval + usage evidence;
        - REJECTED cannot silently flip to APPROVED.
        """
        if record.lifecycle_state == AssetLifecycleState.REJECTED:
            raise RejectedAssetError(
                "Rejected asset cannot be re-selected without a new review record."
            )

        if new_license == LicenseState.UNKNOWN:
            target = AssetLifecycleState.LICENSE_UNKNOWN
            AssetStateMachine.require_transition(record.lifecycle_state, target)
            return replace(record, lifecycle_state=target)

        # APPROVED path requires evidence.
        evidence = evidence or []
        if new_license == LicenseState.REJECTED:
            target = AssetLifecycleState.REJECTED
            AssetStateMachine.require_transition(record.lifecycle_state, target)
            return replace(
                record,
                original_license=new_license,
                license_evidence=list(record.license_evidence) + evidence,
                lifecycle_state=target,
                approval_state={"reviewed": True, "approved": False},
            )

        # new_license == APPROVED (LICENSED/PUBLIC_DOMAIN/CREATIVE_COMMONS/PROPRIETARY)
        if not evidence:
            raise LicenseUnknownError(
                "Approval requires license evidence (fail closed).",
                details={"license": new_license.value},
            )
        if real_person_likeness and not human_approved:
            raise LikenessRequiresApprovalError(
                "Real-person likeness requires human approval + usage evidence."
            )
        target = AssetLifecycleState.APPROVED
        AssetStateMachine.require_transition(record.lifecycle_state, target)
        return replace(
            record,
            original_license=new_license,
            license_evidence=list(record.license_evidence) + evidence,
            lifecycle_state=target,
            approval_state={"reviewed": True, "approved": True, "human": human_approved},
        )

    def bind_to_project(self, record: AssetProvenanceRecord) -> AssetProvenanceRecord:
        """APPROVED -> BOUND_TO_PROJECT (final)."""
        AssetStateMachine.require_transition(
            record.lifecycle_state, AssetLifecycleState.BOUND_TO_PROJECT
        )
        return replace(record, lifecycle_state=AssetLifecycleState.BOUND_TO_PROJECT)


__all__ = ["AssetProvenanceService", "AssetProvenanceRecord"]
