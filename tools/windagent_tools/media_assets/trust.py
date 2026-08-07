"""
Asset trust & provenance scanning (stage_c Phase 6).

Two responsibilities:

1. AssetContentScanner — static inspection of downloaded payloads and archives
   BEFORE anything is imported or run:
   - rejects embedded executables / scripts / drivers / Blender add-ons;
   - detects path traversal in archive entry names;
   - NEVER auto-runs embedded script, driver or add-on from an asset.

2. AssetTrustEnforcer — decides whether an acquired asset is trusted enough to
   use (APPROVED), must be quarantined (QUARANTINED), or is rejected
   (REJECTED), based on license, commercial-use right, and checksum
   verification:
   - UNKNOWN license / no commercial-use evidence / unverified checksum ->
     QUARANTINED (fail closed);
   - provider metadata alone is never enough to auto-approve an UNKNOWN-license
     asset; a human review record is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from windagent_core.domain.video_production.asset_lifecycle import (
    AssetLifecycleState,
)
from windagent_core.domain.video_production.enums import LicenseState

from windagent_tools.media_assets.errors import EmbeddedExecutableError

# ---------------------------------------------------------------------------
# Embedded-content scanning (item 5)
# ---------------------------------------------------------------------------

# Strong magic signatures of executable/script-bearing content. Only
# multi-byte signatures are matched so a legitimate mesh/texture is not
# flagged by a coincidental 2-byte sequence.
SCRIPT_MAGIC: tuple[bytes, ...] = (
    b"\x7fELF",           # ELF binary
    b"MZ",                # PE / DOS executable
    b"#!",                # shebang script
    b"PK\x03\x04",        # zip (may carry add-ons / .py / .exe)
    b"\x1f\x8b",          # gzip
    b"BZh",               # bzip2
    b"\xca\xfe\xba\xbe",  # Mach-O (java classfile also starts with this)
    b"7z\xbc\xaf\x27\x1c",  # 7z
    b"Rar!",              # rar
)

# Blender add-on / extensions are archived python/pyz. A mesh payload that is
# itself a zip carrying an add-on must be rejected.
_ADDON_HINTS = (b"blender", b"addons", b"__init__.py", b"pyz", b"zipfile")


def _has_script_magic(data: bytes, window: int = 8192) -> bool:
    head = data[:window]
    for sig in SCRIPT_MAGIC:
        if sig in head:
            return True
    return False


@dataclass(frozen=True)
class ScanVerdict:
    """Result of static content inspection."""

    safe: bool
    embedded_script: bool
    addon_hint: bool
    path_traversal: bool
    reasons: List[str] = field(default_factory=list)


class AssetContentScanner:
    """Static, read-only inspection; never executes or extracts automatically."""

    def inspect_archive_entries(self, entry_names: List[str]) -> List[str]:
        """Return the subset of archive entry names that escape the root.

        Guards against path traversal / zip-slip: `..`, absolute paths, and
        backslash separators are all flagged.
        """
        unsafe: List[str] = []
        for name in entry_names:
            normalized = name.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                unsafe.append(name)
        return unsafe

    def scan_payload(self, data: bytes, *, archive_entry_names: Optional[List[str]] = None) -> ScanVerdict:
        """Static scan of a payload before import.

        - embedded executable/script magic -> reject;
        - archive entry path traversal -> reject;
        - Blender add-on hints -> reject;
        - nothing is executed or extracted.
        """
        reasons: List[str] = []
        embedded_script = _has_script_magic(data)
        if embedded_script:
            reasons.append("payload embeds executable/script magic")

        addon_hint = any(h in data[:16384].lower() for h in _ADDON_HINTS)
        if addon_hint:
            reasons.append("payload carries Blender add-on / extension hints")

        unsafe_entries = self.inspect_archive_entries(archive_entry_names or [])
        path_traversal = bool(unsafe_entries)
        if path_traversal:
            reasons.append(f"archive path traversal: {unsafe_entries}")

        return ScanVerdict(
            safe=not (embedded_script or addon_hint or path_traversal),
            embedded_script=embedded_script,
            addon_hint=addon_hint,
            path_traversal=path_traversal,
            reasons=reasons,
        )

    def assert_safe(self, data: bytes, *, archive_entry_names: Optional[List[str]] = None) -> ScanVerdict:
        """Raise EmbeddedExecutableError if the payload is not safe."""
        verdict = self.scan_payload(data, archive_entry_names=archive_entry_names)
        if not verdict.safe:
            raise EmbeddedExecutableError(
                "Payload rejected by static content scan (embedded executable/"
                "script/add-on or path traversal).",
                details={"reasons": verdict.reasons},
            )
        return verdict


# ---------------------------------------------------------------------------
# Trust decision (items 2, 3, 7)
# ---------------------------------------------------------------------------

# License states that never grant standing approval on their own.
_UNTRUSTED_LICENSES = {
    LicenseState.UNKNOWN,
    LicenseState.PROPRIETARY,
}


@dataclass(frozen=True)
class TrustDecision:
    """Result of a trust decision for an acquired asset."""

    action: str  # APPROVE | QUARANTINE | REJECT
    lifecycle_state: AssetLifecycleState
    reasons: List[str] = field(default_factory=list)


class AssetTrustEnforcer:
    """Decides whether an asset is trusted, quarantined, or rejected.

    Rules (all fail closed):
    - checksum not verifiable          -> QUARANTINE (cannot use unverified content);
    - commercialUse required and not
      verified                          -> QUARANTINE (no commercial-use right);
    - UNKNOWN / proprietary license and
      no human review                   -> QUARANTINE;
    - REJECTED license                  -> REJECT;
    - trademark / attribution asset and
      no human approval                 -> QUARANTINE;
    - otherwise                         -> APPROVE (standalone licenses).
    """

    def decide(
        self,
        *,
        license_state: LicenseState,
        checksum_verified: bool,
        commercial_use_verified: bool,
        trademark: bool = False,
        requires_attribution: bool = False,
        human_reviewed: bool = False,
    ) -> TrustDecision:
        """Compute a fail-closed trust decision.

        Gates, in order:
        1. license REJECTED           -> REJECT;
        2. checksum unverified        -> QUARANTINE;
        3. trademark/attribution and
           not human-reviewed          -> QUARANTINE;
        4. commercial use unverified  -> QUARANTINE;
        5. UNKNOWN/proprietary license
           and not human-reviewed      -> QUARANTINE (metadata alone is never
                                        enough);
        6. otherwise                  -> APPROVE.
        """
        reasons: List[str] = []

        if license_state == LicenseState.REJECTED:
            return TrustDecision(
                action="REJECT",
                lifecycle_state=AssetLifecycleState.REJECTED,
                reasons=["license is REJECTED"],
            )

        if not checksum_verified:
            return TrustDecision(
                action="QUARANTINE",
                lifecycle_state=AssetLifecycleState.QUARANTINED,
                reasons=["checksum not independently verified"],
            )

        if (trademark or requires_attribution) and not human_reviewed:
            return TrustDecision(
                action="QUARANTINE",
                lifecycle_state=AssetLifecycleState.QUARANTINED,
                reasons=["trademark/attribution asset needs human approval"],
            )

        if not commercial_use_verified:
            return TrustDecision(
                action="QUARANTINE",
                lifecycle_state=AssetLifecycleState.QUARANTINED,
                reasons=["commercial use not verified (fail closed)"],
            )

        if license_state in _UNTRUSTED_LICENSES and not human_reviewed:
            return TrustDecision(
                action="QUARANTINE",
                lifecycle_state=AssetLifecycleState.QUARANTINED,
                reasons=[
                    f"{license_state.value} license requires human review "
                    "(metadata alone is never sufficient)"
                ],
            )

        reasons.append("trusted for use")
        return TrustDecision(
            action="APPROVE",
            lifecycle_state=AssetLifecycleState.APPROVED,
            reasons=reasons,
        )


__all__ = [
    "AssetContentScanner",
    "ScanVerdict",
    "AssetTrustEnforcer",
    "TrustDecision",
    "SCRIPT_MAGIC",
]
