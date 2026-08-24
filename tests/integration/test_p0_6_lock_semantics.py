"""P0.6 — Review/Approval/Lock semantics: truthful ``issued_at`` (P0.6.1).

Before P0.6 the A-issued ``LockedScreenplayReceipt.issued_at`` was DERIVED
from the draft content hash (pseudo-time) for fixture determinism. The fix:

- production issues receipts with the ACTUAL wall-clock issuance time
  (injected clock seam on ``StudioRunService``/reconciler/dispatch);
- deterministic tests inject a fixed clock;
- timestamps are never derived from content hashes.

Drives the REAL durable path (queue → worker → FixtureModelPort) end-to-end
and inspects the persisted LockedScreenplayReceipt artifact.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from windagent_api.composition.container import ApplicationContainer

import windagent_api.dependencies as api_deps
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_storage.unit_of_work.studio_uow import StudioUnitOfWork
from windagent_worker.runner import ProductionWorker
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_intelligence.story.prompts.fixture import FixtureModelPort
from windagent_intelligence.story.runtime_handlers import HANDLER_REGISTRY
from windagent_worker.studio_runtime import StudioRuntimeAdapter
from windagent_core.contracts.studio.commands import (
    CreateEpisodeCommand,
    CreateSeriesCommand,
    StartRunCommand,
)
from windagent_core.domain.studio.approval import (
    ApprovalCheckpoint,
    ApprovalMode,
    ApprovalPolicy,
)
from produce_b3_evidence import GOLDEN_GENERATION_RESPONSE
from produce_b4_evidence import GOLDEN_BIBLE_RESPONSE
from produce_b5_evidence import GOLDEN_BEAT_SHEET, GOLDEN_EPISODE_OUTLINE
from produce_b6_evidence import GOLDEN_SCREENPLAY_DRAFT
from produce_b7_evidence import GOLDEN_REVIEW_CLEAN


PINNED = datetime(2026, 1, 15, 12, 30, 0, tzinfo=timezone.utc)


def _responses() -> dict:
    return {
        "ideation": json.dumps(GOLDEN_GENERATION_RESPONSE, ensure_ascii=False),
        "bibles": json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False),
        "beats": json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False),
        "outline": json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False),
        "screenplay": json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False),
        "review": json.dumps(GOLDEN_REVIEW_CLEAN, ensure_ascii=False),
    }


async def _drive(container, *, clock=None) -> dict:
    async with StudioUnitOfWork(container.db.session_factory) as uow:
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

    series = await container.studio_run_service.create_series(
        CreateSeriesCommand(idempotency_key="p06-srs", title="Lock Semantics")
    )
    episode = await container.studio_run_service.create_episode(
        CreateEpisodeCommand(
            idempotency_key="p06-ep",
            series_id=series.series_id,
            title="Ep Lock",
            metadata={
                "creative_brief": {
                    "brief_id": "brf_p06",
                    "title": "P06 Brief",
                    "genre": "fantasy",
                    "logline": "A rabbit crosses the valley.",
                    "tone": "warm",
                    "audience": "kids",
                    "language": "vi",
                }
            },
        )
    )

    port = FixtureModelPort(responses=_responses())
    adapter = StudioRuntimeAdapter(
        handler_registry=HANDLER_REGISTRY,
        session_factory=container.db.session_factory,
        studio_uow_factory=lambda: StudioUnitOfWork(container.db.session_factory),
        model_port=port,
        certification=False,
    )
    registry = ExecutionRuntimeRegistry()
    registry.register_capability("studio", adapter)
    worker = ProductionWorker(
        name="p06-worker",
        task_queue=SqlDurableTaskQueue(container.db.session_factory),
        execution_registry=registry,
        uow_factory=lambda: SqlUnitOfWork(container.db.session_factory),
        studio_reconciler=container.studio_run_service,
    )
    await worker.start()

    started = datetime.now(timezone.utc).replace(tzinfo=None)
    await container.studio_run_service.start_or_resume_run(
        StartRunCommand(episode_id=episode.episode_id, idempotency_key="p06-run")
    )
    for _ in range(40):
        tick = await worker.poll_and_execute_tick()
        if tick.get("status") == "idle":
            async with container.db.session_factory() as sess:
                from sqlalchemy import text

                rows = (
                    await sess.execute(
                        text(
                            "SELECT status FROM studio_run_nodes "
                            "WHERE dag_node_id='lock'"
                        )
                    )
                ).fetchall()
                if rows and all(r[0] == "SUCCEEDED" for r in rows):
                    break
    finished = datetime.now(timezone.utc).replace(tzinfo=None)

    async with StudioUnitOfWork(container.db.session_factory) as uow:
        arts = await uow.artifacts.list_for_episode(episode.episode_id)
        receipts = [
            a for a in arts if a.artifact_type.value == "LockedScreenplayReceipt"
        ]
        ep = await uow.episodes.get(episode.episode_id)
    state = ep.state.value if hasattr(ep.state, "value") else str(ep.state)
    return {
        "receipts": receipts,
        "state": state,
        "started": started,
        "finished": finished,
    }


@pytest.mark.asyncio
async def test_receipt_uses_injected_clock_when_provided():
    tmp = Path(tempfile.mkdtemp(prefix="p06_pin_"))
    container = ApplicationContainer(db_url=f"sqlite+aiosqlite:///{tmp / 'p06pin.db'}")
    container.studio_clock = lambda: PINNED
    await container.bootstrap()
    api_deps._container = container

    result = await _drive(container)
    assert result["state"] in ("LOCKED", "READY_FOR_PRODUCTION")
    assert len(result["receipts"]) == 1
    issued_at = result["receipts"][0].content["issued_at"]
    if not isinstance(issued_at, datetime):
        issued_at = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
    assert issued_at == PINNED


@pytest.mark.asyncio
async def test_receipt_uses_actual_wall_clock_without_clock():
    tmp = Path(tempfile.mkdtemp(prefix="p06_live_"))
    container = ApplicationContainer(db_url=f"sqlite+aiosqlite:///{tmp / 'p06live.db'}")
    await container.bootstrap()
    api_deps._container = container

    result = await _drive(container)
    assert len(result["receipts"]) == 1
    issued_at = result["receipts"][0].content["issued_at"]
    if not isinstance(issued_at, datetime):
        issued_at = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
    naive = issued_at.replace(tzinfo=None)
    # Actual persisted issuance window — never a hash-derived pseudo-time.
    assert result["started"] <= naive <= result["finished"]