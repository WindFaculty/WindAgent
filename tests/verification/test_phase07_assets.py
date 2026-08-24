"""Unit tests for the Phase 7 media asset pipeline (plan 02 §21-§22).

Covers the SSRF-safe downloader, ordered media validation, provenance
fail-closed contract, asset lifecycle state machine, and identity-safe
reference building. All checks are offline and deterministic.
"""

import pytest

from windagent_core.domain.video_production.asset_lifecycle import (
    AssetLifecycleState,
    AssetStateMachine,
)
from windagent_core.domain.video_production.errors import (
    VideoProductionProtocolError,
)
from windagent_tools.media_assets.errors import (
    LicenseUnknownError,
    LikenessRequiresApprovalError,
    MediaValidationError,
    RejectedAssetError,
    UrlBlockedError,
)


# ---------------------------------------------------------------------------
# State machine (plan 02 §21.5)
# ---------------------------------------------------------------------------


def test_lifecycle_happy_path_transitions():
    state = AssetLifecycleState.DISCOVERED
    for target in (
        AssetLifecycleState.DOWNLOADED,
        AssetLifecycleState.VALIDATED,
        AssetLifecycleState.LICENSE_UNKNOWN,
        AssetLifecycleState.APPROVED,
        AssetLifecycleState.BOUND_TO_PROJECT,
    ):
        assert AssetStateMachine.can_transition(state, target)
        state = target


def test_downloaded_to_bound_forbidden():
    assert not AssetStateMachine.can_transition(
        AssetLifecycleState.DOWNLOADED, AssetLifecycleState.BOUND_TO_PROJECT
    )


def test_rejected_to_approved_requires_review_record():
    assert not AssetStateMachine.can_transition(
        AssetLifecycleState.REJECTED, AssetLifecycleState.APPROVED
    )
    assert AssetStateMachine.can_transition(
        AssetLifecycleState.REJECTED, AssetLifecycleState.APPROVED,
        new_review_record=True,
    )


def test_require_transition_raises_typed_error():
    with pytest.raises(VideoProductionProtocolError):
        AssetStateMachine.require_transition(
            AssetLifecycleState.DISCOVERED, AssetLifecycleState.APPROVED
        )


# ---------------------------------------------------------------------------
# SSRF-safe URL policy (plan 02 §21.1 / §22)
# ---------------------------------------------------------------------------


def _fake_resolver(addresses):
    import socket

    def resolver(host, port):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (addr, port or 80))
            for addr in addresses
        ]

    return resolver


def test_private_ip_literal_blocked():
    from windagent_tools.media_assets.security import validate_download_url

    with pytest.raises(UrlBlockedError):
        validate_download_url("http://192.168.1.10/a.png")


def test_localhost_blocked():
    from windagent_tools.media_assets.security import validate_download_url

    with pytest.raises(UrlBlockedError):
        validate_download_url("http://127.0.0.1/a.png")


def test_ftp_scheme_blocked():
    from windagent_tools.media_assets.security import validate_download_url

    with pytest.raises(UrlBlockedError):
        validate_download_url("ftp://example.com/a.png")


def test_dns_rebinding_blocked():
    from windagent_tools.media_assets.security import validate_download_url

    with pytest.raises(UrlBlockedError):
        validate_download_url(
            "http://rebind.example/a.png", resolver=_fake_resolver(["10.0.0.5"])
        )


def test_mixed_addresses_rejected_even_with_public_one():
    from windagent_tools.media_assets.security import validate_download_url

    with pytest.raises(UrlBlockedError):
        validate_download_url(
            "http://mixed.example/a.png",
            resolver=_fake_resolver(["93.184.216.34", "10.0.0.6"]),
        )


def test_public_host_allowed():
    from windagent_tools.media_assets.security import validate_download_url

    assert validate_download_url(
        "http://good.example/a.png", resolver=_fake_resolver(["93.184.216.34"])
    )


def test_redirect_target_revalidated():
    from windagent_tools.media_assets.security import validate_redirect_target

    with pytest.raises(UrlBlockedError):
        validate_redirect_target("http://10.0.0.7/b.png")


# ---------------------------------------------------------------------------
# Payload classification (plan 02 §21.2 / §22)
# ---------------------------------------------------------------------------


def test_polyglot_png_with_zip_stub_detected():
    from windagent_tools.media_assets.security import classify_payload

    poly = classify_payload(b"\x89PNG\r\n\x1a\n" + b"PK\x03\x04\x14\x00\x00\x00")
    assert poly.looks_polyglot


def test_executable_and_svg_detected():
    from windagent_tools.media_assets.security import classify_payload

    assert classify_payload(b"MZ\x90\x00").is_executable
    assert classify_payload(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>").is_svg


# ---------------------------------------------------------------------------
# Media validation (plan 02 §21.2 / §22)
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    from windagent_tools.media_assets.store import ContentAddressedStore

    return ContentAddressedStore(tmp_path / "store")


def _png_bytes(width=4, height=4, color=(200, 50, 50)) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def test_valid_png_passes_and_publishes(store):
    from windagent_tools.media_assets.validation import AssetValidationService

    svc = AssetValidationService(store)
    receipt = svc.validate(_png_bytes())
    assert len(receipt.content_hash) == 64
    assert store.exists(receipt.content_hash)


def test_extension_is_not_mime_evidence(store):
    from windagent_tools.media_assets.validation import AssetValidationService

    svc = AssetValidationService(store)
    receipt = svc.validate(_png_bytes(), extension=".txt")
    assert receipt.sniffed_mime == "image/png"


def test_zero_byte_and_oversize_rejected(store):
    from windagent_tools.media_assets.validation import AssetValidationService

    svc = AssetValidationService(store)
    with pytest.raises(MediaValidationError):
        svc.validate(b"")
    small = AssetValidationService(store, max_bytes=8)
    with pytest.raises(MediaValidationError):
        small.validate(_png_bytes())


def test_pixel_limit_rejected(store):
    from windagent_tools.media_assets.validation import AssetValidationService

    svc = AssetValidationService(store, max_pixels=1)
    with pytest.raises(MediaValidationError):
        svc.validate(_png_bytes(4, 4))


def test_exif_stripped_before_publish(store):
    import io

    from PIL import Image

    from windagent_tools.media_assets.validation import AssetValidationService

    buf = io.BytesIO()
    img = Image.new("RGB", (4, 4), (50, 200, 50))
    exif = Image.Exif()
    exif[0x010F] = "Phase 7 test camera"
    img.save(buf, format="JPEG", exif=exif)
    jpeg = buf.getvalue()

    svc = AssetValidationService(store)
    receipt = svc.validate(jpeg, extension=".jpg")
    assert receipt.exif_stripped
    stored = store.read(receipt.content_hash) or b""
    assert b"Phase 7 test camera" not in stored


def test_failed_validation_publishes_nothing(store):
    from windagent_tools.media_assets.validation import AssetValidationService

    svc = AssetValidationService(store)
    before = len(store.list_hashes())
    with pytest.raises(MediaValidationError):
        svc.validate(b"MZ\x90\x00" + _png_bytes())
    assert len(store.list_hashes()) == before


# ---------------------------------------------------------------------------
# Provenance / license fail-closed (plan 02 §21.3 / §21.4)
# ---------------------------------------------------------------------------


def test_license_unknown_never_auto_approves():
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        LicenseState,
    )
    from windagent_tools.media_assets.provenance import AssetProvenanceService

    svc = AssetProvenanceService(seed="phase7-unit")
    record = svc.build_record(
        content_hash="a" * 64,
        source_type=AssetSourceType.INTERNET,
        source_url="https://example.com/a.png",
    )
    unknown = svc.advance_license(record, new_license=LicenseState.UNKNOWN)
    assert unknown.lifecycle_state == AssetLifecycleState.LICENSE_UNKNOWN
    with pytest.raises(LicenseUnknownError):
        svc.advance_license(unknown, new_license=LicenseState.LICENSED)


def test_approval_requires_evidence():
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        LicenseState,
    )
    from windagent_tools.media_assets.provenance import AssetProvenanceService

    svc = AssetProvenanceService(seed="phase7-unit")
    record = svc.build_record(
        content_hash="b" * 64, source_type=AssetSourceType.INTERNET
    )
    with pytest.raises(LicenseUnknownError):
        svc.advance_license(record, new_license=LicenseState.LICENSED)


def test_likeness_requires_human_approval():
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        LicenseState,
    )
    from windagent_tools.media_assets.provenance import AssetProvenanceService

    svc = AssetProvenanceService(seed="phase7-unit")
    record = svc.build_record(
        content_hash="c" * 64, source_type=AssetSourceType.INTERNET
    )
    with pytest.raises(LikenessRequiresApprovalError):
        svc.advance_license(
            record, new_license=LicenseState.LICENSED,
            evidence=["release"], real_person_likeness=True,
        )
    approved = svc.advance_license(
        record, new_license=LicenseState.LICENSED,
        evidence=["signed release"], real_person_likeness=True, human_approved=True,
    )
    assert approved.lifecycle_state == AssetLifecycleState.APPROVED


def test_rejected_asset_cannot_reselect():
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        LicenseState,
    )
    from windagent_tools.media_assets.provenance import AssetProvenanceService

    svc = AssetProvenanceService(seed="phase7-unit")
    record = svc.build_record(
        content_hash="d" * 64, source_type=AssetSourceType.INTERNET
    )
    rejected = svc.advance_license(record, new_license=LicenseState.REJECTED)
    assert rejected.lifecycle_state == AssetLifecycleState.REJECTED
    with pytest.raises(RejectedAssetError):
        svc.advance_license(rejected, new_license=LicenseState.LICENSED)


def test_bind_requires_approved():
    from windagent_core.domain.video_production.enums import (
        AssetSourceType,
        LicenseState,
    )
    from windagent_tools.media_assets.provenance import AssetProvenanceService

    svc = AssetProvenanceService(seed="phase7-unit")
    record = svc.build_record(
        content_hash="e" * 64, source_type=AssetSourceType.INTERNET
    )
    with pytest.raises(VideoProductionProtocolError):
        svc.bind_to_project(record)
    approved = svc.advance_license(
        record, new_license=LicenseState.PUBLIC_DOMAIN, evidence=["CC0"]
    )
    bound = svc.bind_to_project(approved)
    assert bound.lifecycle_state == AssetLifecycleState.BOUND_TO_PROJECT


# ---------------------------------------------------------------------------
# Identity-safe reference building (plan 02 §21.4)
# ---------------------------------------------------------------------------


def test_character_reference_binds_stable_identity():
    from windagent_core.domain.video_production.ids import CharacterId
    from windagent_tools.media_assets.references import IdentityReferenceBuilder

    builder = IdentityReferenceBuilder(seed="phase7-unit")
    char_id = CharacterId("chr_doudou")
    ref = builder.build_character(
        character_id=char_id,
        character_name="Doudou",
        revision_id="rev_1",
        asset_id="ast_1",
        content_hash="f" * 64,
        prompt_version="1.0.0",
        prompt_hash="g" * 64,
    )
    assert ref.character_id == char_id
    assert ref.revision_id == "rev_1"


def test_trace_variant_links_back_to_source():
    from windagent_core.domain.video_production.ids import CharacterId
    from windagent_tools.media_assets.references import IdentityReferenceBuilder

    builder = IdentityReferenceBuilder(seed="phase7-unit")
    ref = builder.build_character(
        character_id=CharacterId("chr_doudou"),
        character_name="Doudou",
        revision_id="rev_1",
        asset_id="ast_source",
        content_hash="h" * 64,
    )
    variant = builder.trace_variant(
        ref,
        variant_asset_id="ast_variant",
        variant_hash="i" * 64,
        prompt_version="1.0.0",
        prompt_hash="j" * 64,
    )
    assert variant.asset_id == "ast_variant"
    assert variant.metadata["source_asset_id"] == "ast_source"
