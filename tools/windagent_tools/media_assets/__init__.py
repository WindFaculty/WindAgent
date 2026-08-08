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
    CheckSumUnverifiedError,
    CommercialUseRequiresEvidenceError,
    DownloadFailedError,
    EmbeddedExecutableError,
    LicenseUnknownError,
    LikenessRequiresApprovalError,
    MediaValidationError,
    QuarantinedAssetError,
    RejectedAssetError,
    TrademarkRequiresApprovalError,
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
from windagent_tools.media_assets.trust import (
    AssetContentScanner,
    AssetTrustEnforcer,
    ScanVerdict,
    TrustDecision,
)
from windagent_tools.media_assets.references import (
    CharacterReference,
    IdentityReferenceBuilder,
    LocationReference,
    LocationReferenceBuilder,
)
from windagent_tools.media_assets.normalization import (
    AssetNormalizationPipeline,
    AssetNormalizer,
    FakeAssetJobRunner,
    JobInvocation,
    JobResult,
    MeshSnapshot,
    detect_format,
    parse_asset,
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
    "TrademarkRequiresApprovalError",
    "CommercialUseRequiresEvidenceError",
    "CheckSumUnverifiedError",
    "QuarantinedAssetError",
    "EmbeddedExecutableError",
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
    # trust
    "AssetContentScanner",
    "AssetTrustEnforcer",
    "ScanVerdict",
    "TrustDecision",
    # references
    "IdentityReferenceBuilder",
    "LocationReferenceBuilder",
    "CharacterReference",
    "LocationReference",
    # normalization (VP3D Phase 7)
    "AssetNormalizationPipeline",
    "AssetNormalizer",
    "FakeAssetJobRunner",
    "JobInvocation",
    "JobResult",
    "MeshSnapshot",
    "detect_format",
    "parse_asset",
]
