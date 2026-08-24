"""Studio fakes package — re-exports for compatibility."""

from tests.fakes.studio.orchestrator import FakeStudioOrchestrator, FakeRunQueryPort, FakeEventQueryPort
from tests.fakes.studio.repositories import (
    FakeApprovalRepository,
    FakeArtifactRepository,
    FakeEpisodeRepository,
    FakeRevisionRepository,
    FakeSeriesRepository,
)
from tests.fakes.studio.capability import FakeCapabilityPort

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
