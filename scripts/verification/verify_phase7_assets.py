#!/usr/bin/env python3
"""
Phase 7 verification — VP7_ASSET_PIPELINE_VERIFIED (plan 02 §19-§23).

Verifies the media asset pipeline (`tools/windagent_tools/media_assets/`)
against the ratified contracts in `docs/video_production/assets/`:

  artifacts/video_production/phase_07/
  ├── downloader_security_matrix.json
  ├── media_validation_receipt.json
  ├── provenance_contract_receipt.json
  ├── state_machine_test_receipt.json
  ├── e2e_package_receipt.json
  └── phase_verdict.json

Gate conditions (plan 02 §23):
  1. SSRF / redirect / MIME / size / pixel controls have automated negative
     tests (localhost, private IP, DNS rebinding, redirect to private IP,
     oversize, decompression bomb, wrong MIME, zero byte, polyglot,
     executable, archive, SVG);
  2. every approved / bound asset carries a content hash, a validation
     receipt, and a provenance record (license unknown or real-person
     likeness never passes the human gate without evidence/approval);
  3. partial or invalid downloads never appear in the canonical
     content-addressed store;
  4. the pre-production E2E (search -> download -> validate -> approve ->
     bind -> reference -> package) assembles a valid VideoProductionPackage
     v1 without importing upstream.

Every check below is real and offline: downloads use a fake transport and a
fake DNS resolver (no network), media payloads are generated in-memory, and
provenance/state-machine checks exercise the canonical domain rules.

Supports --no-write / --verify-only (runs all checks, writes nothing).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_07"

# Root of the canonical workspace is always importable in the venv; ensure it
# even when this script runs from another cwd.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Evidence writers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


# ---------------------------------------------------------------------------
# Deterministic fakes (offline — no network ever)
# ---------------------------------------------------------------------------


def _fake_resolver(addresses: list[str]):
    """DNS resolver fake returning the given addresses (getaddrinfo shape)."""
    import socket

    def resolver(host, port):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (addr, port or 80))
            for addr in addresses
        ]

    return resolver


def _png_bytes(width: int = 4, height: int = 4, color=(200, 50, 50)) -> bytes:
    """Small valid PNG generated in-memory (no file writes, offline)."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_exif() -> bytes:
    """JPEG carrying EXIF metadata (Make tag) for the sanitization check."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (4, 4), (50, 200, 50))
    exif = Image.Exif()
    exif[0x010F] = "Phase 7 test camera"
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class _FakeRedirectTransport:
    """Transport fake: pops a redirect hop, then returns a fixed body.

    Each hop is delivered as a `_RedirectSignal` (the exact signal the
    download service already handles) so the service's hop-by-hop
    re-validation is exercised without any network call.
    """

    def __init__(self, hops: list[str], body: bytes = b"ok") -> None:
        self._hops = list(hops)
        self._body = body
        self.fetched: list[str] = []
        self.max_concurrent = 0
        self._active = 0

    async def fetch(self, url: str, *, max_bytes: int, timeout: float) -> bytes:

        if self._hops:
            return await self._redirect(self._hops.pop(0))
        self._active += 1
        self.max_concurrent = max(self.max_concurrent, self._active)
        try:
            await asyncio.sleep(0)
            self.fetched.append(url)
            return self._body
        finally:
            self._active -= 1

    async def _redirect(self, location: str) -> bytes:
        from windagent_tools.media_assets.download import _RedirectSignal

        raise _RedirectSignal(location)


class _StaticSearchProvider:
    """Search provider fake returning pinned raw items."""

    name = "fake-image-catalog"

    def __init__(self, items: list[dict]) -> None:
        self._items = items

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        return self._items[:limit]


# ---------------------------------------------------------------------------
# 1. Downloader security matrix (plan 02 §21.1 / §22)
# ---------------------------------------------------------------------------


def build_downloader_security_matrix() -> dict:
    """Negative + positive SSRF/redirect/MIME controls with offline fakes."""
    from windagent_tools.media_assets import (
        DownloadFailedError,
        UrlBlockedError,
        classify_payload,
        is_public_ip,
        validate_download_url,
        validate_host_ips,
        validate_redirect_target,
    )

    checks: list[dict] = []
    PUBLIC_IP = "93.184.216.34"  # public IPv4 literal (example.com)

    # --- URL / IP policy -------------------------------------------------
    _record(checks, "scheme_ftp_blocked",
            _raises(lambda: validate_download_url("ftp://example.com/a.png"), UrlBlockedError),
            "non-http(s) scheme must be rejected")
    _record(checks, "scheme_https_allowed",
            _ok(lambda: validate_download_url(f"https://{PUBLIC_IP}/a.png")),
            "https to a public IP literal is allowed")
    _record(checks, "private_ip_literal_blocked",
            _raises(lambda: validate_download_url("http://192.168.1.10/a.png"), UrlBlockedError),
            "RFC1918 literal must be rejected")
    _record(checks, "localhost_ip_literal_blocked",
            _raises(lambda: validate_download_url("http://127.0.0.1/a.png"), UrlBlockedError),
            "loopback literal must be rejected")
    _record(checks, "link_local_ip_literal_blocked",
            _raises(lambda: validate_download_url("http://169.254.0.1/a.png"), UrlBlockedError),
            "link-local literal must be rejected")
    _record(checks, "embedded_credentials_blocked",
            _raises(lambda: validate_download_url(f"http://user:pass@{PUBLIC_IP}/a.png"), UrlBlockedError),
            "URLs embedding credentials must be rejected")
    _record(checks, "public_ip_literal_ok",
            _ok(lambda: validate_download_url(f"http://{PUBLIC_IP}/a.png")),
            "public IP literal passes")

    # --- DNS rebinding ---------------------------------------------------
    _record(checks, "dns_rebinding_private_resolved_blocked",
            _raises(lambda: validate_download_url(
                "http://rebind.example/a.png", resolver=_fake_resolver(["10.0.0.5"])), UrlBlockedError),
            "host resolving to a private IP is rejected (DNS rebinding)")
    _record(checks, "dns_rebinding_mixed_addresses_blocked",
            _raises(lambda: validate_download_url(
                "http://mixed.example/a.png",
                resolver=_fake_resolver([PUBLIC_IP, "10.0.0.6"])), UrlBlockedError),
            "ANY non-public resolved address rejects the host")
    _record(checks, "dns_all_public_ok",
            _ok(lambda: validate_download_url(
                "http://good.example/a.png", resolver=_fake_resolver([PUBLIC_IP]))),
            "host resolving only to public IPs passes")
    _record(checks, "dns_unresolvable_fail_closed",
            _raises(lambda: validate_host_ips("nope.example", resolver=_unresolvable), UrlBlockedError),
            "an unresolvable host fails closed (no silent allow)")

    # --- Redirects -------------------------------------------------------
    _record(checks, "redirect_to_private_ip_blocked",
            _raises(lambda: validate_redirect_target("http://10.0.0.7/b.png"), UrlBlockedError),
            "redirect target must be re-validated")
    _record(checks, "redirect_bounded_after_max_hops",
            _raises(lambda: asyncio.run(_download_hop_loop()), DownloadFailedError),
            "too many redirects raises DownloadFailedError")

    # --- Oversize / payload classification -------------------------------
    _record(checks, "oversize_response_rejected",
            _raises(lambda: asyncio.run(_download_oversize()), DownloadFailedError),
            "body over max_bytes must be rejected")
    fp_exe = classify_payload(b"MZ\x90\x00\x03\x00\x00\x00")
    _record(checks, "executable_magic_detected", fp_exe.is_executable,
            "PE/ELF/shebang magic must be flagged")
    fp_zip = classify_payload(b"PK\x03\x04rest")
    _record(checks, "archive_magic_detected", fp_zip.is_archive,
            "zip/rar/7z/gzip magic must be flagged")
    # A PNG that embeds a zip stub inside its header window is a polyglot.
    poly = classify_payload(b"\x89PNG\r\n\x1a\n" + b"PK\x03\x04\x14\x00\x00\x00")
    _record(checks, "polyglot_png_zip_detected", poly.looks_polyglot,
            "image+archive polyglot (embedded zip magic) must be flagged")
    _record(checks, "zero_byte_detected",
            classify_payload(b"").is_zero_byte,
            "zero-byte payload must be flagged")
    _record(checks, "public_ip_heuristic",
            is_public_ip(PUBLIC_IP) and not is_public_ip("127.0.0.1") and not is_public_ip("10.1.2.3"),
            "is_public_ip classifies public vs private")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "control_count": len(checks),
        "all_controls_pass": all_ok,
        "controls": checks,
    }


def _unresolvable(host, port):
    raise OSError(f"no addresses for {host}")


def _raises(fn, exc_type) -> bool:
    try:
        fn()
        return False
    except exc_type:
        return True
    except Exception:
        return False


def _ok(fn) -> bool:
    try:
        fn()
        return True
    except Exception:
        return False


async def _download_hop_loop() -> None:
    from windagent_tools.media_assets.download import AssetDownloadService

    hops = [f"http://93.184.216.34/hop{i}.png" for i in range(12)]
    svc = AssetDownloadService(
        transport=_FakeRedirectTransport(hops),
        max_redirects=5,
    )
    await svc.download("http://93.184.216.34/start.png")


async def _download_oversize() -> None:
    from windagent_tools.media_assets.download import AssetDownloadService

    svc = AssetDownloadService(
        transport=_FakeRedirectTransport([], body=b"x" * 1024),
        max_bytes=100,
    )
    await svc.download("http://93.184.216.34/big.png")


# ---------------------------------------------------------------------------
# 2. Media validation receipt (plan 02 §21.2)
# ---------------------------------------------------------------------------


def build_media_validation_receipt() -> dict:
    """Ordered validation pipeline: decode -> pixel -> sanitize -> hash ->
    publish, with every negative control from plan 02 §22."""
    from windagent_tools.media_assets import (
        AssetValidationService,
        ContentAddressedStore,
        MediaValidationError,
    )

    import tempfile

    checks: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="phase7_media_") as tmp:
        store = ContentAddressedStore(Path(tmp) / "store")
        service = AssetValidationService(store)

        png = _png_bytes()
        receipt = service.validate(png, extension=".png")
        _record(checks, "valid_png_passes", receipt.content_hash and len(receipt.content_hash) == 64,
                f"png validated, hash={receipt.content_hash[:12]}")
        _record(checks, "publish_content_addressed", store.exists(receipt.content_hash),
                "validated payload is published by content hash")
        _record(checks, "publish_atomic_single_file", len(store.list_hashes()) == 1,
                "store holds exactly one canonical file (no partials)")

        # Extension is never evidence of MIME.
        receipt_txt = service.validate(png, extension=".txt")
        _record(checks, "extension_not_mime_evidence",
                receipt_txt.sniffed_mime == "image/png",
                "PNG bytes validate as image/png even with a .txt extension")

        # Negative controls (plan 02 §22).
        _record(checks, "zero_byte_rejected",
                _raises(lambda: service.validate(b""), MediaValidationError),
                "zero-byte asset is rejected")
        _record(checks, "executable_rejected",
                _raises(lambda: service.validate(b"MZ\x90\x00" + png), MediaValidationError),
                "executable payload is rejected (polyglot/exec)")
        _record(checks, "archive_rejected",
                _raises(lambda: service.validate(b"PK\x03\x04" + png), MediaValidationError),
                "archive payload is rejected")
        _record(checks, "svg_rejected",
                _raises(lambda: service.validate(
                    b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"), MediaValidationError),
                "SVG is banned in Release 0.1")
        _record(checks, "wrong_mime_rejected",
                _raises(lambda: service.validate(b"plain text bytes"), MediaValidationError),
                "non-image payload is rejected")
        _record(checks, "oversize_rejected",
                _raises(lambda: AssetValidationService(store, max_bytes=8).validate(png),
                        MediaValidationError),
                "oversize asset is rejected")
        _record(checks, "pixel_limit_rejected",
                _raises(lambda: AssetValidationService(store, max_pixels=1).validate(_png_bytes(4, 4)),
                        MediaValidationError),
                "decompression/pixel limit is enforced")
        _record(checks, "truncated_image_rejected",
                _raises(lambda: service.validate(png[:20]), MediaValidationError),
                "truncated image fails decoder validation")

        # EXIF sanitization: published bytes must NOT carry embedded metadata.
        jpeg = _jpeg_with_exif()
        exif_receipt = service.validate(jpeg, extension=".jpg")
        stored = store.read(exif_receipt.content_hash) or b""
        _record(checks, "exif_stripped", exif_receipt.exif_stripped,
                "EXIF-bearing JPEG reports exif_stripped=True")
        _record(checks, "exif_not_in_published_bytes", b"Phase 7 test camera" not in stored,
                "sanitized bytes stored in the store carry no EXIF Make tag")

        # Atomicity: a failed validation publishes nothing (store file count
        # is unchanged by the rejected payload).
        files_before = len(store.list_hashes())
        try:
            service.validate(b"MZ\x90\x00" + png)
        except MediaValidationError:
            pass
        _record(checks, "failed_validation_publishes_nothing",
                len(store.list_hashes()) == files_before,
                "invalid payload never produces a partial artifact")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "pipeline": [
            "size_limit", "mime_sniff", "decoder_validation",
            "pixel_limit", "metadata_inspection", "exif_sanitization",
            "content_hash", "publish_content_addressed",
        ],
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Provenance contract receipt (plan 02 §21.3 / §21.4)
# ---------------------------------------------------------------------------


def build_provenance_contract_receipt() -> dict:
    """License fail-closed, likeness human gate, rejected re-selection."""
    from windagent_core.domain.video_production.asset_lifecycle import (
        AssetLifecycleState,
    )
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        LicenseState,
    )
    from windagent_tools.media_assets import (
        AssetProvenanceService,
        LicenseUnknownError,
        LikenessRequiresApprovalError,
        RejectedAssetError,
    )

    checks: list[dict] = []
    svc = AssetProvenanceService(seed="phase7-verifier")
    base = svc.build_record(
        content_hash="a" * 64,
        source_type=AssetSourceType.INTERNET,
        source_url="https://93.184.216.34/asset.png",
        source_provider="fake-catalog",
    )
    _record(checks, "record_starts_validated",
            base.lifecycle_state == AssetLifecycleState.VALIDATED,
            "a built record starts at VALIDATED")
    _record(checks, "record_carries_content_hash", base.content_sha256 == "a" * 64,
            "content hash is recorded")

    unknown = svc.advance_license(base, new_license=LicenseState.UNKNOWN)
    _record(checks, "license_unknown_blocks_auto_approve",
            unknown.lifecycle_state == AssetLifecycleState.LICENSE_UNKNOWN,
            "UNKNOWN license -> LICENSE_UNKNOWN, never auto-approved")

    approved = svc.advance_license(
        unknown, new_license=LicenseState.CREATIVE_COMMONS,
        evidence=["https://creativecommons.org/licenses/by/4.0/"],
    )
    _record(checks, "license_evidence_approves",
            approved.lifecycle_state == AssetLifecycleState.APPROVED,
            "CC evidence moves LICENSE_UNKNOWN -> APPROVED")

    _record(checks, "approve_without_evidence_fails_closed",
            _raises(
                lambda: svc.advance_license(unknown, new_license=LicenseState.LICENSED),
                LicenseUnknownError),
            "approval without evidence is rejected")

    _record(checks, "likeness_requires_human",
            _raises(
                lambda: svc.advance_license(
                    unknown, new_license=LicenseState.LICENSED,
                    evidence=["release form"], real_person_likeness=True),
                LikenessRequiresApprovalError),
            "real-person likeness needs human approval")
    likeness_ok = svc.advance_license(
        unknown, new_license=LicenseState.LICENSED,
        evidence=["signed release"], real_person_likeness=True, human_approved=True,
    )
    _record(checks, "likeness_with_human_approves",
            likeness_ok.lifecycle_state == AssetLifecycleState.APPROVED,
            "likeness with human approval + evidence approves")

    rejected = svc.advance_license(base, new_license=LicenseState.REJECTED)
    _record(checks, "reject_to_rejected",
            rejected.lifecycle_state == AssetLifecycleState.REJECTED,
            "REJECTED license moves VALIDATED -> REJECTED")
    _record(checks, "rejected_asset_cannot_reselect",
            _raises(lambda: svc.advance_license(
                rejected, new_license=LicenseState.LICENSED), RejectedAssetError),
            "rejected asset cannot silently flip to APPROVED")

    bound = svc.bind_to_project(approved)
    _record(checks, "approved_binds_to_project",
            bound.lifecycle_state == AssetLifecycleState.BOUND_TO_PROJECT,
            "APPROVED -> BOUND_TO_PROJECT")
    _record(checks, "unapproved_cannot_bind",
            _raises(lambda: svc.bind_to_project(unknown), Exception),
            "a non-APPROVED asset cannot be bound")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "policy": "docs/video_production/assets/provenance_schema.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. State machine test receipt (plan 02 §21.5)
# ---------------------------------------------------------------------------


def build_state_machine_test_receipt() -> dict:
    """Full transition matrix for the asset lifecycle state machine."""
    from windagent_core.domain.video_production.asset_lifecycle import (
        AssetLifecycleState as S,
        AssetStateMachine,
    )
    from windagent_core.domain.video_production.errors import (
        VideoProductionProtocolError,
    )

    checks: list[dict] = []
    expected = {
        S.DISCOVERED: {S.DOWNLOADED},
        S.DOWNLOADED: {S.VALIDATED},
        S.VALIDATED: {S.LICENSE_UNKNOWN, S.QUARANTINED, S.APPROVED, S.REJECTED},
        S.LICENSE_UNKNOWN: {S.QUARANTINED, S.APPROVED, S.REJECTED},
        # Stage C Phase 6: an untrusted asset can only be promoted by a fresh
        # human review record (metadata alone is never sufficient).
        S.QUARANTINED: {S.APPROVED, S.REJECTED},
        S.APPROVED: {S.BOUND_TO_PROJECT},
        S.REJECTED: {S.APPROVED},
        S.BOUND_TO_PROJECT: set(),
    }

    for state, allowed in expected.items():
        actual = set(AssetStateMachine.allowed_transitions(state))
        _record(checks, f"transition_table_{state.value}",
                actual == allowed,
                f"{state.value} -> {{{', '.join(sorted(a.value for a in allowed))}}}")

    # Forbidden transitions (plan 02 §21.5).
    _record(checks, "download_to_bound_forbidden",
            not AssetStateMachine.can_transition(S.DOWNLOADED, S.BOUND_TO_PROJECT),
            "DOWNLOADED -> BOUND_TO_PROJECT is forbidden (must validate first)")
    _record(checks, "discovered_to_approved_forbidden",
            not AssetStateMachine.can_transition(S.DISCOVERED, S.APPROVED),
            "DISCOVERED -> APPROVED is forbidden")
    _record(checks, "rejected_to_approved_requires_review",
            not AssetStateMachine.can_transition(S.REJECTED, S.APPROVED),
            "REJECTED -> APPROVED without a new review record is forbidden")
    _record(checks, "rejected_to_approved_with_review_allowed",
            AssetStateMachine.can_transition(S.REJECTED, S.APPROVED, new_review_record=True),
            "REJECTED -> APPROVED with a new review record is allowed")
    _record(checks, "bound_is_terminal",
            not AssetStateMachine.can_transition(S.BOUND_TO_PROJECT, S.REJECTED),
            "BOUND_TO_PROJECT is terminal")
    # Stage C Phase 6 fail-closed rules.
    _record(checks, "quarantined_promotion_requires_review_record",
            not AssetStateMachine.can_transition(S.QUARANTINED, S.APPROVED),
            "QUARANTINED -> APPROVED without a fresh human review record is forbidden")
    _record(checks, "quarantined_promotion_with_review_allowed",
            AssetStateMachine.can_transition(S.QUARANTINED, S.APPROVED, new_review_record=True),
            "QUARANTINED -> APPROVED with a fresh human review record is allowed")

    # require_transition raises a typed protocol error.
    _record(checks, "require_transition_raises_typed_error",
            _raises(
                lambda: AssetStateMachine.require_transition(S.DOWNLOADED, S.BOUND_TO_PROJECT),
                VideoProductionProtocolError),
            "require_transition raises VideoProductionProtocolError on illegal move")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "state_count": len(expected),
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 5. E2E package receipt (plan 02 §22 / §24)
# ---------------------------------------------------------------------------


def build_e2e_package_receipt() -> dict:
    """search -> download -> validate -> approve -> bind -> reference ->
    package. Assembles a canonical VideoProductionPackage v1 that carries the
    approved reference asset and passes the Phase 3 validator."""
    from windagent_core.domain.video_production.asset import ReferenceAsset
    from windagent_core.domain.video_production.asset_lifecycle import (
        AssetLifecycleState,
    )
    from windagent_core.domain.video_production.character import CharacterBible
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        CharacterRole,
        LicenseState,
        MediaType,
    )
    from windagent_core.domain.video_production.ids import (
        CharacterId,
        CreativeBriefId,
        DialogueLineId,
        LocationId,
        ReferenceAssetId,
        SceneId,
        ScreenplayId,
        StoryConceptId,
        VideoProjectId,
        ProductionRevisionId,
    )
    from windagent_core.domain.video_production.location import LocationBible
    from windagent_core.domain.video_production.package import (
        PackageProvenance,
        VideoProductionPackage,
    )
    from windagent_core.domain.video_production.scene import Scene
    from windagent_core.domain.video_production.screenplay import (
        CreativeBrief,
        DialogueLine,
        Screenplay,
        StoryConcept,
    )
    from windagent_core.domain.video_production.validation import (
        VideoProductionPackageValidator,
    )
    from windagent_tools.media_assets import (
        AssetDownloadService,
        AssetProvenanceService,
        AssetSearchService,
        AssetValidationService,
        ContentAddressedStore,
        IdentityReferenceBuilder,
    )

    import tempfile

    checks: list[dict] = []
    PUBLIC_IP = "93.184.216.34"
    png = _png_bytes(8, 8)

    with tempfile.TemporaryDirectory(prefix="phase7_e2e_") as tmp:
        store = ContentAddressedStore(Path(tmp) / "store")

        # 1. Search -> DISCOVERED
        search = AssetSearchService(provider=_StaticSearchProvider([
            {"id": "e2e-1", "url": f"https://{PUBLIC_IP}/doudou.png",
             "title": "Doudou concept art"},
        ]))
        results = search.search("doudou concept")
        _record(checks, "e2e_search_discovered",
                len(results) == 1 and results[0].lifecycle_state == AssetLifecycleState.DISCOVERED,
                "search produces exactly one DISCOVERED result with a validated URL")
        source_url = results[0].source_url

        # 2. Download -> DOWNLOADED (fake transport returns the PNG body)
        downloader = AssetDownloadService(
            transport=_FakeRedirectTransport([], body=png),
            max_redirects=2,
        )
        receipt = asyncio.run(downloader.download(source_url))
        _record(checks, "e2e_download_ok", receipt.data == png and receipt.redirect_count == 0,
                "download returns the payload through a single validated hop")

        # 3. Validate -> VALIDATED (ordered pipeline publishes by hash)
        validator = AssetValidationService(store)
        v_receipt = validator.validate(receipt.data, extension=".png")
        _record(checks, "e2e_validate_publishes",
                store.exists(v_receipt.content_hash) and len(v_receipt.content_hash) == 64,
                "validated asset is published to the content-addressed store")

        # 4. Provenance: approve with evidence -> APPROVED -> BOUND
        provenance = AssetProvenanceService(seed="phase7-e2e")
        record = provenance.build_record(
            content_hash=v_receipt.content_hash,
            source_type=AssetSourceType.INTERNET,
            source_url=source_url,
            source_provider="fake-image-catalog",
        )
        approved = provenance.advance_license(
            record, new_license=LicenseState.CREATIVE_COMMONS,
            evidence=["https://creativecommons.org/licenses/by/4.0/"],
        )
        bound = provenance.bind_to_project(approved)
        _record(checks, "e2e_approved_then_bound",
                bound.lifecycle_state == AssetLifecycleState.BOUND_TO_PROJECT,
                "asset ends BOUND_TO_PROJECT with a full provenance record")

        # 5. Reference builder binds identity, never display name.
        character_id = CharacterId("chr_e2e_doudou")
        ref_builder = IdentityReferenceBuilder(seed="phase7-e2e")
        char_ref = ref_builder.build_character(
            character_id=character_id,
            character_name="Doudou",
            revision_id="rev_e2e_1",
            asset_id=bound.asset_id,
            content_hash=bound.content_sha256,
            prompt_version="1.0.0",
            prompt_hash="c" * 64,
        )
        _record(checks, "e2e_reference_binds_identity",
                char_ref.character_id == character_id and char_ref.content_hash == bound.content_sha256,
                "character reference binds stable character_id + revision + content hash")

        # 6. Assemble a canonical package carrying the approved asset.
        brief = CreativeBrief(
            brief_id=CreativeBriefId("brf_e2e_1"),
            title="Doudou Adventure",
            target_duration_seconds=60,
        )
        concept = StoryConcept(
            concept_id=StoryConceptId("con_e2e_1"),
            title="Doudou Adventure",
            premise="A lost fox finds its way home.",
            synopsis="Doudou meets new friends in the forest.",
            themes=["friendship", "courage"],
        )
        scene = Scene(
            scene_id=SceneId("scn_e2e_1"),
            order=1,
            title="Forest",
            location_id=LocationId("loc_e2e_forest"),
            character_ids=[character_id],
            dialogue_line_ids=[DialogueLineId("dlg_e2e_1")],
            action_description="Doudou looks around the forest.",
        )
        screenplay = Screenplay(
            screenplay_id=ScreenplayId("scr_e2e_1"),
            title="Doudou Adventure",
            scenes=[scene],
        )
        dialogue = DialogueLine(
            dialogue_id=DialogueLineId("dlg_e2e_1"),
            scene_id=SceneId("scn_e2e_1"),
            character_id=character_id,
            order=1,
            text="Where am I?",
        )
        character = CharacterBible(
            character_id=character_id,
            name="Doudou",
            role=CharacterRole.LEAD,
            portrait_asset_ids=[ReferenceAssetId(bound.asset_id)],
        )
        location = LocationBible(
            location_id=LocationId("loc_e2e_forest"),
            name="Forest",
            reference_asset_ids=[ReferenceAssetId(bound.asset_id)],
        )
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId(bound.asset_id),
            content_hash=bound.content_sha256,
            media_type=MediaType.IMAGE,
            mime_type="image/png",
            size_bytes=v_receipt.size_bytes,
            source_type=AssetSourceType.INTERNET,
            source_url=source_url,
            license_state=LicenseState.CREATIVE_COMMONS,
        )
        package = VideoProductionPackage(
            schema_version="1.0.0",
            project_id=VideoProjectId("vp_e2e_1"),
            revision_id=ProductionRevisionId("rev_e2e_1"),
            creative_brief=brief,
            story_concept=concept,
            screenplay=screenplay,
            characters=[character],
            locations=[location],
            dialogue=[dialogue],
            assets=[asset],
            provenance=PackageProvenance(created_by="phase7-verifier"),
        )
        issues = VideoProductionPackageValidator.validate(package)
        _record(checks, "e2e_package_valid",
                not issues,
                "package with the approved asset passes the canonical validator")
        serialized = package.serialize()
        reparsed = VideoProductionPackage.deserialize(serialized)
        _record(checks, "e2e_package_round_trip",
                reparsed.content_hash() == package.content_hash(),
                "package serialization round-trips with a stable content hash")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "pipeline": [
            "search_discovered", "download", "validate", "provenance_approve",
            "bind_to_project", "identity_reference", "package_assembly",
        ],
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def main(no_write: bool = False) -> int:
    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)

    security_matrix = build_downloader_security_matrix()
    validation_receipt = build_media_validation_receipt()
    provenance_receipt = build_provenance_contract_receipt()
    state_receipt = build_state_machine_test_receipt()
    e2e_receipt = build_e2e_package_receipt()

    gate_reasons: list[str] = []
    if not security_matrix["all_controls_pass"]:
        gate_reasons.append("downloader security matrix failed")
    if not validation_receipt["all_checks_pass"]:
        gate_reasons.append("media validation pipeline failed")
    if not provenance_receipt["all_checks_pass"]:
        gate_reasons.append("provenance/license contract failed")
    if not state_receipt["all_checks_pass"]:
        gate_reasons.append("asset lifecycle state machine failed")
    if not e2e_receipt["all_checks_pass"]:
        gate_reasons.append("e2e package assembly failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 7,
        "status": overall_status,
        "gate": "VP7_ASSET_PIPELINE_VERIFIED",
        "evidence": [
            {"path": "downloader_security_matrix.json"},
            {"path": "media_validation_receipt.json"},
            {"path": "provenance_contract_receipt.json"},
            {"path": "state_machine_test_receipt.json"},
            {"path": "e2e_package_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase7_assets.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "downloader_security_matrix.json", security_matrix)
        write_json(PHASE_DIR / "media_validation_receipt.json", validation_receipt)
        write_json(PHASE_DIR / "provenance_contract_receipt.json", provenance_receipt)
        write_json(PHASE_DIR / "state_machine_test_receipt.json", state_receipt)
        write_json(PHASE_DIR / "e2e_package_receipt.json", e2e_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(
                overall_status,
                security_matrix,
                validation_receipt,
                provenance_receipt,
                state_receipt,
                e2e_receipt,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_07 artifacts untouched (--no-write keeps the tree clean).")

    print(f"Phase 7 verdict: {overall_status}")
    print(f"  downloader security matrix: {'PASS' if security_matrix['all_controls_pass'] else 'FAIL'}")
    print(f"  media validation: {'PASS' if validation_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  provenance contract: {'PASS' if provenance_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  state machine: {'PASS' if state_receipt['all_checks_pass'] else 'FAIL'}")
    print(f"  e2e package: {'PASS' if e2e_receipt['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(
    status: str,
    security_matrix: dict,
    validation_receipt: dict,
    provenance_receipt: dict,
    state_receipt: dict,
    e2e_receipt: dict,
) -> str:
    return f"""# Phase 7 Report — Asset Pipeline Verified

- **Gate:** `VP7_ASSET_PIPELINE_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Downloader security matrix

- Controls: {security_matrix.get('control_count')}
- All controls pass: {security_matrix.get('all_controls_pass')}

## Media validation

- Ordered pipeline: `size -> mime sniff -> decoder -> pixel -> sanitize -> hash -> publish`
- Checks: {validation_receipt.get('check_count')}
- All checks pass: {validation_receipt.get('all_checks_pass')}

## Provenance contract

- Policy: `docs/video_production/assets/provenance_schema.md`
- Checks: {provenance_receipt.get('check_count')}
- All checks pass: {provenance_receipt.get('all_checks_pass')}

## State machine

- States: {state_receipt.get('state_count')}
- Checks: {state_receipt.get('check_count')}
- All checks pass: {state_receipt.get('all_checks_pass')}

## E2E package

- Pipeline: `search -> download -> validate -> approve -> bind -> reference -> package`
- Checks: {e2e_receipt.get('check_count')}
- All checks pass: {e2e_receipt.get('all_checks_pass')}

## Evidence

- `downloader_security_matrix.json`
- `media_validation_receipt.json`
- `provenance_contract_receipt.json`
- `state_machine_test_receipt.json`
- `e2e_package_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
