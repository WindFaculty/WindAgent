"""
Legacy compatibility — `GenerationModeDecision`.

Retired from `windagent_core.domain.video_production.shot_graph` during VP3D
Stage A. Kept ONLY so the bounded legacy reader (`ProductionIrMigrator`) can
map old decision objects onto engine-neutral IR semantics and so legacy
fixtures remain readable during the compatibility window.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.legacy_v1.enums import (
    GenerationMode,
    GenerationModeReasonCode,
)


class GenerationModeDecision(BaseModel):
    """Legacy preferred generation mode + acceptable fallbacks (retired)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    preferred_mode: GenerationMode = GenerationMode.TEXT_TO_VIDEO
    acceptable_fallback_modes: List[GenerationMode] = Field(default_factory=list)
    reason_code: GenerationModeReasonCode = (
        GenerationModeReasonCode.NO_MANDATORY_REFERENCE
    )
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "preferred_mode": self.preferred_mode.value,
            "acceptable_fallback_modes": [
                m.value for m in self.acceptable_fallback_modes
            ],
            "reason_code": self.reason_code.value,
            "rationale": self.rationale,
        }


__all__ = ["GenerationModeDecision"]
