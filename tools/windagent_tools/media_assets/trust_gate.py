"""
MediaAssetTrustGate — AssetTrustPort implementation (VP3D Phase 6).

Composes the existing media-asset trust machinery behind the gateway's trust
port:

    asset + acquisition + evidence
        -> content-scan evidence (AssetContentScanner when a payload is
           provided via `payload_provider`)
        -> trust decision (AssetTrustEnforcer)
        -> AssetTrustVerdict (APPROVE / QUARANTINE / REJECT)

Rules (all fail closed, mirroring `AssetTrustEnforcer`):
- UNKNOWN / proprietary license without human review      -> QUARANTINE
- checksum not verified                                   -> QUARANTINE
- commercial use not verified                             -> QUARANTINE
- trademark / attribution without human approval          -> QUARANTINE
- REJECTED license                                        -> REJECT
- embedded executable/script/add-on or path traversal     -> REJECT

The gate is wired at the composition root; providers only see the core
`AssetTrustPort` contract (no tools import).
"""

from __future__ import annotations

from typing import Callable, Optional

from windagent_core.domain.video_production.asset import (
    AssetAcquisitionRecord,
    ReferenceAsset,
)
from windagent_core.domain.video_production.asset_resolution import (
    AssetTrustEvidence,
    AssetTrustVerdict,
)
from windagent_core.domain.video_production.enums import LicenseState

from windagent_tools.media_assets.trust import (
    AssetContentScanner,
    AssetTrustEnforcer,
)


class MediaAssetTrustGate:
    """Content-scan + provenance + trust decision behind the gateway port."""

    def __init__(
        self,
        *,
        scanner: Optional[AssetContentScanner] = None,
        enforcer: Optional[AssetTrustEnforcer] = None,
        payload_provider: Optional[Callable[[ReferenceAsset], Optional[bytes]]] = None,
        archive_entry_names_provider: Optional[Callable[[ReferenceAsset], list]] = None,
    ) -> None:
        self._scanner = scanner or AssetContentScanner()
        self._enforcer = enforcer or AssetTrustEnforcer()
        self._payload_provider = payload_provider
        self._archive_entries_provider = archive_entry_names_provider

    def evaluate(
        self,
        *,
        asset: ReferenceAsset,
        acquisition: AssetAcquisitionRecord,
        evidence: AssetTrustEvidence,
    ) -> AssetTrustVerdict:
        """Decide APPROVE / QUARANTINE / REJECT for the acquired asset."""
        reasons: list = []

        # 1. Content scan (static, read-only; never executes anything).
        scan_rejected = False
        if evidence.content_scan_passed is False:
            scan_rejected = True
            reasons.extend(evidence.scan_reasons or ["content scan reported unsafe"])
        else:
            payload = (
                self._payload_provider(asset) if self._payload_provider else None
            )
            if payload is not None:
                entry_names = (
                    self._archive_entries_provider(asset)
                    if self._archive_entries_provider
                    else None
                )
                try:
                    self._scanner.assert_safe(payload, archive_entry_names=entry_names)
                except Exception as exc:  # noqa: BLE001 - any scan failure is unsafe
                    scan_rejected = True
                    reasons.append(f"content scan rejected payload: {exc}")
        if scan_rejected:
            return AssetTrustVerdict(
                decision="REJECT",
                lifecycle_state="REJECTED",
                reasons=reasons,
            )

        # 2. Provenance trust decision (license/checksum/commercial-use).
        decision = self._enforcer.decide(
            license_state=acquisition.license_state,
            checksum_verified=evidence.checksum_verified,
            commercial_use_verified=evidence.commercial_use_verified,
            trademark=evidence.trademark or bool(evidence.requires_attribution),
            requires_attribution=evidence.requires_attribution,
            human_reviewed=evidence.human_reviewed,
        )
        verdict = AssetTrustVerdict(
            decision=decision.action,
            lifecycle_state=decision.lifecycle_state.value,
            reasons=list(decision.reasons),
        )
        # A license REJECTED at the record level is never downgraded to
        # quarantine: rejected is rejected.
        if acquisition.license_state == LicenseState.REJECTED:
            return AssetTrustVerdict(
                decision="REJECT",
                lifecycle_state="REJECTED",
                reasons=["license is REJECTED"],
            )
        return verdict


__all__ = ["MediaAssetTrustGate"]
