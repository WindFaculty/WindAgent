"""
Unit tests for the VP3D Phase 5 Universal Asset Gateway (providers side).

Covers (Stage C Phase 5 backlog):
- capability matching BEFORE provider calls (typed rejection);
- idempotency: canonical requirement + adapter/version cache hit/miss;
- discover separated from acquire (candidates never usable);
- timeout, retry budget, circuit breaker, cancellation, per-provider
  concurrency;
- credentials never stored (redaction guard fail closed);
- real adapters: local library (traversal guard), internet seam, mesh
  api/mcp unconfigured rejections, generator not enabled;
- fake adapters share contract semantics.
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from windagent_core.domain.video_production.asset_resolution import (
    AssetKind,
    AssetRequirement,
    AssetResolutionRequest,
    AssetResolutionStatus,
    AssetStyle,
    CapabilityRejectedError,
    LicenseConstraint,
    NoCapableAdapterError,
    ProviderAvailability,
    RigRequirement,
    SecretLeakError,
)
from tests.support.waiting import async_deterministic_sleep

from windagent_providers.assets import (
    AssetAdapterRegistry,
    AssetResolutionCache,
    AssetResolver,
    CancellationScope,
    CapabilityMatcher,
    CircuitBreaker,
    ExecutionPolicy,
    FakeGeneratorAdapter,
    FakeGeneratorBackend,
    FakeInternetAcquisitionBackend,
    FakeInternetAssetAdapter,
    FakeInternetSearchBackend,
    FakeLocalAssetAdapter,
    FakeMeshApiAdapter,
    FakeMeshMcpAdapter,
    FutureGeneratorAdapter,
    InternetAssetAdapter,
    LocalAssetAdapter,
    MeshApiAdapter,
    MeshMcpAdapter,
    MeshMcpConfig,
)

CHAR_REQUIREMENT = AssetRequirement(
    kind=AssetKind.CHARACTER,
    description="contract hero",
    style=AssetStyle.THREE_D_CARTOON,
    rig_required=RigRequirement.SKELETAL,
    texture_resolution=2048,
)


def build_resolver(*adapters, **kwargs) -> AssetResolver:
    registry = AssetAdapterRegistry()
    for adapter in adapters:
        registry.register(adapter)
    return AssetResolver(registry, **kwargs)


def trusted_resolver(*adapters, **kwargs) -> AssetResolver:
    """Resolver wired with the REAL Phase 6 trust gate.

    RESOLVED is only reachable through an APPROVE verdict — the gate contract
    introduced by Phase 6 (an UNKNOWN-license / unverified-checksum /
    unverified-commercial-use asset is QUARANTINED, never usable).
    """
    from windagent_tools.media_assets.trust_gate import MediaAssetTrustGate

    kwargs.setdefault("trust", MediaAssetTrustGate())
    return build_resolver(*adapters, **kwargs)


def fake_registry() -> AssetAdapterRegistry:
    registry = AssetAdapterRegistry()
    for adapter in (
        FakeLocalAssetAdapter(),
        FakeInternetAssetAdapter(),
        FakeMeshApiAdapter(),
        FakeMeshMcpAdapter(),
    ):
        registry.register(adapter)
    return registry


class TestCapabilityMatching:
    def test_incapable_provider_is_rejected_before_call(self):
        class AnimationOnly(FakeLocalAssetAdapter):
            adapter_id = "narrow.local"

            def capability(self):
                base = super().capability()
                return base.model_copy(
                    update={"supported_kinds": [AssetKind.ANIMATION_CLIP]}
                )

        narrow = AnimationOnly()
        registry = AssetAdapterRegistry()
        registry.register(narrow)
        resolver = AssetResolver(registry)
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.REJECTED
        assert any(
            a.error_code == CapabilityRejectedError.code for a in result.attempts
        )

    def test_unconfigured_provider_typed_rejection(self):
        registry = AssetAdapterRegistry()
        registry.register(MeshApiAdapter())
        resolver = AssetResolver(registry)
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.REJECTED
        assert result.attempts[0].error_code == CapabilityRejectedError.code
        assert result.attempts[0].provider_id == "mesh.api.v1"

    def test_matcher_rejects_each_unsatisfied_constraint(self):
        matcher = CapabilityMatcher()
        from windagent_core.domain.video_production.asset_resolution import (
            AdapterKind,
            AssetProviderCapability,
            LicenseConstraint,
            ProviderAvailability,
        )

        capability = AssetProviderCapability(
            provider_id="p",
            provider_kind=AdapterKind.LOCAL,
            adapter_version="1.0.0",
            availability=ProviderAvailability.READY,
            supported_kinds=[AssetKind.CHARACTER],
            supported_styles=[AssetStyle.LOW_POLY],
            max_texture_resolution=512,
            license_constraints=[LicenseConstraint.ANY_PERMISSIVE],
        )
        match = matcher.match(CHAR_REQUIREMENT, capability)
        assert not match.matched
        assert any("style" in r for r in match.rejection_reasons)
        assert any("texture" in r for r in match.rejection_reasons)
        assert any("rig" in r for r in match.rejection_reasons)

    def test_license_constraint_matching(self):
        matcher = CapabilityMatcher()
        capability = FakeLocalAssetAdapter().capability()
        req = CHAR_REQUIREMENT.model_copy(
            update={"license_constraint": LicenseConstraint.ATTRIBUTION_REQUIRED}
        )
        assert not matcher.match(req, capability).matched
        req2 = CHAR_REQUIREMENT.model_copy(
            update={"license_constraint": LicenseConstraint.COMMERCIAL_ALLOWED}
        )
        assert matcher.match(req2, capability).matched

    def test_no_capable_adapter_when_none_match(self):
        registry = AssetAdapterRegistry()
        registry.register(MeshApiAdapter())
        resolver = AssetResolver(registry)
        # Mesh API rejects TEXTURE? it supports TEXTURE... use unsupported style:
        result = asyncio.run(
            resolver.discover(
                AssetResolutionRequest(
                    requirement=CHAR_REQUIREMENT.model_copy(
                        update={"kind": AssetKind.ANIMATION_CLIP}
                    )
                )
            )
        )
        assert result.status == AssetResolutionStatus.REJECTED

    def test_unknown_adapter_id_is_typed_rejection(self):
        resolver = AssetResolver(fake_registry())
        result = asyncio.run(
            resolver.discover(
                AssetResolutionRequest(
                    requirement=CHAR_REQUIREMENT,
                    adapter_ids=["does.not.exist"],
                )
            )
        )
        assert result.status == AssetResolutionStatus.REJECTED
        assert result.attempts[0].error_code == NoCapableAdapterError.code


class TestDiscoverAndAcquire:
    def test_discover_returns_candidates_never_assets(self):
        resolver = AssetResolver(fake_registry())
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.DISCOVERED
        assert result.candidates
        assert result.acquired is None
        for candidate in result.candidates:
            assert candidate.requirement_hash == CHAR_REQUIREMENT.canonical_hash

    def test_acquire_promotes_candidate_to_asset(self):
        resolver = trusted_resolver(*[a() for a in (FakeLocalAssetAdapter, FakeInternetAssetAdapter, FakeMeshApiAdapter, FakeMeshMcpAdapter)])
        discovered = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        acquired = asyncio.run(
            resolver.acquire(discovered.candidates[0], AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert acquired.status == AssetResolutionStatus.RESOLVED
        assert acquired.acquired is not None
        assert len(acquired.acquired.content_hash) == 64
        assert acquired.acquisition is not None
        assert acquired.acquisition.license_state == acquired.acquired.license_state
        assert acquired.metadata.get("trust_decision") == "APPROVE"

    def test_acquire_rejects_candidate_for_other_requirement(self):
        resolver = AssetResolver(fake_registry())
        other = CHAR_REQUIREMENT.model_copy(update={"description": "someone else"})
        discovered = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        acquired = asyncio.run(
            resolver.acquire(discovered.candidates[0], AssetResolutionRequest(requirement=other))
        )
        assert acquired.status == AssetResolutionStatus.REJECTED
        assert acquired.acquired is None

    def test_acquire_unknown_provider_rejected(self):
        resolver = AssetResolver(fake_registry())
        from windagent_core.domain.video_production.asset_resolution import AssetCandidate
        from windagent_core.domain.video_production.ids import AssetCandidateId

        bogus = AssetCandidate(
            candidate_id=AssetCandidateId("cand_x"),
            requirement_hash=CHAR_REQUIREMENT.canonical_hash,
            provider_id="ghost.provider",
            adapter_version="0.0.0",
            title="ghost",
        )
        result = asyncio.run(
            resolver.acquire(bogus, AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.REJECTED
        assert result.attempts[0].error_code == NoCapableAdapterError.code


class TestIdempotency:
    def test_discover_cache_hit(self):
        registry = fake_registry()
        calls = []
        original = registry.get("fake.internet.search").discover

        async def counting_discover(request):
            calls.append(1)
            return await original(request)

        registry.get("fake.internet.search").discover = counting_discover  # type: ignore[assignment]
        resolver = AssetResolver(registry)
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        first = asyncio.run(resolver.discover(request))
        second = asyncio.run(resolver.discover(request))
        assert first.cache_hit is False
        assert second.cache_hit is True
        assert len(calls) == 1  # provider NOT re-called on cache hit
        assert [c.title for c in first.candidates] == [c.title for c in second.candidates]

    def test_different_requirement_misses_cache(self):
        resolver = AssetResolver(fake_registry())
        a = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        b = AssetResolutionRequest(
            requirement=CHAR_REQUIREMENT.model_copy(update={"texture_resolution": 4096})
        )
        assert asyncio.run(resolver.discover(a)).cache_hit is False
        assert asyncio.run(resolver.discover(b)).cache_hit is False

    def test_acquire_cache_reuses_artifact(self):
        resolver = trusted_resolver(FakeLocalAssetAdapter())
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        discovered = asyncio.run(resolver.discover(request))
        first = asyncio.run(resolver.acquire(discovered.candidates[0], request))
        second = asyncio.run(resolver.acquire(discovered.candidates[0], request))
        assert second.cache_hit is True
        assert first.acquired.content_hash == second.acquired.content_hash

    def test_cache_key_version_isolated(self):
        registry = AssetAdapterRegistry()
        registry.register(FakeLocalAssetAdapter())
        registry.register(_VersionBump())
        resolver = AssetResolver(registry)
        request_a = AssetResolutionRequest(
            requirement=CHAR_REQUIREMENT, adapter_ids=["fake.local.library"]
        )
        request_b = AssetResolutionRequest(
            requirement=CHAR_REQUIREMENT, adapter_ids=["fake.local.library.v2"]
        )
        # A different adapter version must NEVER reuse another version's cache.
        assert asyncio.run(resolver.discover(request_a)).cache_hit is False
        assert asyncio.run(resolver.discover(request_b)).cache_hit is False
        assert asyncio.run(resolver.discover(request_a)).cache_hit is True

    def test_cache_bounded(self):
        cache = AssetResolutionCache(max_entries=2)
        cache.put("k1", _dummy_result())
        cache.put("k2", _dummy_result())
        cache.put("k3", _dummy_result())
        assert cache.get("k1") is None
        assert cache.get("k2") is not None
        assert cache.get("k3") is not None


class _VersionBump(FakeLocalAssetAdapter):
    adapter_id = "fake.local.library.v2"
    adapter_version = "2.0.0"


def _dummy_result():
    from windagent_core.domain.video_production.asset_resolution import (
        AssetResolutionResult,
    )

    return AssetResolutionResult(
        resolution_id="res_dummy",
        requirement_hash="0" * 64,
        status=AssetResolutionStatus.NOT_FOUND,
    )


class TestExecutionPolicy:
    def test_timeout_returns_typed_timeout(self):
        class Slow(FakeLocalAssetAdapter):
            adapter_id = "slow.local"

            async def discover(self, request):
                await async_deterministic_sleep(5)
                return []

        registry = AssetAdapterRegistry()
        registry.register(Slow())
        resolver = AssetResolver(
            registry,
            policy=ExecutionPolicy(timeout_seconds=0.05, max_retries=0),
        )
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.TIMEOUT
        assert result.attempts[0].error_code == "ASSET_PROVIDER_TIMEOUT"

    def test_retry_budget_respected(self):
        calls = []

        class Flaky(FakeLocalAssetAdapter):
            adapter_id = "flaky.local"

            async def discover(self, request):
                calls.append(1)
                raise ConnectionError("boom")

        registry = AssetAdapterRegistry()
        registry.register(Flaky())
        resolver = AssetResolver(
            registry,
            policy=ExecutionPolicy(max_retries=2, retry_backoff_seconds=0.01),
        )
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert len(calls) == 3  # 1 + 2 retries
        assert result.status in (AssetResolutionStatus.FAILED, AssetResolutionStatus.REJECTED)
        assert result.attempts[0].error_code == "ASSET_RETRY_BUDGET_EXHAUSTED"

    def test_circuit_breaker_opens_after_threshold(self):
        calls = []

        class Crashy(FakeLocalAssetAdapter):
            adapter_id = "crashy.local"

            async def discover(self, request):
                calls.append(1)
                raise RuntimeError("down")

        registry = AssetAdapterRegistry()
        registry.register(Crashy())
        policy = ExecutionPolicy(max_retries=0, retry_backoff_seconds=0.0)
        resolver = AssetResolver(registry, policy=policy)
        breaker = CircuitBreaker("crashy.local", failure_threshold=2, cooldown_seconds=3600)
        resolver._breakers["crashy.local"] = breaker
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        asyncio.run(resolver.discover(request))
        asyncio.run(resolver.discover(request))
        assert breaker.state.value == "OPEN"
        third = asyncio.run(resolver.discover(request))
        assert third.attempts[0].error_code == "ASSET_CIRCUIT_OPEN"
        assert len(calls) == 2  # third call rejected before execution

    def test_cancellation_aborts_and_reports_cancelled(self):
        class Slow(FakeLocalAssetAdapter):
            adapter_id = "slow2.local"

            async def discover(self, request):
                await async_deterministic_sleep(0.5)
                return []

        registry = AssetAdapterRegistry()
        registry.register(Slow())
        resolver = AssetResolver(registry)
        scope = CancellationScope()

        async def run():
            task = asyncio.create_task(
                resolver.discover(
                    AssetResolutionRequest(requirement=CHAR_REQUIREMENT),
                    scope=scope,
                )
            )
            await async_deterministic_sleep(0.05)
            scope.cancel()
            return await task

        result = asyncio.run(run())
        assert result.status == AssetResolutionStatus.CANCELLED

    def test_concurrency_limit_enforced(self):
        inflight = 0
        peak = 0

        class Busy(FakeLocalAssetAdapter):
            adapter_id = "busy.local"

            async def discover(self, request):
                nonlocal inflight, peak
                inflight += 1
                peak = max(peak, inflight)
                await async_deterministic_sleep(0.02)
                inflight -= 1
                return []

        registry = AssetAdapterRegistry()
        registry.register(Busy())
        policy = ExecutionPolicy(per_provider_concurrency=1, max_retries=0)
        resolver = AssetResolver(registry, policy=policy)

        async def run():
            await asyncio.gather(
                *[
                    resolver.discover(
                        AssetResolutionRequest(
                            requirement=CHAR_REQUIREMENT.model_copy(
                                update={"description": f"req {i}"}
                            )
                        )
                    )
                    for i in range(3)
                ]
            )

        asyncio.run(run())
        assert peak == 1

    def test_circuit_breaker_half_open_recovers(self):
        breaker = CircuitBreaker("p", failure_threshold=1, cooldown_seconds=0.01)
        breaker.record_failure()
        assert breaker.state.value == "OPEN"
        # Cooldown elapses -> HALF_OPEN -> success closes the circuit.
        import time as _time

        breaker.opened_at = _time.monotonic() - breaker.cooldown_seconds - 0.001
        assert breaker.allow_call() is True
        assert breaker.state.value == "HALF_OPEN"
        breaker.record_success()
        assert breaker.state.value == "CLOSED"


class TestRedaction:
    def test_request_with_credential_fails_closed(self):
        resolver = AssetResolver(fake_registry())
        request = AssetResolutionRequest(
            requirement=CHAR_REQUIREMENT,
            metadata={"api_key": "sk-12345678901234"},
        )
        with pytest.raises(SecretLeakError):
            asyncio.run(resolver.discover(request))

    def test_receipts_never_contain_credentials(self):
        resolver = AssetResolver(fake_registry())
        request = AssetResolutionRequest(
            requirement=CHAR_REQUIREMENT, metadata={"session": "s1"}
        )
        result = asyncio.run(resolver.discover(request))
        serialized = str(result.model_dump())
        assert "sk-" not in serialized
        assert "api_key" not in serialized

    def test_redaction_guard_accepts_secret_references(self):
        # A secret REFERENCE (env-style) is not a credential value.
        from windagent_providers.assets.redaction import assert_no_credentials

        assert_no_credentials(
            {"api_key_ref": "env:WINDAGENT_MESH_API_KEY"}, context="config"
        )


class TestRealAdapters:
    def test_local_adapter_discovers_and_acquires(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "teapot.glb").write_bytes(b"teapot data")
            # A local asset only becomes RESOLVED when the library index
            # declares license + commercial-use evidence (Phase 6 trust gate).
            (root / "library_index.json").write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "file": "teapot.glb",
                                "title": "Teapot",
                                "kinds": ["CHARACTER", "PROP"],
                                "license_state": "LICENSED",
                                "commercial_use": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            registry = AssetAdapterRegistry()
            registry.register(LocalAssetAdapter(root))
            resolver = trusted_resolver(LocalAssetAdapter(root))
            request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
            result = asyncio.run(resolver.discover(request))
            assert result.status == AssetResolutionStatus.DISCOVERED
            acquired = asyncio.run(resolver.acquire(result.candidates[0], request))
            assert acquired.status == AssetResolutionStatus.RESOLVED
            assert acquired.acquired.source_type.value == "LOCAL_LIBRARY"

    def test_local_adapter_unknown_license_quarantines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "teapot.glb").write_bytes(b"teapot data")
            registry = AssetAdapterRegistry()
            registry.register(LocalAssetAdapter(root))
            resolver = trusted_resolver(LocalAssetAdapter(root))
            request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
            result = asyncio.run(resolver.discover(request))
            acquired = asyncio.run(resolver.acquire(result.candidates[0], request))
            # No license metadata -> UNKNOWN license -> QUARANTINED, never usable.
            assert acquired.status == AssetResolutionStatus.QUARANTINED
            assert acquired.acquired is not None
            assert acquired.metadata.get("trust_decision") == "QUARANTINE"

    def test_local_adapter_blocks_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evil.glb").write_bytes(b"evil")
            registry = AssetAdapterRegistry()
            registry.register(LocalAssetAdapter(root))
            resolver = AssetResolver(registry)
            request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
            result = asyncio.run(resolver.discover(request))
            candidate = result.candidates[0].model_copy(
                update={"metadata": {"relative_path": "../outside.glb"}}
            )
            acquired = asyncio.run(resolver.acquire(candidate, request))
            assert acquired.status == AssetResolutionStatus.REJECTED

    def test_local_adapter_missing_library_fails_closed(self):
        registry = AssetAdapterRegistry()
        registry.register(LocalAssetAdapter(Path("Z:/does/not/exist")))
        resolver = AssetResolver(registry)
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        # Fail closed: an unusable library is a typed rejection, never a
        # fabricated or silently-ignored provider.
        assert result.status == AssetResolutionStatus.REJECTED

    def test_internet_adapter_unconfigured_fails_closed(self):
        registry = AssetAdapterRegistry()
        registry.register(InternetAssetAdapter())
        resolver = AssetResolver(registry)
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.REJECTED
        assert result.attempts[0].error_code == "ASSET_CAPABILITY_REJECTED"

    def test_internet_adapter_with_injected_backends(self):
        registry = AssetAdapterRegistry()
        registry.register(
            InternetAssetAdapter(
                search=FakeInternetSearchBackend(),
                acquisition=FakeInternetAcquisitionBackend(),
            )
        )
        resolver = trusted_resolver(
            InternetAssetAdapter(
                search=FakeInternetSearchBackend(),
                acquisition=FakeInternetAcquisitionBackend(),
            )
        )
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        result = asyncio.run(resolver.discover(request))
        assert result.status == AssetResolutionStatus.DISCOVERED
        acquired = asyncio.run(resolver.acquire(result.candidates[0], request))
        assert acquired.status == AssetResolutionStatus.RESOLVED
        assert acquired.acquired.source_type.value == "INTERNET"

    def test_internet_unknown_license_candidate_quarantines(self):
        # The fake internet adapter discovers TWO candidates: one LICENSED
        # and one UNKNOWN-license. The UNKNOWN one must NEVER come back as
        # RESOLVED — it is quarantined (Phase 6 fail closed).
        registry = AssetAdapterRegistry()
        registry.register(
            InternetAssetAdapter(
                search=FakeInternetSearchBackend(),
                acquisition=FakeInternetAcquisitionBackend(),
            )
        )
        resolver = trusted_resolver(
            InternetAssetAdapter(
                search=FakeInternetSearchBackend(),
                acquisition=FakeInternetAcquisitionBackend(),
            )
        )
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        result = asyncio.run(resolver.discover(request))
        unknown = [c for c in result.candidates if c.license_state.value == "UNKNOWN"]
        assert unknown, "fixture must include an UNKNOWN-license candidate"
        acquired = asyncio.run(resolver.acquire(unknown[0], request))
        assert acquired.status == AssetResolutionStatus.QUARANTINED
        assert acquired.metadata.get("trust_decision") == "QUARANTINE"

    def test_mesh_mcp_requires_config(self):
        registry = AssetAdapterRegistry()
        registry.register(MeshMcpAdapter())
        resolver = AssetResolver(registry)
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.REJECTED
        assert result.attempts[0].error_code == "ASSET_CAPABILITY_REJECTED"
        configured = MeshMcpAdapter(config=MeshMcpConfig(client_ref="env:WINDAGENT_MESH_MCP"))
        assert configured.capability().availability.value == "REQUIRES_CONFIG"
        assert configured.capability().availability != ProviderAvailability.READY

    def test_generator_not_enabled_fails_closed(self):
        registry = AssetAdapterRegistry()
        registry.register(FutureGeneratorAdapter())
        resolver = AssetResolver(registry)
        result = asyncio.run(
            resolver.discover(AssetResolutionRequest(requirement=CHAR_REQUIREMENT))
        )
        assert result.status == AssetResolutionStatus.REJECTED

    def test_generator_with_backend_resolves(self):
        registry = AssetAdapterRegistry()
        registry.register(FutureGeneratorAdapter(backend=FakeGeneratorBackend()))
        resolver = trusted_resolver(FutureGeneratorAdapter(backend=FakeGeneratorBackend()))
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        result = asyncio.run(resolver.discover(request))
        assert result.status == AssetResolutionStatus.DISCOVERED
        acquired = asyncio.run(resolver.acquire(result.candidates[0], request))
        assert acquired.status == AssetResolutionStatus.RESOLVED
        assert acquired.acquired.source_type.value == "GENERATED"
        assert acquired.acquired.metadata.get("model") == "fake-3d-gen-1"

    def test_no_trust_gate_never_resolves(self):
        """Fail closed: a resolver without an injected trust gate can NEVER
        return RESOLVED — untrusted assets are quarantined."""
        resolver = AssetResolver(fake_registry())
        request = AssetResolutionRequest(requirement=CHAR_REQUIREMENT)
        discovered = asyncio.run(resolver.discover(request))
        acquired = asyncio.run(resolver.acquire(discovered.candidates[0], request))
        assert acquired.status == AssetResolutionStatus.QUARANTINED
        assert acquired.metadata.get("trust_decision") == "QUARANTINE"

    def test_fake_generator_disabled_typed_rejection(self):
        adapter = FakeGeneratorAdapter(enabled=False)
        assert adapter.capability().availability == ProviderAvailability.REQUIRES_CONFIG


class TestContractSuiteWiring:
    def test_all_fakes_are_registered(self):
        registry = fake_registry()
        ids = {adapter.adapter_id for adapter in registry.list()}
        assert ids == {
            "fake.local.library",
            "fake.internet.search",
            "fake.mesh.api.v1",
            "fake.mesh.mcp.v1",
        }