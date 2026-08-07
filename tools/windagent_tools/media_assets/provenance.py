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
    QuarantinedAssetError,
    RejectedAssetError,
    TrademarkRequiresApprovalError,
)


@dataclass(frozen=True)
class AssetProvenanceRecord:
    """Complete provenance + lifecycle record for one asset.

    Extended for asset trust (stage_c Phase 6):
    - `source_author` / `tool` / `model` / `prompt_hash` / `seed` / `generation_receipt`
      record full provenance, including the generation parameters of a
      generated asset (item 2);
    - `commercial_use_verified` gates commercial-use licensing (item 3);
    - `trademark` / `requires_attribution` trigger human approval (item 7);
    - `derived_from_hash` / `normalization_receipt` record conversion lineage
      (item 6).
    """

    asset_id: str
    content_sha256: str
    source_type: AssetSourceType
    source_url: Optional[str] = None
    source_provider: Optional[str] = None
    source_author: str = ""
    retrieved_at: Optional[datetime] = None
    original_license: LicenseState = LicenseState.UNKNOWN
    license_evidence: List[str] = field(default_factory=list)
    creator_attribution: str = ""
    # Generated-asset provenance (item 2)
    tool: Optional[str] = None
    model: Optional[str] = None
    prompt_hash: Optional[str] = None
    seed: Optional[int] = None
    generation_receipt: Optional[dict] = None
    # Trust gates (items 3, 7)
    commercial_use_verified: bool = False
    trademark: bool = False
    requires_attribution: bool = False
    checksum_verified: bool = True
    # Conversion lineage (item 6)
    derived_from_hash: Optional[str] = None
    normalization_receipt: Optional[dict] = None
    transformation_history: List[str] = field(default_factory=list)
    validation_receipt: Optional[dict] = None
    quarantine_reason: Optional[str] = None
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
            "source_author": self.source_author,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "original_license": self.original_license.value,
            "license_evidence": self.license_evidence,
            "creator_attribution": self.creator_attribution,
            "tool": self.tool,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "seed": self.seed,
            "generation_receipt": self.generation_receipt,
            "commercial_use_verified": self.commercial_use_verified,
            "trademark": self.trademark,
            "requires_attribution": self.requires_attribution,
            "checksum_verified": self.checksum_verified,
            "derived_from_hash": self.derived_from_hash,
            "normalization_receipt": self.normalization_receipt,
            "transformation_history": self.transformation_history,
            "validation_receipt": self.validation_receipt,
            "quarantine_reason": self.quarantine_reason,
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
        source_author: str = "",
        original_license: LicenseState = LicenseState.UNKNOWN,
        license_evidence: Optional[List[str]] = None,
        creator_attribution: str = "",
        validation_receipt: Optional[dict] = None,
        # generated-asset provenance (item 2)
        tool: Optional[str] = None,
        model: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        seed: Optional[int] = None,
        generation_receipt: Optional[dict] = None,
        # trust gates (items 3, 7)
        commercial_use_verified: bool = False,
        trademark: bool = False,
        requires_attribution: bool = False,
        checksum_verified: bool = True,
    ) -> AssetProvenanceRecord:
        """Create a new record from a validated content hash (VALIDATED)."""
        return AssetProvenanceRecord(
            asset_id=self._asset_id(content_hash),
            content_sha256=content_hash,
            source_type=source_type,
            source_url=source_url,
            source_provider=source_provider,
            source_author=source_author,
            retrieved_at=datetime.now(timezone.utc),
            original_license=original_license,
            license_evidence=list(license_evidence or []),
            creator_attribution=creator_attribution,
            tool=tool,
            model=model,
            prompt_hash=prompt_hash,
            seed=seed,
            generation_receipt=generation_receipt,
            commercial_use_verified=commercial_use_verified,
            trademark=trademark,
            requires_attribution=requires_attribution,
            checksum_verified=checksum_verified,
            validation_receipt=validation_receipt,
            lifecycle_state=AssetLifecycleState.VALIDATED,
        )

    def record_derivation(
        self,
        source: AssetProvenanceRecord,
        *,
        derived_hash: str,
        normalization_receipt: Optional[dict] = None,
    ) -> AssetProvenanceRecord:
        """Record a derived asset's conversion lineage (item 6).

        The derived asset points back to the source hash and carries the
        normalization receipt, so every transformed asset keeps an auditable
        lineage. Both source and derived remain content-addressed by their own
        hashes.
        """
        return AssetProvenanceRecord(
            asset_id=self._asset_id(derived_hash),
            content_sha256=derived_hash,
            source_type=source.source_type,
            source_url=source.source_url,
            source_provider=source.source_provider,
            source_author=source.source_author,
            retrieved_at=datetime.now(timezone.utc),
            original_license=source.original_license,
            license_evidence=list(source.license_evidence),
            creator_attribution=source.creator_attribution,
            tool=source.tool,
            model=source.model,
            prompt_hash=source.prompt_hash,
            seed=source.seed,
            generation_receipt=source.generation_receipt,
            commercial_use_verified=source.commercial_use_verified,
            trademark=source.trademark,
            requires_attribution=source.requires_attribution,
            checksum_verified=source.checksum_verified,
            derived_from_hash=source.content_sha256,
            normalization_receipt=normalization_receipt,
            transformation_history=[
                *source.transformation_history,
                f"derived:{source.content_sha256}",
            ],
            validation_receipt=source.validation_receipt,
            lifecycle_state=AssetLifecycleState.VALIDATED,
        )

    @staticmethod
    def _require_human_review(record: AssetProvenanceRecord, target: AssetLifecycleState) -> None:
        """QUARANTINED/REJECTED -> APPROVED needs a new human review record."""
        AssetStateMachine.require_transition(
            record.lifecycle_state, target, new_review_record=True
        )

    def quarantine(
        self,
        record: AssetProvenanceRecord,
        *,
        reason: str,
    ) -> AssetProvenanceRecord:
        """Move VALIDATED / LICENSE_UNKNOWN -> QUARANTINED (fail closed).

        Applies when the asset has an UNKNOWN license, unverified checksum, or
        no demonstrable commercial-use right. Only a fresh human review can
        promote it out of quarantine.
        """
        target = AssetLifecycleState.QUARANTINED
        AssetStateMachine.require_transition(record.lifecycle_state, target)
        return replace(
            record,
            lifecycle_state=target,
            quarantine_reason=reason,
            approval_state=dict(record.approval_state, quarantined=True),
        )

    def promote_from_quarantine(
        self,
        record: AssetProvenanceRecord,
        *,
        new_license: LicenseState,
        evidence: List[str],
        human_approved: bool,
    ) -> AssetProvenanceRecord:
        """Promote a QUARANTINED asset to APPROVED after human review.

        Fail closed: requires a fresh human review record + evidence. Trademark
        / attribution / likeness assets additionally require explicit human
        sign-off. A quarantined asset is never promoted by provider metadata
        alone.
        """
        if record.lifecycle_state != AssetLifecycleState.QUARANTINED:
            raise QuarantinedAssetError(
                "Only a QUARANTINED asset can be promoted from quarantine.",
                details={"state": record.lifecycle_state.value},
            )
        self._require_human_review(record, AssetLifecycleState.APPROVED)
        evidence = evidence or []
        if not evidence:
            raise QuarantinedAssetError(
                "Promotion from quarantine requires evidence (fail closed)."
            )
        if not human_approved:
            raise QuarantinedAssetError(
                "Promotion from quarantine requires explicit human approval."
            )
        if record.trademark or record.requires_attribution:
            if not human_approved or not record.checksum_verified:
                raise TrademarkRequiresApprovalError(
                    "Trademark/attribution asset requires human approval and a "
                    "verified checksum.",
                    details={
                        "trademark": record.trademark,
                        "requires_attribution": record.requires_attribution,
                    },
                )
        approved = replace(
            record,
            original_license=new_license,
            license_evidence=list(record.license_evidence) + evidence,
            lifecycle_state=AssetLifecycleState.APPROVED,
            quarantine_reason=None,
            approval_state={
                "reviewed": True,
                "approved": True,
                "human": True,
                "promoted_from_quarantine": True,
            },
        )
        return approved

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
