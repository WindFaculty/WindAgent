"""
Phase 9 — Shot dependency graph and camera planning (plan 03 §12-§16).

The `ShotGraphPlannerService` enriches a Phase 8 `CinematicPlan` into a full
shot graph with typed dependency semantics, deterministic camera decisions
(reason-coded), generation mode decisions (plan §14.3 matrix), scheduling
metadata (plan §14.4) and a deterministic graph hash. It is fully
deterministic — the LLM already proposed the shot plan in Phase 8; this layer
only records rules and validates them. The Director never calls a provider.
"""

from windagent_intelligence.video.shot_planner.camera import CameraPlanner
from windagent_intelligence.video.shot_planner.graph import ShotGraphBuilder
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt
from windagent_intelligence.video.shot_planner.scheduling import ShotScheduler
from windagent_intelligence.video.shot_planner.service import ShotGraphPlannerService

__all__ = [
    "CameraPlanner",
    "ShotGraphBuilder",
    "ShotGraphReceipt",
    "ShotScheduler",
    "ShotGraphPlannerService",
]
