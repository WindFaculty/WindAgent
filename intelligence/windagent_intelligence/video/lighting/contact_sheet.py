"""
Lighting contact sheet / histogram manifest (VP3D Phase 14, stage_g §4
backlog 6).

Deterministic, engine-neutral numeric proxy of a light rig for the reviewer:
a 16-bin luminance histogram estimate, exposure, contrast and per-light
entries. Real low-sample renders stay in the renderer/tools layer; this
manifest exists so review can happen before Cycles and so the same shape
can be produced for Unreal/Lumen (backlog 7). Confidence stays LOW — the
mood check is a human call (stage_g §6 risk).
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.ids import (
    LightingContactSheetId,
    ShotId,
)
from windagent_core.domain.video_production.lighting import (
    LightRigPlan,
    LightSpec,
)

HISTOGRAM_BINS = 16


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


class ContactSheetEntry(BaseModel):
    """One light's contribution as seen by the reviewer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    color_kelvin: int
    intensity_ratio: float
    casts_shadow: bool


class LightingContactSheetManifest(BaseModel):
    """Deterministic contact sheet + histogram for one rig plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sheet_id: LightingContactSheetId
    shot_id: ShotId
    preset_id: str
    preset_version: str
    exposure_ev: float
    mean_luminance: float = Field(ge=0.0, le=1.0)
    contrast_ratio: float = Field(gt=0.0)
    histogram: List[float] = Field(min_length=HISTOGRAM_BINS,
                                   max_length=HISTOGRAM_BINS)
    entries: List[ContactSheetEntry] = Field(default_factory=list)
    confidence: str = "LOW"     # human visual review required (stage_g §6)
    manifest_hash: str = ""

    def compute_hash(self) -> str:
        payload = json.loads(self.model_dump_json(exclude={"manifest_hash"}))
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ContactSheetBuilder:
    """Builds the deterministic contact sheet for a compiled rig plan."""

    def build(
        self,
        *,
        plan: LightRigPlan,
        sheet_id: LightingContactSheetId,
    ) -> LightingContactSheetManifest:
        exposure_factor = 2.0 ** plan.world.exposure_ev
        total_ratio = sum(l.intensity_ratio for l in plan.lights) or 1.0
        mean = _clamp01(
            (plan.world.environment_strength * 0.25 + total_ratio * 0.10)
            * exposure_factor / (1.0 + exposure_factor))
        contrast = plan.key_fill_ratio
        histogram = self._histogram(mean=mean, contrast=contrast)
        manifest = LightingContactSheetManifest(
            sheet_id=sheet_id,
            shot_id=plan.shot_id,
            preset_id=plan.preset_id,
            preset_version=plan.preset_version,
            exposure_ev=plan.world.exposure_ev,
            mean_luminance=mean,
            contrast_ratio=contrast,
            histogram=histogram,
            entries=[ContactSheetEntry(
                role=l.role.value, color_kelvin=l.color_kelvin,
                intensity_ratio=l.intensity_ratio, casts_shadow=l.casts_shadow)
                for l in plan.lights],
        )
        return manifest.model_copy(
            update={"manifest_hash": manifest.compute_hash()})

    @staticmethod
    def _histogram(*, mean: float, contrast: float) -> List[float]:
        """16-bin luminance histogram proxy, deterministic.

        A bump around `mean` whose spread shrinks as contrast grows (a
        high-contrast rig peaks and crushes; a flat rig spreads evenly).
        """
        spread = max(0.5, 3.0 / contrast)
        center = mean * (HISTOGRAM_BINS - 1)
        bins = []
        for i in range(HISTOGRAM_BINS):
            d = (i - center) / spread
            bins.append(math.exp(-0.5 * d * d))
        total = sum(bins) or 1.0
        return [round(b / total, 6) for b in bins]


__all__ = [
    "HISTOGRAM_BINS",
    "ContactSheetEntry",
    "LightingContactSheetManifest",
    "ContactSheetBuilder",
]
