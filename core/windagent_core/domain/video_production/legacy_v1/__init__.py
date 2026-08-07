"""
BOUNDED LEGACY COMPATIBILITY LAYER — VP3D Stage A (retirement window).

This package holds the generative-video types that Stage A retires from the
canonical runtime:

- `GenerationMode` / `GenerationModeReasonCode`   (retired from enums.py)
- `GenerationModeDecision`                        (retired from shot_graph.py)
- `FlowGenerationSpecification`                   (retired from prompt_compiler.py)
- `FlowGenerationSpecificationId`                 (retired from ids.py)
- `LegacyGenerationRequest`                       (retired from generation_job.py)

Boundary rules (Stage A §4 / §5):

1. NOT exported from `windagent_core.domain.video_production.__init__` nor
   `windagent_core.__init__` — nothing canonical re-exports these names.
2. NOT imported by the new runtime. The only canonical consumer is the
   bounded legacy reader `ProductionIrMigrator` (and the legacy fixture tests
   that exercise the migration path).
3. A removal/sunset manifest (`SUNSET.md`) documents when these types are
   deleted; the compatibility window ends when all persisted legacy artifacts
   have been migrated.
4. New code must use `ProductionIrDocument` / `ShotExecutionIntent` and the
   engine-neutral IR instead of these types.
"""

from windagent_core.domain.video_production.legacy_v1.enums import (
    GenerationMode,
    GenerationModeReasonCode,
)
from windagent_core.domain.video_production.legacy_v1.decision import (
    GenerationModeDecision,
)
from windagent_core.domain.video_production.legacy_v1.flow_spec import (
    FlowGenerationSpecification,
)
from windagent_core.domain.video_production.legacy_v1.generation_request import (
    LegacyGenerationRequest,
)
from windagent_core.domain.video_production.legacy_v1.ids import (
    FlowGenerationSpecificationId,
)

__all__ = [
    "GenerationMode",
    "GenerationModeReasonCode",
    "GenerationModeDecision",
    "FlowGenerationSpecification",
    "FlowGenerationSpecificationId",
    "LegacyGenerationRequest",
]
