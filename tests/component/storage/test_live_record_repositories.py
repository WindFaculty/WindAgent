"""Live Record repository tests (live_record.contract/v0.1, Phase 1).

Covers the persistence surface over in-memory SQLite:
- plan round trip with JSON value objects (scenes/actions/profile),
- optimistic concurrency: stale writes rejected on guarded version,
- per-episode preparation revision allocation (unique (episode, revision)),
- takes by plan, segments by take ordered by index,
- append-only event timeline with monotonic per-take ``seq``,
- director session upsert.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from windagent_core.contracts.live_record.errors import LiveRecordValidationError
from windagent_core.contracts.live_record.ids import (
    DirectorSessionId,
    LiveExecutionPlanId,
    RecordingTakeId,
)
from windagent_core.domain.live_record.plan import (
    ExpectedVisualState,
    LiveExecutionPlan,
    PreparedAction,
    RecordingCue,
    RecordingScene,
)
from windagent_core.domain.live_record.runtime import (
    DirectorSessionRecord,
    RecordingEventRecord,
    RecordingSegmentRecord,
    RecordingTakeRecord,
)

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
import windagent_storage.orm.live_record_models  # noqa: F401  (registers Live Record tables)
from windagent_storage.live_record.repositories import (
    create_sql_director_session_repository,
    create_sql_live_execution_plan_repository,
    create_sql_recording_event_repository,
    create_sql_recording_segment_repository,
    create_sql_recording_take_repository,
)

HASH_A = "a" * 64


@pytest_asyncio.fixture
async def in_memory_db():
    db_manager = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)
    yield db_manager
    await db_manager.close()


@pytest_asyncio.fixture
async def repos(in_memory_db):
    """Repository bundle bound to one fresh session per test via the factory.

    The session runs ``autoflush=False`` (house convention): repositories only
    stage changes, so tests commit explicitly between write and read phases.
    """
    async with in_memory_db.session_factory() as session:
        yield {
            "session": session,
            "plans": create_sql_live_execution_plan_repository(session),
            "takes": create_sql_recording_take_repository(session),
            "segments": create_sql_recording_segment_repository(session),
            "events": create_sql_recording_event_repository(session),
            "directors": create_sql_director_session_repository(session),
        }


async def _commit(repos) -> None:
    await repos["session"].commit()


def _plan(plan_no: int = 1, preparation_revision: int = 1) -> LiveExecutionPlan:
    state = ExpectedVisualState(state_id="st_build_green", test_should_pass=True)
    cue = RecordingCue(cue_id=f"cue_{plan_no}_1", scene_id="sc_1", index=0, expected_state=state)
    return LiveExecutionPlan.model_validate(
        {
            "plan_id": LiveExecutionPlanId(f"plan_alpha_{plan_no}"),
            "episode_id": "ep_alpha",
            "episode_revision_id": "rev_alpha_7",
            "preparation_revision": preparation_revision,
            "scenes": [RecordingScene.model_validate({"scene_id": "sc_1", "index": 0, "cues": [cue]})],
            "actions": [
                PreparedAction.model_validate(
                    {
                        "action_id": f"act_{plan_no}_1",
                        "type": "CODE_PLAYBACK",
                        "scene_id": "sc_1",
                        "payload_ref": f"artifact://bundles/act_{plan_no}_1.py",
                        "idempotency_key": f"idem_{plan_no}",
                        "expected_after": state,
                    }
                )
            ],
        }
    )


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


async def test_plan_round_trip_preserves_value_objects(repos):
    plans = repos["plans"]
    original = _plan().mark_prepared().mark_validated()

    await plans.save(original)
    await _commit(repos)
    loaded = await plans.get(LiveExecutionPlanId("plan_alpha_1"))

    assert loaded is not None
    assert loaded == original
    assert loaded.plan_hash == original.plan_hash
    assert loaded.recording_profile == original.recording_profile
    assert loaded.scenes[0].cues[0].expected_state.state_id == "st_build_green"
    assert loaded.actions[0].payload_ref == "artifact://bundles/act_1_1.py"
    assert await plans.get(LiveExecutionPlanId("plan_missing")) is None


async def test_plan_guarded_update_rejects_stale_write(repos):
    plans = repos["plans"]
    v0 = _plan()
    await plans.save(v0)

    writer_a = v0.mark_prepared()          # optimistic_version -> 1
    writer_b = v0.mark_prepared()          # same base version -> conflict
    await plans.save(writer_a)
    await _commit(repos)

    with pytest.raises(LiveRecordValidationError, match="optimistic version"):
        await plans.save(writer_b)


async def test_next_preparation_revision_increments(repos):
    plans = repos["plans"]
    assert await plans.next_preparation_revision("ep_alpha") == 1
    await plans.save(_plan(plan_no=1, preparation_revision=1))
    await _commit(repos)
    assert await plans.next_preparation_revision("ep_alpha") == 2
    await plans.save(_plan(plan_no=2, preparation_revision=2).mark_prepared())
    await _commit(repos)
    assert await plans.next_preparation_revision("ep_alpha") == 3


async def test_list_by_episode_orders_by_revision_desc(repos):
    plans = repos["plans"]
    await plans.save(_plan(plan_no=1, preparation_revision=1))
    await plans.save(_plan(plan_no=2, preparation_revision=2).mark_prepared())
    await _commit(repos)

    listed = await plans.list_by_episode("ep_alpha")
    assert [p.preparation_revision for p in listed] == [2, 1]


# ---------------------------------------------------------------------------
# Takes / Segments
# ---------------------------------------------------------------------------


async def test_take_round_trip_and_list_by_plan(repos):
    plans = repos["plans"]
    takes = repos["takes"]
    frozen = _plan().mark_prepared().mark_validated().freeze()
    await plans.save(frozen)
    await _commit(repos)

    take = RecordingTakeRecord(
        take_id=str(RecordingTakeId("take_alpha_1")),
        execution_plan_id=str(frozen.plan_id),
        execution_plan_hash=frozen.plan_hash,
        episode_id=frozen.episode_id,
        session_status="RECORDING",
    )
    await takes.save(take)
    await _commit(repos)
    loaded = await takes.get(RecordingTakeId("take_alpha_1"))
    assert loaded == take

    ended = RecordingTakeRecord.model_validate(
        {**take.model_dump(mode="json"), "session_status": "COMPLETED", "ended_at": None}
    ).model_copy(update={"optimistic_version": 1})
    await takes.save(ended)
    await _commit(repos)
    listed = await takes.list_by_plan(str(frozen.plan_id))
    assert len(listed) == 1 and listed[0].session_status == "COMPLETED"


async def test_segments_ordered_by_index(repos):
    segments = repos["segments"]
    for idx in (2, 0, 1):
        await segments.save(
            RecordingSegmentRecord(
                segment_id=f"seg_{idx}",
                take_id="take_alpha_1",
                segment_index=idx,
                file_token=f"tok://segments/seg_{idx}.mkv",
                duration_sec=300.0,
            )
        )
    listed = await segments.list_by_take("take_alpha_1")
    assert [s.segment_index for s in listed] == [0, 1, 2]
    assert all(s.file_token.startswith("tok://") for s in listed)


# ---------------------------------------------------------------------------
# Events — append-only timeline
# ---------------------------------------------------------------------------


async def test_events_append_assigns_monotonic_seq(repos):
    events = repos["events"]
    seqs = []
    for i, etype in enumerate(("TAKE_STARTED", "CUE_ENTERED", "ACTION_EXECUTED")):
        appended = await events.append(
            RecordingEventRecord(
                take_id="take_alpha_1",
                event_type=etype,
                t=float(i),
                cue_id="cue_1_1" if etype == "CUE_ENTERED" else None,
                action_id="act_1_1" if etype == "ACTION_EXECUTED" else None,
            )
        )
        seqs.append(appended.seq)
    await _commit(repos)
    assert seqs == [1, 2, 3]

    listed = await events.list_by_take("take_alpha_1")
    assert [e.event_type for e in listed] == ["TAKE_STARTED", "CUE_ENTERED", "ACTION_EXECUTED"]
    assert [e.seq for e in listed] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Director sessions
# ---------------------------------------------------------------------------


async def test_director_session_upsert(repos):
    directors = repos["directors"]
    record = DirectorSessionRecord(
        session_id=str(DirectorSessionId("ds_alpha_1")),
        execution_plan_id="plan_alpha_1",
        execution_plan_hash=HASH_A,
        provider_id="gemini",
        model_id="gemini-live-v2",
    )
    await directors.save(record)

    connected = record.model_copy(update={"connection_state": "CONNECTED"})
    await directors.save(connected)
    await _commit(repos)

    loaded = await directors.get(DirectorSessionId("ds_alpha_1"))
    assert loaded is not None
    assert loaded.connection_state == "CONNECTED"
    assert loaded.execution_plan_hash == HASH_A
    assert await directors.get(DirectorSessionId("ds_missing")) is None
