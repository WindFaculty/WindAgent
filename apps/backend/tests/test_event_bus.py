"""Unit tests for EventBus."""
from __future__ import annotations

import asyncio

import pytest

from schemas.event import EventEnvelope
from services.event_bus import EventBus, drain


@pytest.mark.asyncio
async def test_publish_delivers_to_all_subscribers():
    bus = EventBus()
    sid = "s1"
    q1 = await bus.subscribe(sid)
    q2 = await bus.subscribe(sid)

    env = EventEnvelope(event="session_created", data={"session_id": sid})
    delivered = await bus.publish(sid, env)

    assert delivered == 2
    assert (await drain(q1))[0].event == "session_created"
    assert (await drain(q2))[0].event == "session_created"


@pytest.mark.asyncio
async def test_publish_to_unknown_session_is_noop():
    bus = EventBus()
    delivered = await bus.publish("nope", EventEnvelope(event="error", data={}))
    assert delivered == 0


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    bus = EventBus()
    sid = "s1"
    q = await bus.subscribe(sid)
    assert bus.subscriber_count(sid) == 1

    await bus.unsubscribe(sid, q)
    assert bus.subscriber_count(sid) == 0
    # Idempotent
    await bus.unsubscribe(sid, q)
    assert bus.subscriber_count(sid) == 0


@pytest.mark.asyncio
async def test_subscribers_isolated_per_session():
    bus = EventBus()
    qa = await bus.subscribe("A")
    qb = await bus.subscribe("B")

    await bus.publish("A", EventEnvelope(event="session_created", data={}))
    await bus.publish("B", EventEnvelope(event="session_finished", data={}))

    a_events = await drain(qa)
    b_events = await drain(qb)

    assert [e.event for e in a_events] == ["session_created"]
    assert [e.event for e in b_events] == ["session_finished"]


@pytest.mark.asyncio
async def test_publish_drops_for_full_subscriber():
    bus = EventBus()
    sid = "s1"
    q = await bus.subscribe(sid, maxsize=2)

    for i in range(5):
        delivered = await bus.publish(
            sid, EventEnvelope(event="error", data={"i": i})
        )

    # Only first 2 fit, so total delivered across the 5 calls is 2.
    assert delivered == 0  # 5th call sees a full queue
    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_await_on_queue_blocks_until_publish():
    bus = EventBus()
    sid = "s1"
    q = await bus.subscribe(sid)

    async def publisher():
        await asyncio.sleep(0.05)
        await bus.publish(sid, EventEnvelope(event="step_started", data={}))

    asyncio.create_task(publisher())
    env = await asyncio.wait_for(q.get(), timeout=1.0)
    assert env.event == "step_started"