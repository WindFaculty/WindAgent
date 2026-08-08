"""Stage F set-dressing planning layer (VP3D Phase 12)."""

from windagent_intelligence.video.set_dressing.environment_builder import (
    ApprovedEnvironment,
    EnvironmentBuilder,
)
from windagent_intelligence.video.set_dressing.planner import (
    SetDressingPlanReceipt,
    SetDressingPlanner,
)
from windagent_intelligence.video.set_dressing.prop_planner import (
    ApprovedProp,
    PropPlacementPlanner,
    SCATTER_ALGORITHM_VERSION,
)
from windagent_intelligence.video.set_dressing.spatial_validator import (
    SpatialConstraintValidator,
)

__all__ = [
    "ApprovedEnvironment",
    "EnvironmentBuilder",
    "ApprovedProp",
    "PropPlacementPlanner",
    "SpatialConstraintValidator",
    "SetDressingPlanner",
    "SetDressingPlanReceipt",
    "SCATTER_ALGORITHM_VERSION",
]
