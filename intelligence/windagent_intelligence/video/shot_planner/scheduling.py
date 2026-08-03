"""
Scheduling metadata (plan 03 §14.4).

- Independent shots (no blocking predecessor) are marked parallel-capable.
- A tail-frame dependency waits for the predecessor artifact to be approved
  (recorded on the edge as `required_artifact_type=TAIL_FRAME`).
- A transition waits for BOTH endpoints (recorded as `FULL_CLIP`).
- Sequence retry boundary is explicit (per scene/sequence).
- Concurrency hint never exceeds the production constraint, but the
  orchestration layer keeps the final scheduling authority.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.enums import RequiredArtifactType
from windagent_core.domain.video_production.shot import (
    ShotDependencyGraph,
)
from windagent_core.domain.video_production.shot_graph import ShotScheduling

# Default production constraint cap on parallel shots unless the package's
# creative brief declares a larger one.
DEFAULT_MAX_PARALLEL_SHOTS = 2


class ShotScheduler:
    """Deterministic scheduling metadata per shot (plan §14.4)."""

    def __init__(
        self,
        *,
        max_parallel_shots: int = DEFAULT_MAX_PARALLEL_SHOTS,
    ) -> None:
        self.max_parallel_shots = max_parallel_shots

    def schedule(
        self,
        graph: ShotDependencyGraph,
        *,
        production_max_parallel: Optional[int] = None,
    ) -> List[ShotScheduling]:
        """Compute scheduling metadata for every shot in the graph.

        `parallel_capable` is True when the shot has no blocking predecessor.
        `concurrency_hint` is the number of parallel-capable shots in the same
        sequence, capped by the production constraint (orchestration decides).
        """
        blocking_to = {
            str(d.to_shot_id) for d in graph.dependencies if d.blocking
        }
        waits_by_shot: Dict[str, List[RequiredArtifactType]] = {}
        for dep in graph.dependencies:
            if dep.blocking and dep.required_artifact_type != RequiredArtifactType.NONE:
                waits_by_shot.setdefault(str(dep.to_shot_id), []).append(
                    dep.required_artifact_type
                )

        # Sequence = scene id for Phase 9 (scenes are the retry boundary).
        sequence_of = {str(s.shot_id): str(s.scene_id) for s in graph.shots}
        per_sequence_count: Dict[str, int] = {}
        for shot in graph.shots:
            if str(shot.shot_id) not in blocking_to:
                seq = sequence_of.get(str(shot.shot_id), "default")
                per_sequence_count[seq] = per_sequence_count.get(seq, 0) + 1

        max_parallel = production_max_parallel or self.max_parallel_shots
        max_parallel = max(max_parallel, 1)

        result: List[ShotScheduling] = []
        for shot in sorted(graph.shots, key=lambda s: (str(s.scene_id), s.order)):
            seq = sequence_of.get(str(shot.shot_id), "default")
            parallel_capable = str(shot.shot_id) not in blocking_to
            count = per_sequence_count.get(seq, 1)
            result.append(
                ShotScheduling(
                    shot_id=shot.shot_id,
                    parallel_capable=parallel_capable,
                    concurrency_hint=min(max(1, count), max_parallel),
                    sequence_retry_boundary=seq,
                    waits_for_artifact_types=list(
                        dict.fromkeys(waits_by_shot.get(str(shot.shot_id), []))
                    ),
                )
            )
        return result


__all__ = ["ShotScheduler", "DEFAULT_MAX_PARALLEL_SHOTS"]
