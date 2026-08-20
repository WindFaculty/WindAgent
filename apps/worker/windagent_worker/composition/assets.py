"""Guarded asset gateway and normalization composition for Worker."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from windagent_worker.composition.settings import WorkerRuntimeSettings

logger = logging.getLogger("windagent.worker.composition.assets")


@dataclass(frozen=True)
class AssetGatewayBundle:
    asset_resolver: Any
    asset_trust_gate: Any


@dataclass(frozen=True)
class AssetNormalizerBundle:
    asset_normalizer: Any
    normalization_config: Any


class AssetComposer:
    """Compose guarded asset acquisition/trust and normalization adapters."""

    @staticmethod
    def compose_gateway(settings: WorkerRuntimeSettings) -> AssetGatewayBundle:
        from windagent_providers.assets import (
            AssetAdapterRegistry,
            AssetResolver,
            InternetAssetAdapter,
            LocalAssetAdapter,
        )
        from windagent_tools.media_assets.trust_gate import MediaAssetTrustGate

        registry = AssetAdapterRegistry()
        registry.register(LocalAssetAdapter(Path(settings.asset_library_root).resolve()))
        # No search/acquisition backend is injected: Internet stays fail-closed.
        registry.register(InternetAssetAdapter())
        trust_gate = MediaAssetTrustGate()
        return AssetGatewayBundle(
            asset_resolver=AssetResolver(registry, trust=trust_gate),
            asset_trust_gate=trust_gate,
        )

    @staticmethod
    def compose_normalizer(
        settings: WorkerRuntimeSettings,
    ) -> AssetNormalizerBundle:
        from windagent_core.domain.video_production.asset_normalization import (
            NormalizationConfig,
        )
        from windagent_tools.media_assets.normalization import (
            AssetNormalizationPipeline,
            AssetNormalizer,
        )
        from windagent_tools.media_assets.normalization.bundle import (
            AssetBundlePublisher,
        )
        from windagent_tools.media_assets.store import ContentAddressedStore

        artifact_root = Path(settings.artifact_root)
        store = ContentAddressedStore(
            artifact_root / "video_production_3d" / "assets" / "store"
        )
        job_runner = None
        executable_path = settings.blender_executable
        if executable_path and Path(executable_path).is_file():
            try:
                from windagent_tools.production_engines.blender.asset_pipeline import (
                    BlenderAssetJobRunner,
                )

                job_runner = BlenderAssetJobRunner(
                    executable_path=executable_path,
                    artifact_root=str(artifact_root / "video_production_3d"),
                    state_dir=str(
                        artifact_root / "video_production_3d" / "blender_state"
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - optional engine
                logger.warning("Blender asset job runner unavailable: %s", exc)

        pipeline = AssetNormalizationPipeline(
            store=store,
            bundle_publisher=AssetBundlePublisher(
                str(artifact_root / "video_production_3d" / "bundles")
            ),
            job_runner=job_runner,
        )
        return AssetNormalizerBundle(
            asset_normalizer=AssetNormalizer(pipeline),
            normalization_config=NormalizationConfig(),
        )


__all__ = [
    "AssetComposer",
    "AssetGatewayBundle",
    "AssetNormalizerBundle",
]
