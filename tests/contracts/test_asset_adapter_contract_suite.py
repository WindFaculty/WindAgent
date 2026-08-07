"""
Shared contract suite applied to every fake adapter (VP3D Phase 5, backlog 7).

Proves all adapters — fake or future real — return the SAME semantics through
the common assertions in ``tests/contracts/asset_adapter_contract.py``.
"""

import pytest

from tests.contracts.asset_adapter_contract import (
    DEFAULT_DESCRIPTION,
    AssetAdapterContractSuite,
)

from windagent_providers.assets import (
    FakeGeneratorAdapter,
    FakeInternetAssetAdapter,
    FakeLocalAssetAdapter,
    FakeMeshApiAdapter,
    FakeMeshMcpAdapter,
    LocalAssetAdapter,
)
from windagent_providers.assets.generator import FutureGeneratorAdapter
from windagent_providers.assets.internet import InternetAssetAdapter
from windagent_providers.assets.mesh_api import MeshApiAdapter
from windagent_providers.assets.mesh_mcp import MeshMcpAdapter


class TestFakeLocalContract(AssetAdapterContractSuite):
    def make_adapter(self):
        return FakeLocalAssetAdapter()


class TestFakeInternetContract(AssetAdapterContractSuite):
    def make_adapter(self):
        return FakeInternetAssetAdapter()


class TestFakeMeshApiContract(AssetAdapterContractSuite):
    def make_adapter(self):
        return FakeMeshApiAdapter()


class TestFakeMeshMcpContract(AssetAdapterContractSuite):
    def make_adapter(self):
        return FakeMeshMcpAdapter()


class TestFakeGeneratorContract(AssetAdapterContractSuite):
    def make_adapter(self):
        return FakeGeneratorAdapter()


class _RealAdapterContractBase(AssetAdapterContractSuite):
    """Real adapters must satisfy the same contract as the fakes.

    Unconfigured adapters are exercised through the fail-closed branch of the
    suite; the local adapter gets a real temp-directory library.
    """

    @pytest.fixture
    def adapter(self):
        raise NotImplementedError

    @pytest.fixture
    def requirement(self):
        from windagent_core.domain.video_production.asset_resolution import (
            AssetKind,
            AssetRequirement,
            AssetStyle,
        )

        return AssetRequirement(
            kind=AssetKind.PROP,
            description="contract test asset",
            style=AssetStyle.STYLIZED,
        )


class TestLocalAdapterContract(_RealAdapterContractBase):
    @pytest.fixture
    def adapter(self, tmp_path):
        (tmp_path / "teapot.glb").write_bytes(b"teapot data")
        return LocalAssetAdapter(tmp_path)


class TestInternetAdapterContract(_RealAdapterContractBase):
    @pytest.fixture
    def adapter(self):
        return InternetAssetAdapter()


class TestMeshApiAdapterContract(_RealAdapterContractBase):
    @pytest.fixture
    def adapter(self):
        return MeshApiAdapter()


class TestMeshMcpAdapterContract(_RealAdapterContractBase):
    @pytest.fixture
    def adapter(self):
        return MeshMcpAdapter()


class TestFutureGeneratorAdapterContract(_RealAdapterContractBase):
    @pytest.fixture
    def adapter(self):
        return FutureGeneratorAdapter()


class TestFutureGeneratorDisabledContract(AssetAdapterContractSuite):
    """Generation disabled must be a typed rejection, never a fabricated asset."""

    def make_adapter(self):
        return FakeGeneratorAdapter(enabled=False)

    def make_requirement(self):
        from windagent_core.domain.video_production.asset_resolution import (
            AssetKind,
            AssetRequirement,
            AssetStyle,
        )

        return AssetRequirement(
            kind=AssetKind.PROP,
            description=DEFAULT_DESCRIPTION,
            style=AssetStyle.STYLIZED,
        )
