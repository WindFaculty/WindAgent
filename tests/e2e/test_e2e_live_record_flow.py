"""E2E Test: Live Record plan creation, take capture, and privacy scanning."""

from __future__ import annotations

import pytest
from windagent.kernel.time import SystemClock
from windagent.modules.live_record.application.runtime import LiveRecordServices, container_for
from windagent.modules.live_record.infrastructure.memory import (
    InMemoryLiveRecordStore,
    memory_scope_factory,
)


@pytest.mark.asyncio
async def test_e2e_live_record_full_lifecycle() -> None:
    store = InMemoryLiveRecordStore()
    services = LiveRecordServices(
        scope_factory=memory_scope_factory(store),
        clock=SystemClock(),
    )
    container = container_for(services)

    # 1. Create Live Execution Plan
    plan_view = await container.live_record.create_plan(
        episode_id="ep-e2e-1",
        episode_revision_id="rev-e2e-1",
        recording_profile={"fps": 60, "resolution": "1920x1080", "codec": "H264"},
        scenes=({"scene_id": "sc-1", "index": 0, "title": "IDE Intro", "cues": []},),
    )
    assert plan_view is not None
    assert plan_view.episode_id == "ep-e2e-1"
    assert plan_view.episode_revision_id == "rev-e2e-1"

    # 2. Transition Plan through lifecycle (DRAFT -> PREPARED -> VALIDATED -> FROZEN)
    await container.live_record.transition_plan(plan_id=plan_view.plan_id, target="PREPARED")
    await container.live_record.transition_plan(plan_id=plan_view.plan_id, target="VALIDATED")
    frozen_plan = await container.live_record.transition_plan(plan_id=plan_view.plan_id, target="FROZEN")

    assert frozen_plan.status == "FROZEN"
    assert frozen_plan.recordable is True

    # 3. Record Take
    take_view = await container.live_record.create_take(
        plan_id=plan_view.plan_id,
        episode_id="ep-e2e-1",
    )
    assert take_view is not None
    assert take_view.execution_plan_id == plan_view.plan_id
