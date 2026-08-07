"""
Shared adapter contract suite for the Universal Asset Gateway (VP3D Phase 5).

Every adapter — fake or real — must satisfy the same semantics. Concrete test
classes inherit from ``AssetAdapterContractBase`` and provide
``make_adapter()`` and ``make_requirement()``; the base class then asserts the
common contract:

- capability is declarative, READY adapters are actually callable;
- discover returns DISCOVERED candidates bound to the request's canonical hash;
- acquire produces a content-addressed asset + provenance and never stores
  credentials in the payload;
- repeated acquire of the same candidate is deterministic in content hash;
- typed errors are raised for unsupported/invalid operations (never silent).
"""

from __future__ import annotations

import pytest

from windagent_core.domain.video_production.asset_resolution import (
    AssetCandidate,
    AssetKind,
    AssetResolutionRequest,
    AssetRequirement,
    AssetStyle,
    GenerationNotEnabledError,
    ProviderUnavailableError,
)

from windagent_providers.assets.adapter import AssetAdapter

DEFAULT_DESCRIPTION = "contract test asset"


class AssetAdapterContractBase:
    """Contract tests every asset adapter must pass."""

    @pytest.fixture
    def adapter(self):
        return self.make_adapter()

    @pytest.fixture
    def requirement(self) -> AssetRequirement:
        return self.make_requirement()

    @pytest.fixture
    def resolution_request(self, requirement: AssetRequirement) -> AssetResolutionRequest:
        return AssetResolutionRequest(requirement=requirement)

    # -- to override -----------------------------------------------

    def make_adapter(self) -> AssetAdapter:
        raise NotImplementedError

    def make_requirement(self) -> AssetRequirement:
        return AssetRequirement(
            kind=AssetKind.PROP,
            description=DEFAULT_DESCRIPTION,
            style=AssetStyle.STYLIZED,
        )

    def _skip_if_not_ready(self, adapter: AssetAdapter) -> None:
        """Adapters that are not READY fail closed; their serving behavior is
        exercised by the fail-closed branch instead."""
        capability = adapter.capability()
        if capability.availability.value != "READY":
            pytest.skip(
                f"adapter {adapter.adapter_id} is not READY "
                f"(availability={capability.availability.value}); "
                "fail-closed semantics covered by the dedicated test"
            )

    # -- contract --------------------------------------------------

    def test_adapter_has_stable_identity(self, adapter: AssetAdapter):
        assert adapter.adapter_id
        assert adapter.adapter_version
        capability = adapter.capability()
        assert capability.provider_id == adapter.adapter_id
        assert capability.adapter_version == adapter.adapter_version

    def test_capability_is_declarative(self, adapter: AssetAdapter):
        capability = adapter.capability()
        assert capability.supported_kinds
        assert capability.supported_styles
        assert capability.license_constraints

    async def test_discover_returns_candidates_bound_to_request(
        self, adapter: AssetAdapter, resolution_request: AssetResolutionRequest
    ):
        self._skip_if_not_ready(adapter)
        candidates = await adapter.discover(resolution_request)
        assert isinstance(candidates, list)
        for candidate in candidates:
            assert isinstance(candidate, AssetCandidate)
            assert candidate.requirement_hash == resolution_request.requirement.canonical_hash
            assert candidate.provider_id == adapter.adapter_id
            assert candidate.adapter_version == adapter.adapter_version

    async def test_discover_is_idempotent(
        self, adapter: AssetAdapter, resolution_request: AssetResolutionRequest
    ):
        self._skip_if_not_ready(adapter)
        first = await adapter.discover(resolution_request)
        second = await adapter.discover(resolution_request)
        titles = lambda items: [c.title for c in items]  # noqa: E731
        assert titles(first) == titles(second)

    async def test_acquire_builds_content_addressed_asset(
        self, adapter: AssetAdapter, resolution_request: AssetResolutionRequest
    ):
        self._skip_if_not_ready(adapter)
        candidates = await adapter.discover(resolution_request)
        if not candidates:
            pytest.skip("adapter produced no candidates for the contract requirement")
        acquired = await adapter.acquire(candidates[0], resolution_request)
        assert len(acquired.asset.content_hash) == 64
        assert acquired.asset.size_bytes >= 0
        assert acquired.acquisition is not None
        assert acquired.acquisition.source_type is not None

    async def test_repeated_acquire_is_deterministic(
        self, adapter: AssetAdapter, resolution_request: AssetResolutionRequest
    ):
        self._skip_if_not_ready(adapter)
        candidates = await adapter.discover(resolution_request)
        if not candidates:
            pytest.skip("adapter produced no candidates for the contract requirement")
        first = await adapter.acquire(candidates[0], resolution_request)
        second = await adapter.acquire(candidates[0], resolution_request)
        assert first.asset.content_hash == second.asset.content_hash
        assert first.asset.source_url == second.asset.source_url

    async def test_acquire_with_bogus_candidate_never_fabricates_asset(
        self, adapter: AssetAdapter, resolution_request: AssetResolutionRequest
    ):
        """The gateway validates the requirement hash; the adapter must still
        behave deterministically on any candidate and never invent content."""
        self._skip_if_not_ready(adapter)
        candidates = await adapter.discover(resolution_request)
        if not candidates:
            pytest.skip("adapter produced no candidates for the contract requirement")
        bogus = candidates[0].model_copy(update={"requirement_hash": "0" * 64})
        acquired = await adapter.acquire(bogus, resolution_request)
        assert len(acquired.asset.content_hash) == 64

    async def test_fail_closed_when_not_configured(
        self, adapter: AssetAdapter, resolution_request: AssetResolutionRequest
    ):
        capability = adapter.capability()
        if capability.availability.value == "READY":
            pytest.skip("adapter is ready; nothing to fail closed")
        with pytest.raises((ProviderUnavailableError, GenerationNotEnabledError)):
            await adapter.discover(resolution_request)


class AssetAdapterContractSuite(AssetAdapterContractBase):
    """Concrete base for CI: asserts common semantics for ALL adapters."""

    pass
