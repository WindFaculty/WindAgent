"""
Unit tests for the VP3D Phase 5 canonical AssetRequirement and DTOs.

Covers (Stage C Phase 5 backlog 1-4):
- standardized asset kind/style/topology/rig/texture/license/budget fields;
- canonical hash is stable and content-scoped (idempotency key);
- cache key scopes the requirement to adapter id + version;
- candidates are DISCOVERED results only (no approved/acquired semantics);
- typed resolution statuses and rejection errors serialize without secrets.
"""

import pytest
from pydantic import ValidationError

from windagent_core.domain.video_production.asset_resolution import (
    AssetCandidate,
    AssetKind,
    AssetProviderCapability,
    AssetRequirement,
    AssetResolutionRequest,
    AssetResolutionResult,
    AssetResolutionStatus,
    AssetStyle,
    CapabilityRejectedError,
    LicenseConstraint,
    ProviderAvailability,
    RigRequirement,
    TopologyPolicy,
)
from windagent_core.domain.video_production.enums import LicenseState
from windagent_core.domain.video_production.ids import AssetCandidateId


def make_requirement(**overrides) -> AssetRequirement:
    base = dict(
        kind=AssetKind.CHARACTER,
        description="hero character",
        style=AssetStyle.THREE_D_CARTOON,
        topology=TopologyPolicy.QUAD_DOMINANT,
        rig_required=RigRequirement.SKELETAL,
        texture_resolution=2048,
        license_constraint=LicenseConstraint.COMMERCIAL_ALLOWED,
    )
    base.update(overrides)
    return AssetRequirement(**base)


class TestCanonicalFields:
    def test_standardized_fields(self):
        req = make_requirement()
        assert req.kind == AssetKind.CHARACTER
        assert req.style == AssetStyle.THREE_D_CARTOON
        assert req.topology == TopologyPolicy.QUAD_DOMINANT
        assert req.rig_required == RigRequirement.SKELETAL
        assert req.texture_resolution == 2048
        assert req.license_constraint == LicenseConstraint.COMMERCIAL_ALLOWED
        assert req.budget.max_polygons == 1_000_000

    def test_budget_bounds_reject_invalid_values(self):
        with pytest.raises(ValidationError):
            make_requirement(texture_resolution=0)
        with pytest.raises(ValidationError):
            make_requirement(texture_resolution=100_000)
        with pytest.raises(ValidationError):
            AssetRequirement(
                kind=AssetKind.PROP,
                description="x",
                budget={"max_polygons": 0},
            )

    def test_unknown_kind_fails_closed(self):
        with pytest.raises(ValidationError):
            make_requirement(kind="HOLOGRAM")

    def test_frozen(self):
        req = make_requirement()
        with pytest.raises(ValidationError):
            req.kind = AssetKind.PROP  # type: ignore[misc]


class TestCanonicalHash:
    def test_hash_is_stable_and_sha256(self):
        a = make_requirement()
        b = make_requirement()
        assert a.canonical_hash == b.canonical_hash
        assert len(a.canonical_hash) == 64

    def test_hash_changes_with_any_standardized_field(self):
        base = make_requirement()
        for changed in (
            dict(style=AssetStyle.STYLIZED),
            dict(texture_resolution=4096),
            dict(rig_required=RigRequirement.FACIAL_CAPABLE),
            dict(kind=AssetKind.PROP),
            dict(license_constraint=LicenseConstraint.UNSPECIFIED),
        ):
            assert make_requirement(**changed).canonical_hash != base.canonical_hash

    def test_hash_ignores_advisory_metadata_and_id(self):
        a = make_requirement(metadata={"session": "abc"})
        b = make_requirement(metadata={"session": "xyz"})
        assert a.canonical_hash == b.canonical_hash

    def test_cache_key_scopes_adapter_and_version(self):
        req = make_requirement()
        assert req.cache_key("local.library", "1.0.0") != req.cache_key("local.library", "1.1.0")
        assert req.cache_key("local.library", "1.0.0") != req.cache_key("internet.search", "1.0.0")
        assert req.cache_key("local.library", "1.0.0") == req.cache_key("local.library", "1.0.0")


class TestCandidateSemantics:
    def test_candidate_is_discovered_only(self):
        candidate = AssetCandidate(
            candidate_id=AssetCandidateId("cand_1"),
            requirement_hash=make_requirement().canonical_hash,
            provider_id="internet.search",
            adapter_version="1.0.0",
            title="web hero",
            license_state=LicenseState.UNKNOWN,
        )
        # Candidates are plain discovery records: no acquired content, no
        # approval state, license stays UNKNOWN by default (fail closed).
        assert candidate.license_state == LicenseState.UNKNOWN

    def test_request_carries_routing_and_policy(self):
        req = AssetResolutionRequest(
            requirement=make_requirement(),
            adapter_ids=["local.library"],
            max_candidates=3,
            timeout_seconds=10.0,
            max_retries=2,
        )
        assert req.adapter_ids == ["local.library"]
        assert req.max_candidates == 3

    def test_result_statuses_cover_discover_and_acquire(self):
        assert AssetResolutionStatus.DISCOVERED.value == "DISCOVERED"
        assert AssetResolutionStatus.RESOLVED.value == "RESOLVED"
        assert AssetResolutionStatus.REJECTED.value == "REJECTED"
        assert AssetResolutionStatus.TIMEOUT.value == "TIMEOUT"
        assert AssetResolutionStatus.CANCELLED.value == "CANCELLED"
        assert AssetResolutionStatus.NOT_FOUND.value == "NOT_FOUND"


class TestCapabilityDto:
    def test_capability_declares_bounds(self):
        cap = AssetProviderCapability(
            provider_id="mesh.api.v1",
            provider_kind="MESH_API",
            adapter_version="1.0.0",
            availability=ProviderAvailability.REQUIRES_CONFIG,
            supported_kinds=[AssetKind.CHARACTER],
            supported_styles=[AssetStyle.STYLIZED],
            max_texture_resolution=4096,
            license_constraints=[LicenseConstraint.COMMERCIAL_ALLOWED],
            max_polygons=5_000_000,
            max_file_bytes=1024 * 1024 * 1024,
        )
        assert cap.provider_kind.value == "MESH_API"
        assert cap.availability.value == "REQUIRES_CONFIG"
        assert cap.max_polygons == 5_000_000


class TestTypedRejectionSerialization:
    def test_capability_rejection_has_typed_code_and_reasons(self):
        error = CapabilityRejectedError(
            "mesh.api.v1",
            ["kind 'CHARACTER' not supported", "rig not supported"],
        )
        assert error.code == "ASSET_CAPABILITY_REJECTED"
        assert error.retryable is False
        assert error.details["provider_id"] == "mesh.api.v1"
        assert len(error.details["reasons"]) == 2
        serialized = error.to_dict()
        assert serialized["code"] == "ASSET_CAPABILITY_REJECTED"
        assert "reasons" in serialized["details"]

    def test_rejection_details_are_sanitized(self):
        from windagent_core.domain.video_production.asset_resolution import (
            AssetResolutionError,
        )

        error = AssetResolutionError(
            "boom",
            details={"api_key": "sk-12345678901234", "provider_id": "p"},
        )
        assert error.details["api_key"] != "sk-12345678901234"
        assert error.details["provider_id"] == "p"

    def test_result_roundtrip_without_secrets(self):
        result = AssetResolutionResult(
            resolution_id="res_1",
            requirement_hash="0" * 64,
            status=AssetResolutionStatus.REJECTED,
        )
        dumped = result.model_dump()
        assert dumped["status"] == "REJECTED"
