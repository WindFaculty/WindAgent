"""
Universal Asset Gateway adapters (VP3D Phase 5, Stage C).

Provider-side implementation of ``AssetResolverPort``:

- adapters: local library, Internet, Mesh API, Mesh MCP, future generator;
- capability matching happens BEFORE any provider call (typed rejection);
- idempotency cache keyed by canonical requirement + adapter/version;
- execution policy: timeout, retry budget, circuit breaker, cancellation,
  per-provider concurrency;
- credentials never stored — only redacted secret references;
- deterministic fake adapters for CI and shared contract tests.

Shared download/validation stays in ``windagent_tools.media_assets`` and is
injected here through structural ports at the composition root.
"""

from windagent_providers.assets.adapter import AcquiredAsset, AssetAdapter
from windagent_providers.assets.cache import AssetResolutionCache
from windagent_providers.assets.capability import (
    CapabilityMatch,
    CapabilityMatcher,
    find_capable_adapters,
)
from windagent_providers.assets.errors import *  # noqa: F401,F403
from windagent_providers.assets.execution import (
    CancellationScope,
    CircuitBreaker,
    CircuitState,
    ExecutionOutcome,
    ExecutionPolicy,
    execute_with_policy,
)
from windagent_providers.assets.fake import (
    FakeGeneratorAdapter,
    FakeGeneratorBackend,
    FakeInternetAcquisitionBackend,
    FakeInternetAssetAdapter,
    FakeInternetSearchBackend,
    FakeLocalAssetAdapter,
    FakeMeshApiAdapter,
    FakeMeshMcpAdapter,
)
from windagent_providers.assets.generator import (
    FutureGeneratorAdapter,
    GeneratorBackendPort,
)
from windagent_providers.assets.internet import (
    InternetAcquisitionPort,
    InternetAssetAdapter,
    InternetSearchPort,
)
from windagent_providers.assets.local import LocalAssetAdapter
from windagent_providers.assets.mesh_api import (
    MeshApiAdapter,
    MeshApiConfig,
    MeshTransportPort,
)
from windagent_providers.assets.mesh_mcp import (
    MeshMcpAdapter,
    MeshMcpConfig,
    MeshMcpTransportPort,
)
from windagent_providers.assets.redaction import (
    assert_no_credentials,
    redact_payload,
)
from windagent_providers.assets.registry import AssetAdapterRegistry
from windagent_providers.assets.resolver import AssetResolver

__all__ = [
    # contract
    "AssetAdapter",
    "AcquiredAsset",
    # capability
    "CapabilityMatch",
    "CapabilityMatcher",
    "find_capable_adapters",
    # cache / execution
    "AssetResolutionCache",
    "CancellationScope",
    "CircuitBreaker",
    "CircuitState",
    "ExecutionOutcome",
    "ExecutionPolicy",
    "execute_with_policy",
    # adapters
    "LocalAssetAdapter",
    "InternetAssetAdapter",
    "InternetSearchPort",
    "InternetAcquisitionPort",
    "MeshApiAdapter",
    "MeshApiConfig",
    "MeshTransportPort",
    "MeshMcpAdapter",
    "MeshMcpConfig",
    "MeshMcpTransportPort",
    "FutureGeneratorAdapter",
    "GeneratorBackendPort",
    # fakes (CI)
    "FakeLocalAssetAdapter",
    "FakeInternetAssetAdapter",
    "FakeMeshApiAdapter",
    "FakeMeshMcpAdapter",
    "FakeGeneratorAdapter",
    "FakeInternetSearchBackend",
    "FakeInternetAcquisitionBackend",
    "FakeGeneratorBackend",
    # registry / gateway
    "AssetAdapterRegistry",
    "AssetResolver",
    # redaction guard
    "assert_no_credentials",
    "redact_payload",
]
