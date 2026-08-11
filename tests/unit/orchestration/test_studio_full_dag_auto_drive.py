"""C7 — full-DAG auto-drive: revision seeding, selection replay, lock receipt.

Covers the A-side half co-signed in B9 evidence that the DAG edges cannot
carry by themselves: a fresh episode gets revision 1 at run start,
``bible.generate`` envelopes receive the replayed ``SelectedIdea`` (user
selection wins, live scoring recommendation otherwise), and the
``studio.story.lock`` envelope receives the completed ScreenplayDraft input
plus the A-issued receipt the worker's lock handler requires. These are pure
orchestrator-side contracts; the worker still executes every handler.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    DeriveRevisionCommand,
    SelectIdeaCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId, SeriesProjectId, StudioRunId
from windagent_core.contracts.studio.models import StudioTaskResult, StudioTaskStatus
from windagent_core.domain.story.ideation.models import IdeaCandidate, IdeaCandidateSet, SelectedIdea
from windagent_core.domain.story.review.models import LockedScreenplayReceipt
from windagent_core.domain.studio.approval import ApprovalPolicy
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
from windagent_orchestration.studio.dag import (
    NODE_BIBLE_GENERATE,
    NODE_IDEA_EVALUATE,
    NODE_LOCK,
)
from windagent_orchestration.studio.service import StudioRunService
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.studio_models  # noqa: F401
import windagent_storage.orm.v2_orchestration_models  # noqa: F401
from windagent_storage.studio.run_nodes import SqlStudioRunNodeRepository
from windagent_storage.studio.task_submission import StudioTaskSubmissionAdapter
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork

HASH64 = "a" * 64

NODE_BEATS = "beats.generate"
NODE_OUTLINE = "outline.generate"
NODE_SCREENPLAY = "screenplay.generate"
NODE_REVIEW = "review"


@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await manager.create_tables(BaseORM.metadata)
    yield manager
    await manager.close()


@pytest.fixture
def service(db):
    return StudioRunService(
        db.session_factory,
        StudioTaskSubmissionAdapter(db.session_factory),
        retry_budget=2,
    )


async def _auto_policy(db):
    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.approvals.save_policy(
            ApprovalPolicy(
                policy_id="studio.default",
                policy_version="1",
                checkpoint_to_mode_map={
                    checkpoint: ApprovalMode.AUTO for checkpoint in ApprovalCheckpoint
                },
            )
        )
        await uow.commit()


async def _seed_episode(db, service) -> tuple[SeriesProjectId, EpisodeId]:
    series = await service.create_series(
        CreateSeriesCommand(idempotency_key="c7-s1", title="Chuyện đồng quê")
    )
    episode = await service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="c7-e1",
            series_id=series.series_id,
            title="Thỏ và chiếc diều",
            metadata={
                "creative_brief": {
                    "premise": "Một chú thỏ và chiếc diều giấy.",
                    "language": "vi",
                    "audience_min_age": 5,
                    "audience_max_age": 8,
                    "target_duration_seconds": 240,
                }
            },
        )
    )
    return series.series_id, episode.episode_id


async def _queue_envelope(db, run_id: StudioRunId, node_id: str) -> dict:
    """Read the durable envelope the orchestrator submitted for a node."""
    async with db.session_factory() as session:
        rows = await session.execute(
            text("SELECT facts_json FROM task_runs WHERE session_id = :sid ORDER BY created_at"),
            {"sid": f"run_{run_id}"},
        )
        for (facts_json,) in rows:
            facts = json.loads(facts_json)
            envelope = (facts.get("parameters") or {}).get("studio_envelope")
            if envelope and envelope.get("dag_node_id") == node_id:
                return envelope
    raise AssertionError(f"no envelope for node {node_id}")


async def _node(db, run_id: StudioRunId, node_id: str) -> dict:
    async with db.session_factory() as session:
        return await SqlStudioRunNodeRepository(session).get(run_id, node_id)


async def _complete_node(
    db, run_id: StudioRunId, node_id: str, artifact_types: list[str], contents: list[dict]
):
    """Mark a node succeeded with persisted output artifacts (bypassing the worker)."""
    import hashlib as _hashlib

    node = await _node(db, run_id, node_id)
    task_id = node["task_id"]
    refs = []
    async with StudioUnitOfWork(db.session_factory) as uow:
        run = await uow.runs.get(run_id)
        for artifact_type, content in zip(artifact_types, contents):
            content_hash = _hashlib.sha256(
                f"{artifact_type}:{json.dumps(content, sort_keys=True, ensure_ascii=False)}".encode()
            ).hexdigest()
            artifact = StoryArtifactEnvelope(
                artifact_id=ArtifactId(f"art_{content_hash[:16]}_{artifact_type[:6]}"),
                artifact_type=artifact_type,
                series_id=run["series_id"],
                episode_id=run["episode_id"],
                revision_id=run["dag"].get("revision_id"),
                content_hash=content_hash,
                content=content,
            )
            await uow.artifacts.save(artifact)
            refs.append(
                {
                    "artifact_id": str(artifact.artifact_id),
                    "artifact_type": artifact_type,
                    "content_hash": content_hash,
                }
            )
        await uow.commit()
    service = StudioRunService(
        db.session_factory, StudioTaskSubmissionAdapter(db.session_factory), retry_budget=2
    )
    result = StudioTaskResult(
        task_id=task_id,
        studio_run_id=run_id,
        dag_node_id=node_id,
        status=StudioTaskStatus.SUCCEEDED,
        output_hashes=[r["content_hash"] for r in refs],
        output_artifact_refs=refs,
    )
    await service._reconciler.handle_task_result(result)


def _set() -> IdeaCandidateSet:
    return IdeaCandidateSet(
        candidates=[
            IdeaCandidate(
                candidate_id="cand_tho_dieu",
                title="Thỏ và chiếc diều",
                summary="Chú thỏ con gặp chiếc diều giấy lạc đường.",
                age_fit=0.9,
                brief_adherence=0.9,
            ),
            IdeaCandidate(
                candidate_id="cand_gio_mua",
                title="Cơn gió mùa",
                summary="Cơn gió giúp các bạn nhỏ thả diều.",
                age_fit=0.7,
                brief_adherence=0.6,
            ),
            IdeaCandidate(
                candidate_id="cand_dom_dom",
                title="Đom đóm và ánh trăng",
                summary="Đom đóm tìm bạn trong đêm trăng.",
                age_fit=0.8,
                brief_adherence=0.7,
            ),
        ],
        evaluated=True,
        scoring_rubric_version="rubric-v1",
        recommended_candidate_id="cand_tho_dieu",
    )


# ---------------------------------------------------------------------------
# 1. Revision seeding on a fresh episode
# ---------------------------------------------------------------------------


async def test_start_run_seeds_initial_revision(db, service):
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="c7-r1", episode_id=episode_id)
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
        revision = await uow.revisions.get(episode.current_revision_id)
        run = await uow.runs.get(started.run_id)
    assert episode.current_revision_id is not None
    assert revision is not None
    assert revision.revision_id.value == f"rev_{episode_id.value}_1"
    assert len(revision.content_hash) == 64
    assert run["dag"]["revision_id"] == revision.revision_id.value


async def test_start_run_does_not_reseed_existing_revision(db, service):
    _, episode_id = await _seed_episode(db, service)
    await service.start_or_resume_run(
        StartRunCommand(idempotency_key="c7-r1", episode_id=episode_id)
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
        first = await uow.revisions.get(episode.current_revision_id)
    derived = await service.derive_revision(
        DeriveRevisionCommand(
            idempotency_key="c7-d1",
            episode_id=episode_id,
            series_id=episode.series_id,
            parent_revision_id=first.revision_id,
            new_content_hash=HASH64,
            actor="tester",
        )
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
    assert episode.current_revision_id == derived.revision_id


# ---------------------------------------------------------------------------
# 2. SelectedIdea replay at bible.generate
# ---------------------------------------------------------------------------


async def test_bible_envelope_injects_recommended_selection(db, service):
    await _auto_policy(db)
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="c7-r2", episode_id=episode_id)
    )
    await _complete_node(
        db, started.run_id, "idea.generate", ["IdeaCandidateSet"], [_set().to_canonical_dict()]
    )
    await _complete_node(
        db, started.run_id, NODE_IDEA_EVALUATE, ["IdeaCandidateSet"], [_set().to_canonical_dict()]
    )
    envelope = await _queue_envelope(db, started.run_id, NODE_BIBLE_GENERATE)
    types = {r["artifact_type"] for r in envelope["input_artifact_refs"]}
    assert "SelectedIdea" in types
    sel_ref = next(r for r in envelope["input_artifact_refs"] if r["artifact_type"] == "SelectedIdea")
    async with StudioUnitOfWork(db.session_factory) as uow:
        artifact = await uow.artifacts.get(ArtifactId(sel_ref["artifact_id"]))
    selected = SelectedIdea.model_validate(artifact.content)
    assert selected.candidate_id == "cand_tho_dieu"
    assert artifact.created_by == "orchestrator:auto-selection"


async def test_bible_envelope_user_selection_wins(db, service):
    await _auto_policy(db)
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="c7-r3", episode_id=episode_id)
    )
    # Select BEFORE idea.evaluate completes: with AUTO gates the bible node is
    # dispatched the moment evaluation lands, so the user's selection must
    # already be bound to the revision.
    async with StudioUnitOfWork(db.session_factory) as uow:
        run = await uow.runs.get(started.run_id)
        revision = await uow.revisions.get(run["dag"]["revision_id"])
        revision_hash = revision.content_hash
        revision_version = revision.optimistic_version
    await service.select_idea(
        SelectIdeaCommand(
            idempotency_key="c7-sel1",
            episode_id=episode_id,
            revision_id=run["dag"]["revision_id"],
            candidate_id="cand_gio_mua",
            expected_content_hash=revision_hash,
            expected_optimistic_version=revision_version,
        )
    )
    await _complete_node(
        db, started.run_id, "idea.generate", ["IdeaCandidateSet"], [_set().to_canonical_dict()]
    )
    await _complete_node(
        db, started.run_id, NODE_IDEA_EVALUATE, ["IdeaCandidateSet"], [_set().to_canonical_dict()]
    )
    envelope = await _queue_envelope(db, started.run_id, NODE_BIBLE_GENERATE)
    sel_ref = next(r for r in envelope["input_artifact_refs"] if r["artifact_type"] == "SelectedIdea")
    async with StudioUnitOfWork(db.session_factory) as uow:
        artifact = await uow.artifacts.get(ArtifactId(sel_ref["artifact_id"]))
    selected = SelectedIdea.model_validate(artifact.content)
    assert selected.candidate_id == "cand_gio_mua"


# ---------------------------------------------------------------------------
# 3. Lock receipt issuance after the full chain
# ---------------------------------------------------------------------------


async def test_lock_envelope_carries_draft_input_and_a_issued_receipt(db, service):
    from windagent_core.domain.story.screenplay import ScreenplayDraft

    await _auto_policy(db)
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(idempotency_key="c7-r4", episode_id=episode_id)
    )
    draft = ScreenplayDraft(
        draft_id="draft_c7_kite",
        title="Thỏ và chiếc diều",
        language="vi",
        audience_band="5-8",
        target_duration_seconds=240,
        scenes=[],
    )
    # Drive the whole pipeline to the review node (worker bypassed, artifacts real).
    await _complete_node(
        db, started.run_id, "idea.generate", ["IdeaCandidateSet"], [_set().to_canonical_dict()]
    )
    await _complete_node(
        db, started.run_id, NODE_IDEA_EVALUATE, ["IdeaCandidateSet"], [_set().to_canonical_dict()]
    )
    await _complete_node(
        db, started.run_id, NODE_BIBLE_GENERATE,
        ["StoryBible", "WorldBible", "CharacterCanon"],
        [{"title": "Kinh thánh câu chuyện", "logline": "Thỏ và diều"}, {}, {}],
    )
    await _complete_node(db, started.run_id, NODE_BEATS, ["BeatSheet"], [{"title": "Nhịp truyện"}])
    await _complete_node(db, started.run_id, NODE_OUTLINE, ["EpisodeOutline"], [{"title": "Dàn ý"}])
    await _complete_node(db, started.run_id, NODE_SCREENPLAY, ["ScreenplayDraft"], [draft.to_canonical_dict()])
    await _complete_node(db, started.run_id, NODE_REVIEW, ["ReviewReport"], [{"report_id": "report_1"}])

    envelope = await _queue_envelope(db, started.run_id, NODE_LOCK)
    types = {r["artifact_type"] for r in envelope["input_artifact_refs"]}
    assert types == {"ReviewReport", "ScreenplayDraft"}
    payload = envelope["payload"]
    assert "receipt" in payload
    assert payload["receipt_artifact_id"].startswith("art_")
    receipt = LockedScreenplayReceipt.model_validate(payload["receipt"])
    assert receipt.draft_id.value == "draft_c7_kite"
    assert receipt.state == "READY_FOR_PRODUCTION"
    assert receipt.approval_mode == "AUTO"
    assert receipt.policy_id == "studio.default"
