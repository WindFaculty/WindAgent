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
    RecordApprovalCommand,
    SelectIdeaCommand,
    StartRunCommand,
)
from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId, SeriesProjectId, StudioRunId
from windagent_core.contracts.studio.models import StudioTaskResult, StudioTaskStatus
from windagent_core.domain.story.ideation.models import IdeaCandidate, IdeaCandidateSet, SelectedIdea
from windagent_core.domain.story.review.models import (
    LockedScreenplayReceipt,
    ReviewFinding,
    ReviewReport,
)
from windagent_core.domain.story.validation import ValidationSeverity
from windagent_core.events.studio import StudioEventCatalog
from windagent_core.domain.studio.approval import ApprovalPolicy
from windagent_core.domain.studio.artifact import StoryArtifactEnvelope
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
from windagent_orchestration.studio.dag import (
    NODE_BIBLE_GENERATE,
    NODE_IDEA_EVALUATE,
    NODE_LOCK,
    NODE_REVIEW_REVISED,
    NODE_REVISE,
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


async def _human_screenplay_threshold_policy(db):
    async with StudioUnitOfWork(db.session_factory) as uow:
        await uow.approvals.save_policy(
            ApprovalPolicy(
                policy_id="studio.default",
                policy_version="quality-1",
                checkpoint_to_mode_map={
                    checkpoint: (
                        ApprovalMode.HUMAN_REQUIRED
                        if checkpoint == ApprovalCheckpoint.SCREENPLAY
                        else ApprovalMode.AUTO
                    )
                    for checkpoint in ApprovalCheckpoint
                },
                quality_thresholds={ApprovalCheckpoint.SCREENPLAY: 0.8},
                max_review_revision_iterations=2,
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
    command = SelectIdeaCommand(
        idempotency_key="c7-sel1",
        episode_id=episode_id,
        revision_id=run["dag"]["revision_id"],
        candidate_id="cand_gio_mua",
        expected_content_hash=revision_hash,
        expected_optimistic_version=revision_version,
    )
    selected_result = await service.select_idea(command)
    assert selected_result.optimistic_version == revision_version + 1
    assert selected_result.content_hash == revision_hash
    replayed_result = await service.select_idea(command)
    assert replayed_result.replayed is True
    assert replayed_result.optimistic_version == revision_version + 1
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
    outline_envelope = await _queue_envelope(db, started.run_id, NODE_OUTLINE)
    assert {
        ref["artifact_type"] for ref in outline_envelope["input_artifact_refs"]
    } == {"BeatSheet", "CharacterCanon", "WorldBible"}
    screenplay_envelope = await _queue_envelope(db, started.run_id, NODE_SCREENPLAY)
    assert {
        ref["artifact_type"] for ref in screenplay_envelope["input_artifact_refs"]
    } == {"EpisodeOutline", "BeatSheet", "CharacterCanon", "WorldBible"}
    await _complete_node(db, started.run_id, NODE_SCREENPLAY, ["ScreenplayDraft"], [draft.to_canonical_dict()])
    report = ReviewReport(
        report_id="report_1",
        draft_id=draft.draft_id,
        verdict="PASS",
    )
    await _complete_node(
        db,
        started.run_id,
        NODE_REVIEW,
        ["ReviewReport"],
        [report.to_canonical_dict()],
    )

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


async def test_human_rejection_revises_inside_same_run_and_locks_revised_hash(
    db, service
):
    from windagent_core.domain.story.screenplay import ScreenplayDraft

    await _human_screenplay_threshold_policy(db)
    _, episode_id = await _seed_episode(db, service)
    started = await service.start_or_resume_run(
        StartRunCommand(
            idempotency_key="c7-quality-revision",
            episode_id=episode_id,
        )
    )
    initial_draft = ScreenplayDraft(
        draft_id="draft_quality_initial",
        title="Initial screenplay",
        language="en",
        audience_band="8-12",
        target_duration_seconds=240,
        scenes=[],
    )
    for node_id, artifact_types, contents in (
        ("idea.generate", ["IdeaCandidateSet"], [_set().to_canonical_dict()]),
        (NODE_IDEA_EVALUATE, ["IdeaCandidateSet"], [_set().to_canonical_dict()]),
        (
            NODE_BIBLE_GENERATE,
            ["StoryBible", "WorldBible", "CharacterCanon"],
            [{"title": "Bible", "logline": "Story"}, {}, {}],
        ),
        (NODE_BEATS, ["BeatSheet"], [{"title": "Beats"}]),
        (NODE_OUTLINE, ["EpisodeOutline"], [{"title": "Outline"}]),
        (
            NODE_SCREENPLAY,
            ["ScreenplayDraft"],
            [initial_draft.to_canonical_dict()],
        ),
    ):
        await _complete_node(db, started.run_id, node_id, artifact_types, contents)

    blocking_report = ReviewReport(
        report_id="report_quality_initial",
        draft_id=initial_draft.draft_id,
        verdict="REVIEW_REQUIRED",
        review_iteration=1,
        maximum_iterations=2,
        findings=[
            ReviewFinding(
                code="QUALITY_THRESHOLD_VIOLATION",
                severity=ValidationSeverity.BLOCKING,
                location="dimensions/age_fit",
                evidence="age_fit score 0.4 below threshold 0.8",
                remediation="Revise age fit.",
                source="model",
                dimension="age_fit",
                threshold=0.8,
                actual_score=0.4,
                provenance={"model_attempt_id": "attempt-review-1"},
            )
        ],
    )
    await _complete_node(
        db,
        started.run_id,
        NODE_REVIEW,
        ["ReviewReport"],
        [blocking_report.to_canonical_dict()],
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
        initial_revision = await uow.revisions.get(episode.current_revision_id)
    rejected = await service.record_approval(
        RecordApprovalCommand(
            idempotency_key="c7-quality-reject",
            episode_id=episode_id,
            revision_id=initial_revision.revision_id,
            checkpoint=ApprovalCheckpoint.SCREENPLAY.value,
            artifact_hash=initial_revision.content_hash,
            actor="owner",
            decision="REJECTED",
            reason="Policy threshold finding requires revision",
            expected_optimistic_version=initial_revision.optimistic_version,
        )
    )
    assert rejected.next_state == "REVISING"
    revise_envelope = await _queue_envelope(db, started.run_id, NODE_REVISE)
    assert {ref["artifact_type"] for ref in revise_envelope["input_artifact_refs"]} == {
        "ReviewReport",
        "ScreenplayDraft",
    }

    revised_draft = initial_draft.model_copy(
        update={"draft_id": "draft_quality_revised", "title": "Revised screenplay"}
    )
    await _complete_node(
        db,
        started.run_id,
        NODE_REVISE,
        ["ScreenplayDraft"],
        [revised_draft.to_canonical_dict()],
    )
    revised_report = ReviewReport(
        report_id="report_quality_revised",
        draft_id=revised_draft.draft_id,
        verdict="PASS",
        review_iteration=2,
        maximum_iterations=2,
    )
    await _complete_node(
        db,
        started.run_id,
        NODE_REVIEW_REVISED,
        ["ReviewReport"],
        [revised_report.to_canonical_dict()],
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        episode = await uow.episodes.get(episode_id)
        revised_revision = await uow.revisions.get(episode.current_revision_id)
    approved = await service.record_approval(
        RecordApprovalCommand(
            idempotency_key="c7-quality-approve-revised",
            episode_id=episode_id,
            revision_id=revised_revision.revision_id,
            checkpoint=ApprovalCheckpoint.SCREENPLAY.value,
            artifact_hash=revised_revision.content_hash,
            actor="owner",
            decision="APPROVED",
            reason="Revised draft passed the second review",
            expected_optimistic_version=revised_revision.optimistic_version,
        )
    )
    assert approved.awaiting_approval is False
    lock_envelope = await _queue_envelope(db, started.run_id, NODE_LOCK)
    lock_draft_ref = next(
        ref
        for ref in lock_envelope["input_artifact_refs"]
        if ref["artifact_type"] == "ScreenplayDraft"
    )
    assert lock_draft_ref["content_hash"] != initial_draft.content_hash()
    await _complete_node(
        db,
        started.run_id,
        NODE_LOCK,
        ["LockedScreenplayPackage"],
        [{"package_id": "pkg_quality_revised"}],
    )
    async with StudioUnitOfWork(db.session_factory) as uow:
        run = await uow.runs.get(started.run_id)
        episode = await uow.episodes.get(episode_id)
        revision = await uow.revisions.get(episode.current_revision_id)
    async with db.session_factory() as session:
        event_rows = await session.execute(
            text(
                "SELECT event_type FROM studio_events "
                "WHERE studio_run_id = :run_id"
            ),
            {"run_id": str(started.run_id)},
        )
    assert run["status"] == "COMPLETED"
    assert len(run["metadata"]["revision_chain"]) == 2
    assert revision.content_hash == lock_draft_ref["content_hash"]
    assert episode.state.value == "READY_FOR_PRODUCTION"
    event_types = {row[0] for row in event_rows}
    assert StudioEventCatalog.STORY_REVISION_REQUESTED in event_types
    assert StudioEventCatalog.RUN_FAILED not in event_types
