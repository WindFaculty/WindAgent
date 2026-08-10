"""
Canonical Studio identity contract (studio.contract/v0.1).

Frozen identity set (docs/plans/studio_roadmap_01/01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md):
- ``SeriesProjectId`` — canonical Studio series/project identifier. Existing
  ``VideoProjectId`` values remain readable; conversion is explicit and lossless
  during migration. No second project row is created.
- ``EpisodeId`` — creative Studio episode aggregate ID, distinct from VP3D
  ``EpisodeRunId``/``EpisodeSceneId``/``EpisodeFixture``.
- ``ProductionRevisionId`` — immutable revision lineage ID, reused from the
  existing video-production type with parent/hash semantics preserved.
- ``ArtifactId`` — immutable content-addressed story artifact reference; the
  identity carries the schema version and content hash.
- ``StudioRunId`` — orchestrator-owned DAG/run identity; durable task IDs are
  children of a run and never replace the aggregate ID.
"""

from __future__ import annotations

from windagent_core.domain.types import OpaqueId
from windagent_core.domain.video_production.ids import ProductionRevisionId  # noqa: F401

__all__ = [
    "SeriesProjectId",
    "EpisodeId",
    "ProductionRevisionId",
    "ArtifactId",
    "StudioRunId",
]


class SeriesProjectId(OpaqueId):
    """Identifier for the canonical Studio SeriesProject aggregate."""


class EpisodeId(OpaqueId):
    """Identifier for the creative Studio Episode aggregate."""


class ArtifactId(OpaqueId):
    """Identifier for an immutable content-addressed story artifact."""


class StudioRunId(OpaqueId):
    """Identifier for an orchestrator-owned Studio DAG/run."""
