"""A3 repository + StudioUnitOfWork tests (studio.contract/v0.1).

Covers the STUDIO_PERSISTENCE_GATE repository surface:
- repository contracts: series/episode/revision/artifact/approval/run round trips,
- dual-read compatibility: canonical rows read first, legacy V2 rows mapped
  through the deterministic backfill identities,
- optimistic concurrency: stale episode/revision writes are rejected,
- unique artifact hash, revision hash-per-episode, approval binding,
  episode-number-per-series enforcement,
- StudioUnitOfWork: atomic commit/rollback, per-aggregate event sequencing,
  outbox publication with per-aggregate ordering, rollback produces no
  events/outbox rows.
"""

from __future__ import annotations


import pytest
import pytest_asyncio
from sqlalchemy import func, select

from windagent_core.contracts.studio.errors import (
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.domain.studio.approval import (
    ApprovalDecisionValue,
    ApprovalPolicy,
    StudioApprovalDecision,
)
from windagent_core.domain.studio.artifact import ArtifactType, StoryArtifactEnvelope
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode, EpisodeState
from windagent_core.domain.studio.revision import (
    StudioProductionRevision,
    StudioRevisionService,
)
from windagent_core.domain.studio.series import SeriesProject
from windagent_core.events.studio import StudioEventCatalog, StudioEventEnvelope

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM, OutboxRecordORM
import windagent_storage.orm.studio_models  # noqa: F401  (registers Studio tables)
from windagent_storage.orm.studio_models import (
    StudioApprovalDecisionORM,
    StudioArtifactORM,
    StudioEventORM,
)
from windagent_storage.studio.repositories import (
    SqlSeriesProjectRepository,
    SqlStudioRevisionRepository,
)
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
from windagent_storage.video_production.video_production_models import (
    ProductionProjectORM,
    ProductionRevisionORM,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


@pytest_asyncio.fixture
async def in_memory_db():
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest_asyncio.fixture
async def seeded(in_memory_db):
    """One series + one episode + one revision committed in the canonical tables."""
    series_id = SeriesProjectId("ser_alpha")
    episode_id = EpisodeId("ep_alpha1")
    series = SeriesProject(series_id=series_id, title="Alpha")
    episode = Episode(
        episode_id=episode_id,
        series_id=series_id,
        title="Alpha 1",
        episode_number=1,
    )
    revision = StudioProductionRevision(
        revision_id=ProductionRevisionId("rev_alpha_1"),
        series_id=series_id,
        episode_id=episode_id,
        creator="tester",
        actor="tester",
        content_hash=HASH_A,
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.series.save(series)
        await uow.episodes.save(episode)
        await uow.revisions.save(revision)
        await uow.commit()
    return {"series": series, "episode": episode, "revision": revision}


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

async def test_series_round_trip_and_list(in_memory_db):
    series = SeriesProject(series_id=SeriesProjectId("ser_one"), title="One")
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.series.save(series)
        await uow.commit()

    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        loaded = await uow.series.get(series.series_id)
        assert loaded == series
        assert await uow.series.get(SeriesProjectId("ser_missing")) is None
        listed = await uow.series.list()
        assert [s.series_id for s in listed] == [series.series_id]


async def test_series_dual_read_legacy_project(in_memory_db):
    async with in_memory_db.session_factory() as session:
        session.add(
            ProductionProjectORM(
                id="proj_legacy_x",
                name="Legacy X",
                status="ACTIVE",
                active_revision_id="",
            )
        )
        await session.commit()

    repo = SqlSeriesProjectRepository(in_memory_db.session_factory())
    loaded = await repo.get(SeriesProjectId("proj_legacy_x"))
    assert loaded is not None
    assert loaded.series_id.value == "proj_legacy_x"  # same id value, no second row
    assert loaded.title == "Legacy X"
    assert loaded.metadata["legacy_project_status"] == "ACTIVE"
    assert loaded.metadata["backfilled"] is True


async def test_series_canonical_row_wins_over_legacy(in_memory_db, seeded):
    async with in_memory_db.session_factory() as session:
        session.add(
            ProductionProjectORM(id="ser_alpha", name="Legacy Alpha", status="DRAFT", active_revision_id="")
        )
        await session.commit()
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        loaded = await uow.series.get(seeded["series"].series_id)
        assert loaded.title == "Alpha"  # canonical row, not the legacy one


# ---------------------------------------------------------------------------
# Episodes — optimistic concurrency
# ---------------------------------------------------------------------------

async def test_episode_save_transition_and_optimistic_guard(in_memory_db, seeded):
    episode = seeded["episode"]
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        current = await uow.episodes.get(episode.episode_id)
        assert current.optimistic_version == 0
        updated = current.transition_to(EpisodeState.IDEA_REVIEW, expected_version=0)
        await uow.episodes.save(updated)
        await uow.commit()

    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        stored = await uow.episodes.get(episode.episode_id)
        assert stored.optimistic_version == 1
        assert stored.state == EpisodeState.IDEA_REVIEW

    # stale write against the old version must be rejected
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        stale = seeded["episode"].transition_to(EpisodeState.IDEA_REVIEW, expected_version=0)
        with pytest.raises(StudioStaleRevisionError):
            await uow.episodes.save(stale)
        await uow.rollback()


async def test_episode_number_unique_per_series(in_memory_db, seeded):
    duplicate = Episode(
        episode_id=EpisodeId("ep_alpha_dup"),
        series_id=seeded["series"].series_id,
        title="Duplicate number",
        episode_number=1,
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.episodes.save(duplicate)
        with pytest.raises(Exception):
            await uow.commit()


async def test_episode_list_by_series(in_memory_db, seeded):
    other = Episode(
        episode_id=EpisodeId("ep_beta1"),
        series_id=SeriesProjectId("ser_beta"),
        title="Beta 1",
        episode_number=1,
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.episodes.save(other)
        await uow.commit()
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        assert [e.episode_id for e in await uow.episodes.list_by_series(seeded["series"].series_id)] == [
            seeded["episode"].episode_id
        ]
        assert [e.episode_id for e in await uow.episodes.list_by_series(SeriesProjectId("ser_beta"))] == [
            other.episode_id
        ]


# ---------------------------------------------------------------------------
# Revisions — lineage, immutability, dual-read
# ---------------------------------------------------------------------------

async def test_revision_derive_save_latest(in_memory_db, seeded):
    parent = seeded["revision"]
    derived = StudioRevisionService.derive_revision(
        parent=parent,
        series_id=parent.series_id,
        episode_id=parent.episode_id,
        new_content_hash=HASH_B,
        creator="tester",
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.revisions.save(derived)
        await uow.commit()

    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        loaded = await uow.revisions.get(derived.revision_id)
        assert loaded.content_hash == HASH_B
        assert loaded.parent_revision_id == parent.revision_id
        latest = await uow.revisions.latest_for_episode(parent.episode_id)
        assert latest.revision_id == derived.revision_id


async def test_revision_optimistic_guard(in_memory_db, seeded):
    locked = StudioRevisionService.lock_revision(revision=seeded["revision"], expected_version=0)
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.revisions.save(locked)
        await uow.commit()
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        stored = await uow.revisions.get(seeded["revision"].revision_id)
        assert stored.locked
        assert stored.optimistic_version == 1
        # stale write with expected_version=0 must fail
        with pytest.raises(StudioStaleRevisionError):
            await uow.revisions.save(
                StudioRevisionService.lock_revision(
                    revision=seeded["revision"], expected_version=0, expected_content_hash=HASH_A
                )
            )


async def test_revision_dual_read_legacy_row(in_memory_db):
    async with in_memory_db.session_factory() as session:
        session.add(
            ProductionRevisionORM(
                id="rev_legacy_9",
                project_id="proj_legacy_9",
                parent_revision_id=None,
                status="LOCKED",
                content_hash=HASH_A,
                sequence=2,
            )
        )
        await session.commit()

    repo = SqlStudioRevisionRepository(in_memory_db.session_factory())
    loaded = await repo.get(ProductionRevisionId("rev_legacy_9"))
    assert loaded is not None
    assert loaded.series_id.value == "proj_legacy_9"
    assert loaded.episode_id.value.startswith("backfill_ep_")
    assert loaded.locked
    assert loaded.content_hash == HASH_A
    assert loaded.metadata["legacy_sequence"] == 2


# ---------------------------------------------------------------------------
# Artifacts — content-addressed uniqueness
# ---------------------------------------------------------------------------

async def test_artifact_save_find_hash_list(in_memory_db, seeded):
    artifact = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.SCREENPLAY_DRAFT,
        series_id=seeded["series"].series_id,
        episode_id=seeded["episode"].episode_id,
        content={"scene": 1, "text": "hello"},
        created_by="tester",
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.artifacts.save(artifact)
        await uow.commit()

    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        by_id = await uow.artifacts.get(artifact.artifact_id)
        assert by_id.content == {"scene": 1, "text": "hello"}
        by_hash = await uow.artifacts.find_by_hash(artifact.content_hash)
        assert by_hash.artifact_id == artifact.artifact_id
        listed = await uow.artifacts.list_for_episode(seeded["episode"].episode_id)
        assert [a.artifact_id for a in listed] == [artifact.artifact_id]


async def test_artifact_save_is_idempotent_and_hash_unique(in_memory_db, seeded):
    first = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.STORY_BIBLE,
        series_id=seeded["series"].series_id,
        episode_id=seeded["episode"].episode_id,
        content={"bible": "v1"},
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.artifacts.save(first)
        await uow.commit()

    # same content, same id -> idempotent
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        again = await uow.artifacts.save(first)
        await uow.commit()
    assert again.artifact_id == first.artifact_id

    # same content hash under a DIFFERENT id -> rejected
    forged = first.model_copy(update={"artifact_id": ArtifactId("art_forged")})
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        with pytest.raises(StudioValidationError):
            await uow.artifacts.save(forged)
        await uow.rollback()


async def test_artifact_hash_unique_index_enforced(in_memory_db, seeded):
    """Raw duplicate insert must fail at the unique index, not just the adapter."""
    a1 = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.IDEA_CANDIDATE_SET,
        series_id=seeded["series"].series_id,
        episode_id=seeded["episode"].episode_id,
        content={"ideas": ["x"]},
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.artifacts.save(a1)
        await uow.commit()
    async with in_memory_db.session_factory() as session:
        session.add(
            StudioArtifactORM(
                artifact_id="art_dupe",
                artifact_type="IdeaCandidateSet",
                series_id=str(seeded["series"].series_id),
                episode_id=str(seeded["episode"].episode_id),
                content_hash=a1.content_hash,
                content_json="{}",
            )
        )
        with pytest.raises(Exception):
            await session.commit()


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

async def test_approval_policy_and_decision_round_trip(in_memory_db, seeded):
    policy = ApprovalPolicy(
        policy_id="pol_strict",
        checkpoint_to_mode_map={ApprovalCheckpoint.SCREENPLAY: ApprovalMode.HUMAN_REQUIRED},
        quality_thresholds={ApprovalCheckpoint.SCREENPLAY: 0.9},
    )
    decision = StudioApprovalDecision(
        approval_id="appr_rev_alpha_1_screenplay_lock_owner",
        aggregate_id=seeded["episode"].episode_id,
        revision_id=seeded["revision"].revision_id,
        artifact_hash=HASH_A,
        checkpoint=ApprovalCheckpoint.SCREENPLAY,
        actor="owner",
        role="OWNER",
        decision=ApprovalDecisionValue.APPROVED,
        reason="looks good",
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.approvals.save_policy(policy)
        await uow.approvals.record_decision(decision)
        await uow.commit()

    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        loaded_policy = await uow.approvals.get_policy("pol_strict")
        assert loaded_policy.requires_human(ApprovalCheckpoint.SCREENPLAY)
        assert loaded_policy.quality_threshold_for(ApprovalCheckpoint.SCREENPLAY) == 0.9
        decisions = await uow.approvals.decisions_for_revision(seeded["revision"].revision_id)
        assert [d.approval_id for d in decisions] == [decision.approval_id]
        assert decisions[0].artifact_hash == HASH_A


async def test_approval_decision_idempotent_replay(in_memory_db, seeded):
    decision = StudioApprovalDecision(
        approval_id="appr_rev_alpha_1_screenplay_lock_owner",
        aggregate_id=seeded["episode"].episode_id,
        revision_id=seeded["revision"].revision_id,
        artifact_hash=HASH_A,
        checkpoint=ApprovalCheckpoint.SCREENPLAY,
        actor="owner",
        decision=ApprovalDecisionValue.APPROVED,
    )
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.approvals.record_decision(decision)
        await uow.commit()
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.approvals.record_decision(decision)  # replay -> idempotent
        await uow.commit()
    async with in_memory_db.session_factory() as session:
        count = (await session.execute(select(func.count()).select_from(StudioApprovalDecisionORM))).scalar()
        assert count == 1


async def test_approval_unique_binding_rejects_different_actor_same_checkpoint(in_memory_db, seeded):
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.approvals.record_decision(
            StudioApprovalDecision(
                approval_id="appr_1",
                aggregate_id=seeded["episode"].episode_id,
                revision_id=seeded["revision"].revision_id,
                artifact_hash=HASH_A,
                checkpoint=ApprovalCheckpoint.SCREENPLAY,
                actor="owner",
                decision=ApprovalDecisionValue.APPROVED,
            )
        )
        await uow.commit()
    async with in_memory_db.session_factory() as session:
        session.add(
            StudioApprovalDecisionORM(
                approval_id="appr_2",
                aggregate_id=str(seeded["episode"].episode_id),
                revision_id=str(seeded["revision"].revision_id),
                artifact_hash=HASH_A,
                checkpoint="SCREENPLAY",
                actor="owner",
                role="OWNER",
                decision="APPROVED",
            )
        )
        with pytest.raises(Exception):
            await session.commit()


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

async def test_run_save_and_get(in_memory_db, seeded):
    run_id = StudioRunId("run_1")
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.runs.save(
            run_id,
            seeded["series"].series_id,
            seeded["episode"].episode_id,
            dag={"nodes": ["n1"]},
            status="RUNNING",
        )
        await uow.commit()
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        loaded = await uow.runs.get(run_id)
        assert loaded["status"] == "RUNNING"
        assert loaded["dag"]["nodes"] == ["n1"]
        assert await uow.runs.get(StudioRunId("run_missing")) is None


# ---------------------------------------------------------------------------
# StudioUnitOfWork — events + outbox atomicity
# ---------------------------------------------------------------------------

def _event(aggregate: str, event_type: str = StudioEventCatalog.EPISODE_CREATED) -> StudioEventEnvelope:
    return StudioEventEnvelope(
        event_type=event_type,
        aggregate_id=aggregate,
        studio_run_id=StudioRunId("run_evt"),
    )


async def test_uow_commit_persists_events_and_outbox(in_memory_db):
    event = _event("agg_a")
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.append_event(event)
        await uow.publish_outbox(event)
        await uow.commit()

    async with in_memory_db.session_factory() as session:
        events = (await session.execute(select(StudioEventORM))).scalars().all()
        assert len(events) == 1
        assert events[0].sequence == 1
        outbox = (await session.execute(select(OutboxRecordORM))).scalars().all()
        assert len(outbox) == 1
        assert outbox[0].aggregate_type == "studio"
        assert outbox[0].sequence_number == 1
        assert outbox[0].deduplication_key == events[0].event_id


async def test_uow_per_aggregate_sequence_ordering(in_memory_db):
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        for _ in range(3):
            await uow.append_event(_event("agg_a"))
        await uow.append_event(_event("agg_b"))
        await uow.commit()

    async with in_memory_db.session_factory() as session:
        rows = (await session.execute(select(StudioEventORM).order_by(StudioEventORM.sequence))).scalars().all()
        by_aggregate = {}
        for row in rows:
            by_aggregate.setdefault(row.aggregate_id, []).append(row.sequence)
        assert by_aggregate["agg_a"] == [1, 2, 3]
        assert by_aggregate["agg_b"] == [1]

    # second UoW continues the sequence
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.append_event(_event("agg_a"))
        await uow.commit()
    async with in_memory_db.session_factory() as session:
        rows = (await session.execute(select(StudioEventORM).where(StudioEventORM.aggregate_id == "agg_a"))).scalars().all()
        assert [r.sequence for r in rows] == [1, 2, 3, 4]


async def test_uow_rollback_produces_no_events_or_outbox(in_memory_db):
    event = _event("agg_a")
    with pytest.raises(RuntimeError):
        async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
            await uow.append_event(event)
            await uow.publish_outbox(event)
            raise RuntimeError("boom")

    async with in_memory_db.session_factory() as session:
        assert (await session.execute(select(func.count()).select_from(StudioEventORM))).scalar() == 0
        assert (await session.execute(select(func.count()).select_from(OutboxRecordORM))).scalar() == 0


async def test_uow_commit_is_atomic_across_repos(in_memory_db, seeded):
    episode_id = EpisodeId("ep_atomic")
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        await uow.episodes.save(
            Episode(episode_id=episode_id, series_id=seeded["series"].series_id, title="Atomic", episode_number=2)
        )
        await uow.append_event(_event("agg_atomic"))
        await uow.commit()

    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        assert (await uow.episodes.get(episode_id)) is not None
        assert await uow.events.latest_sequence(StudioRunId("run_evt")) == 1


async def test_event_query_ports(in_memory_db):
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        for _ in range(5):
            await uow.append_event(_event("agg_q", StudioEventCatalog.ARTIFACT_CREATED))
        await uow.commit()
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        tail = await uow.events.events_after(StudioRunId("run_evt"), after_sequence=2, limit=10)
        assert [e.sequence for e in tail] == [3, 4, 5]
        assert await uow.events.latest_sequence(StudioRunId("run_evt")) == 5
        assert await uow.events.latest_sequence(StudioRunId("run_other")) == 0


async def test_canonical_writes_flag_fails_closed(in_memory_db, monkeypatch):
    monkeypatch.setenv("STUDIO_CANONICAL_WRITES", "0")
    async with StudioUnitOfWork(in_memory_db.session_factory) as uow:
        with pytest.raises(StudioValidationError):
            await uow.series.save(SeriesProject(series_id=SeriesProjectId("ser_x"), title="X"))
        # reads still work
        assert await uow.series.get(SeriesProjectId("ser_x")) is None
