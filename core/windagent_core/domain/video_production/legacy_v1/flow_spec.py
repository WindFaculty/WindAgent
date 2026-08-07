"""
Legacy compatibility — `FlowGenerationSpecification`.

Retired from `windagent_core.domain.video_production.prompt_compiler` during
VP3D Stage A. Kept ONLY so the bounded legacy reader (`ProductionIrMigrator`)
can extract the creative/reference value from old request artifacts during the
compatibility window. It contains NO selectors, cookies, or session state.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.ids import ShotId
from windagent_core.domain.video_production.legacy_v1.enums import GenerationMode
from windagent_core.domain.video_production.legacy_v1.ids import (
    FlowGenerationSpecificationId,
)
from windagent_core.domain.video_production.prompt_compiler import CompiledPrompt


class FlowGenerationSpecification(BaseModel):
    """Legacy request semantics for a generative-video capability (retired)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    spec_id: FlowGenerationSpecificationId
    shot_id: ShotId
    generation_mode: GenerationMode
    prompt: CompiledPrompt
    reference_binding_ids: List[str] = Field(default_factory=list)
    reference_hashes: List[str] = Field(default_factory=list)
    required_inputs: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    model_capability_constraints: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_id": str(self.spec_id),
            "shot_id": str(self.shot_id),
            "generation_mode": self.generation_mode.value,
            "prompt": self.prompt.to_dict(),
            "reference_binding_ids": list(self.reference_binding_ids),
            "reference_hashes": list(self.reference_hashes),
            "required_inputs": list(self.required_inputs),
            "parameters": self.parameters,
            "model_capability_constraints": self.model_capability_constraints,
        }


__all__ = ["FlowGenerationSpecification"]
