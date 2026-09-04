"""Typed identifiers for the Studio bounded context.

V2 uses kernel ``Identifier`` (UUID) nominal types — distinct Python types
over the same wire representation so a ``SeriesId`` cannot be accidentally
used where an ``EpisodeId`` is required.  The old repository's prefixed
opaque IDs (``rev_...``, ``art_...``) are preserved as round-trip compatible
strings only at the migration boundary; new V2 rows are pure UUIDs.
"""

from __future__ import annotations

from windagent.kernel.ids import Identifier


class ProjectId(Identifier):
    """Identifier for a top-level project container."""


class SeriesId(Identifier):
    """Identifier for the canonical ``SeriesProject`` aggregate."""


class EpisodeId(Identifier):
    """Identifier for the creative ``Episode`` aggregate."""


class RevisionId(Identifier):
    """Identifier for an immutable ``ProductionRevision`` lineage node."""


class ArtifactId(Identifier):
    """Identifier for an immutable content-addressed story artifact."""


class CharacterId(Identifier):
    """Canonical character identity inside a series."""


class WorldEntryId(Identifier):
    """Identifier for a world-bible entry (location or prop)."""


class StoryboardId(Identifier):
    """Identifier for a storyboard / scene board aggregate."""


class RunId(Identifier):
    """Identifier for an orchestrator-owned Studio run/DAG."""


__all__ = [
    "ArtifactId",
    "CharacterId",
    "EpisodeId",
    "ProjectId",
    "RevisionId",
    "RunId",
    "SeriesId",
    "StoryboardId",
    "WorldEntryId",
]
