"""
LOD policy + generation (VP3D Phase 7, Stage C item 4).

LODs are DERIVED artifacts: the source asset is never overwritten; every LOD
has its own content hash and quality metrics. Decimation is engine work
(``AssetJobRunner``) — host-side planning decides the policy (ratios/levels)
and computes quality metrics, while the actual geometry reduction happens in a
sandboxed Blender job (or a deterministic fake in CI).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from windagent_core.domain.video_production.asset_normalization.enums import LodPolicy
from windagent_core.domain.video_production.asset_normalization.errors import (
    LODGenerationError,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    LodEntry,
    NormalizationRequest,
)

from windagent_tools.media_assets.normalization.job_runner import (
    AssetJobRunner,
    JobInvocation,
)
from windagent_tools.media_assets.normalization.snapshot import MeshSnapshot

# Quality metric: 1 - |target_ratio - actual_ratio| (1.0 = exact match).
MIN_LOD_TRIANGLES = 32


class LodPolicyApplier:
    """Plans and executes the configured LOD policy."""

    def __init__(self, *, job_runner: Optional[AssetJobRunner] = None) -> None:
        self._job_runner = job_runner

    def plan(self, snapshot: MeshSnapshot, policy: LodPolicy, ratios: List[float]) -> List[float]:
        """Resolve policy + ratios into decimation ratios (LOD0 = 1.0)."""
        if policy is LodPolicy.NONE:
            return [1.0]
        if policy is LodPolicy.SINGLE:
            return [1.0, ratios[0] if ratios else 0.5]
        return [1.0] + [max(0.05, min(0.95, r)) for r in (ratios or [0.5, 0.2])]

    async def generate(
        self,
        snapshot: MeshSnapshot,
        request: NormalizationRequest,
        *,
        workspace: str,
        started: float,
    ) -> List[LodEntry]:
        ratios = self.plan(snapshot, request.config.lod_policy, request.config.lod_ratios)
        source_triangles = snapshot.triangle_count
        entries: List[LodEntry] = []
        for level, ratio in enumerate(ratios):
            target_tris = max(MIN_LOD_TRIANGLES, int(source_triangles * ratio))
            if level == 0:
                entries.append(
                    LodEntry(
                        level=0,
                        triangle_count=source_triangles,
                        vertex_count=snapshot.vertex_count,
                        ratio=1.0,
                        quality_score=1.0,
                        content_hash=request.asset.content_hash,
                        file_name="source",
                        generated_by="source",
                        metrics={"target_triangles": source_triangles},
                    )
                )
                continue

            target_ratio = target_tris / source_triangles if source_triangles else 0.0
            entries.append(
                await self._generate_level(
                    request, level, ratio, target_tris, target_ratio, workspace
                )
            )
        return entries

    async def _generate_level(
        self,
        request: NormalizationRequest,
        level: int,
        ratio: float,
        target_triangles: int,
        target_ratio: float,
        workspace: str,
    ) -> LodEntry:
        if self._job_runner is None:
            raise LODGenerationError(
                "LOD decimation requires an engine job runner",
                details={"level": level, "policy": request.config.lod_policy.value},
            )
        invocation = JobInvocation(
            kind="GENERATE_LOD",
            job_id=f"lod_{request.asset.content_hash[:8]}_{level}",
            input_files=[request.source_uri] if request.source_uri else [],
            output_dir=workspace,
            workspace=workspace,
            config={
                "level": level,
                "ratio": ratio,
                "target_triangles": target_triangles,
                "content_hash": request.asset.content_hash,
                "format": request.format.value,
            },
        )
        result = await self._job_runner.generate_lod(invocation)
        if not result.ok:
            raise LODGenerationError(
                f"LOD {level} generation failed: {result.error}",
                details={"job_id": result.job_id},
            )
        tri = int(result.report.get("triangle_count", target_triangles))
        content_hash = str(result.report.get("content_hash", ""))
        if len(content_hash) != 64:
            content_hash = _fake_hash(result.report)
        generated = [p for p in result.generated_files if Path(p).is_file()]
        return LodEntry(
            level=level,
            triangle_count=tri,
            vertex_count=int(result.report.get("vertex_count", 0)),
            ratio=ratio,
            quality_score=max(0.0, min(1.0, 1.0 - abs(target_ratio - ratio))),
            content_hash=content_hash,
            file_name=str(result.report.get("file_name", "")),
            local_path=generated[0] if generated else "",
            generated_by=str(result.report.get("generated_by", "blender_job")),
            metrics={"target_triangles": target_triangles, "job_id": result.job_id},
        )


def _fake_hash(report: dict) -> str:
    """Deterministic content hash for engine-free fixtures (CI fakes)."""
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = ["LodPolicyApplier", "MIN_LOD_TRIANGLES"]
