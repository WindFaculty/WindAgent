from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId, ProductionRevisionId, SeriesProjectId
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.revision import StudioProductionRevision
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.domain.studio.approval import StudioApprovalDecision

from tests.fakes.studio.orchestrator import FakeStudioOrchestrator

class FakeSeriesRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get(self, series_id: SeriesProjectId) -> Optional[SeriesProject]:
        return self._orchestrator._series.get(str(series_id))

    async def save(self, project: SeriesProject) -> SeriesProject:
        self._orchestrator._series[str(project.series_id)] = project
        return project

    async def list(self, cursor: Optional[str] = None, limit: int = 100) -> List[SeriesProject]:
        items = list(self._orchestrator._series.values())
        return items[:limit]



class FakeEpisodeRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get(self, episode_id: EpisodeId) -> Optional[Episode]:
        return self._orchestrator._episodes.get(str(episode_id))

    async def save(self, episode: Episode) -> Episode:
        self._orchestrator._episodes[str(episode.episode_id)] = episode
        return episode

    async def list_by_series(self, series_id: SeriesProjectId) -> List[Episode]:
        return [e for e in self._orchestrator._episodes.values() if e.series_id == series_id]



class FakeRevisionRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get(self, revision_id: ProductionRevisionId) -> Optional[StudioProductionRevision]:
        return self._orchestrator._revisions.get(str(revision_id))

    async def save(self, revision: StudioProductionRevision) -> StudioProductionRevision:
        self._orchestrator._revisions[str(revision.revision_id)] = revision
        return revision

    async def latest_for_episode(self, episode_id: EpisodeId) -> Optional[StudioProductionRevision]:
        for rev in self._orchestrator._revisions.values():
            if rev.episode_id == episode_id:
                return rev
        return None



class FakeArtifactRepository:
    def __init__(self) -> None:
        self.artifacts: Dict[str, StoryArtifactEnvelope] = {}

    async def get(self, artifact_id: ArtifactId) -> Optional[StoryArtifactEnvelope]:
        return self.artifacts.get(str(artifact_id))

    async def save(self, artifact: StoryArtifactEnvelope) -> StoryArtifactEnvelope:
        self.artifacts[str(artifact.artifact_id)] = artifact
        return artifact

    async def find_by_hash(self, content_hash: str) -> Optional[StoryArtifactEnvelope]:
        for artifact in self.artifacts.values():
            if artifact.content_hash == content_hash:
                return artifact
        return None

    async def list_for_episode(self, episode_id: EpisodeId) -> List[StoryArtifactEnvelope]:
        return [a for a in self.artifacts.values() if a.episode_id == episode_id]



class FakeApprovalRepository:
    def __init__(self, orchestrator: FakeStudioOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def get_policy(self, policy_id: str, policy_version: Optional[str] = None) -> Any:
        return None

    async def save_policy(self, policy: Any) -> Any:
        return policy

    async def record_decision(self, decision: StudioApprovalDecision) -> StudioApprovalDecision:
        self._orchestrator._decisions.append(decision)
        return decision

    async def decisions_for_revision(self, revision_id: ProductionRevisionId) -> List[StudioApprovalDecision]:
        return [d for d in self._orchestrator._decisions if d.revision_id == revision_id]



__all__ = ["FakeSeriesRepository", "FakeEpisodeRepository", "FakeRevisionRepository", "FakeArtifactRepository", "FakeApprovalRepository"]
