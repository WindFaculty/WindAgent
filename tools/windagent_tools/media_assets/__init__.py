"""
WindAgent Media Asset Pipeline (Phase 7 — VP7_ASSET_PIPELINE_VERIFIED).

Safe acquisition of reference assets (search → download → validate →
provenance → approval → bind) with SSRF-safe download, magic-byte MIME
sniffing, pixel/size/decompression limits, EXIF sanitization, content
addressing, license fail-closed provenance, and identity-safe reference
building.

Policy and lifecycle state machine live in core
(`windagent_core.domain.video_production.asset_lifecycle`); the network /
file / metadata services live here in `tools` (plan 02 §20-§21).
"""

from windagent_tools.media_assets.errors import (
    AssetPipelineError,
    DownloadFailedError,
    LicenseUnknownError,
    LikenessRequiresApprovalError,
    MediaValidationError,
    RejectedAssetError,
    UrlBlockedError,
)
from windagent_tools.media_assets.security import (
    PayloadFingerprint,
    classify_payload,
    is_public_ip,
    sniff_mime,
    validate_download_url,
    validate_host_ips,
    validate_redirect_target,
)
from windagent_tools.media_assets.store import ContentAddressedStore
from windagent_tools.media_assets.search import (
    AssetSearchService,
    SearchProviderPort,
    SearchResult,
)
from windagent_tools.media_assets.download import (
    AssetDownloadService,
    DownloadReceipt,
)
from windagent_tools.media_assets.validation import (
    ALLOWED_IMAGE_MIME,
    AssetValidationService,
    ValidationReceipt,
)
from windagent_tools.media_assets.provenance import (
    AssetProvenanceRecord,
    AssetProvenanceService,
)
from windagent_tools.media_assets.references import (
    CharacterReference,
    IdentityReferenceBuilder,
    LocationReference,
    LocationReferenceBuilder,
)

__all__ = [
    # errors
    "AssetPipelineError",
    "UrlBlockedError",
    "DownloadFailedError",
    "MediaValidationError",
    "LicenseUnknownError",
    "LikenessRequiresApprovalError",
    "RejectedAssetError",
    # security
    "PayloadFingerprint",
    "classify_payload",
    "is_public_ip",
    "sniff_mime",
    "validate_download_url",
    "validate_host_ips",
    "validate_redirect_target",
    # store
    "ContentAddressedStore",
    # search / download / validation
    "AssetSearchService",
    "SearchProviderPort",
    "SearchResult",
    "AssetDownloadService",
    "DownloadReceipt",
    "ALLOWED_IMAGE_MIME",
    "AssetValidationService",
    "ValidationReceipt",
    # provenance
    "AssetProvenanceService",
    "AssetProvenanceRecord",
    # references
    "IdentityReferenceBuilder",
    "LocationReferenceBuilder",
    "CharacterReference",
    "LocationReference",
]
