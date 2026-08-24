"""Compatibility shim — re-exports from tests.fakes.studio.

Deprecated: import from tests.fakes.studio instead.
"""

from tests.fakes.studio import (  # noqa: F401
    FakeApprovalRepository,
    FakeArtifactRepository,
    FakeCapabilityPort,
    FakeEpisodeRepository,
    FakeEventQueryPort,
    FakeRevisionRepository,
    FakeRunQueryPort,
    FakeSeriesRepository,
    FakeStudioOrchestrator,
)

__all__ = [
    "FakeStudioOrchestrator",
    "FakeRunQueryPort",
    "FakeEventQueryPort",
    "FakeSeriesRepository",
    "FakeEpisodeRepository",
    "FakeRevisionRepository",
    "FakeArtifactRepository",
    "FakeApprovalRepository",
    "FakeCapabilityPort",
]
