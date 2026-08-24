"""Phase 6 acceptance tests: canonical root /ws protocol, realtime hub, replay.

Covers the canonical subscription contract, durable SQL replay, reconnect
cursors, duplicate suppression, heartbeat, unsubscribe/disconnect cleanup,
malformed-message errors, the OutboxEventPublisher -> EventDispatcher ->
RealtimeHub -> fake UI sender E2E path, the read-only SQL fallback relay, the
conversation compatibility endpoint, and a source guard against the retired
per-socket polling loop.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from windagent_api.main import app as main_app
from windagent_api.routers import conversation_streams as conversation_streams_module
from windagent_api.routers.conversation_streams import router as conversation_streams_router
from windagent_api.services.realtime_hub import RealtimeHub
from windagent_core.events.envelope import EventEnvelope
from windagent_observability.events.dispatcher import EventDispatcher
from windagent_observability.events.publisher import OutboxEventPublisher
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.outbox.models import OutboxRecord
from windagent_storage.outbox.sql_repository import SqlOutboxRepository
from windagent_storage.realtime.sql_replay import SqlRealtimeReplayAdapter
from windagent_storage.repositories.multi_agent_repository import MultiAgentRepository
from tests.support.waiting import async_deterministic_sleep

CANONICAL_EVENT_FIELDS = {
    "event_id",
    "event_type",
    "aggregate_type",
    "aggregate_id",
    "sequence",
    "occurred_at",
    "payload",
}


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{tmp_path / 'phase6_realtime.db'}")
    await manager.upgrade_to_head(BaseORM.metadata)
    try:
        yield manager
    finally:
        await manager.close()


async def _seed_conversation(db, conversation_id: str, outputs: list[str]) -> None:
    async with db.session_factory() as session:
        repo = MultiAgentRepository(session)
        await repo.ensure_conversation(conversation_id)
        for index, output in enumerate(outputs, start=1):
            await repo.append_event(
                event_id=f"evt-{index}",
                idempotency_key=f"idem-evt-{index}",
                conversation_id=conversation_id,
                agent_instance_id=f"agent-{index}",
                agent_session_id=f"session-{index}",
                event_type="terminal_output",
                data={"output": output},
            )
        await session.commit()


def _outbox_record(
    *,
    aggregate_id: str,
    aggregate_type: str = "task",
    sequence_number: int = 1,
    event_id: str | None = None,
    status: str = "pending",
) -> OutboxRecord:
    return OutboxRecord(
        id=f"outbox_{uuid.uuid4().hex[:12]}",
        event_id=event_id or str(uuid.uuid4()),
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        event_type="TaskStatusUpdated",
        payload_json='{"status": "completed"}',
        schema_version=1,
        sequence_number=sequence_number,
        created_at=datetime.now(timezone.utc),
        available_at=datetime.now(timezone.utc),
        status=status,
    )


# ── root /ws canonical protocol ────────────────────────────────────────────


def test_root_ws_subscribe_contract_and_canonical_envelopes(db):
    conversation_id = "phase6-root-ws"
    asyncio.run(_seed_conversation(db, conversation_id, ["A", "B"]))

    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        connected = socket.receive_json()
        assert connected["type"] == "connected"

        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": conversation_id,
            "after_sequence": 0,
        })
        subscribed = socket.receive_json()
        assert subscribed["type"] == "subscribed"
        assert subscribed["aggregate_type"] == "conversation"
        assert subscribed["aggregate_id"] == conversation_id
        assert subscribed["cursor"] == 0

        event1 = socket.receive_json()
        assert set(event1.keys()) == CANONICAL_EVENT_FIELDS
        assert event1["event_id"] == "evt-1"
        assert event1["event_type"] == "terminal_output"
        assert event1["aggregate_type"] == "conversation"
        assert event1["aggregate_id"] == conversation_id
        assert event1["sequence"] == 1
        assert "occurred_at" in event1
        assert event1["payload"] == {"output": "A"}

        event2 = socket.receive_json()
        assert event2["sequence"] == 2
        assert event2["payload"] == {"output": "B"}

        complete = socket.receive_json()
        assert complete["type"] == "catchup_complete"
        assert complete["cursor"] == 2


def test_root_ws_reconnect_after_sequence_replays_only_newer(db):
    conversation_id = "phase6-root-reconnect"
    asyncio.run(_seed_conversation(db, conversation_id, ["A", "B", "C"]))

    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)

    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected
        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": conversation_id,
            "after_sequence": 0,
        })
        socket.receive_json()  # subscribed
        sequences = [socket.receive_json()["sequence"] for _ in range(3)]
        complete = socket.receive_json()
        assert sequences == [1, 2, 3]
        assert complete["type"] == "catchup_complete"
        assert complete["cursor"] == 3

    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected
        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": conversation_id,
            "after_sequence": 2,
        })
        subscribed = socket.receive_json()
        assert subscribed["cursor"] == 2
        replay = socket.receive_json()
        assert replay["sequence"] == 3
        assert replay["event_id"] == "evt-3"
        complete = socket.receive_json()
        assert complete["type"] == "catchup_complete"
        assert complete["cursor"] == 3


def test_root_ws_heartbeat_json_and_legacy(db):
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected
        socket.send_text("ping")
        assert socket.receive_json() == {"type": "pong"}
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}


def test_root_ws_malformed_subscription_error(db):
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected

        socket.send_json({"type": "subscribe", "aggregate_id": "x", "after_sequence": 0})
        err = socket.receive_json()
        assert err["type"] == "error"
        assert err["error"] == "invalid_subscription"

        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "x",
            "after_sequence": -1,
        })
        err = socket.receive_json()
        assert err["error"] == "invalid_subscription"

        socket.send_text("not json")
        err = socket.receive_json()
        assert err["error"] == "invalid_json"

        socket.send_json({"type": "bogus"})
        err = socket.receive_json()
        assert err["error"] == "unsupported_message"


def test_root_ws_unsubscribe_acknowledged(db):
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected
        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
            "after_sequence": 0,
        })
        subscribed = socket.receive_json()
        sub_id = subscribed["subscription_id"]
        socket.receive_json()  # catchup_complete
        socket.send_json({"type": "unsubscribe", "subscription_id": sub_id})
        unsubscribed = socket.receive_json()
        assert unsubscribed["type"] == "unsubscribed"
        assert unsubscribed["subscription_id"] == sub_id


# ── hub-level ordering / dedup / cleanup ───────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_suppression_and_strict_ascending(db):
    conversation_id = "phase6-dedup"
    await _seed_conversation(db, conversation_id, ["A", "B", "C"])

    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    received: list[dict] = []

    async def sender(message):
        received.append(message)

    await hub.subscribe(
        aggregate_type="conversation",
        aggregate_id=conversation_id,
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )
    events = [m for m in received if "event_id" in m]
    assert [e["sequence"] for e in events] == [1, 2, 3]

    # Re-publish an already-replayed sequence -> suppressed.
    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="terminal_output",
            aggregate_type="conversation",
            aggregate_id=conversation_id,
            sequence=1,
            payload={"output": "A"},
        )
    )
    # Publish a genuinely new sequence -> delivered live.
    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="terminal_output",
            aggregate_type="conversation",
            aggregate_id=conversation_id,
            sequence=4,
            payload={"output": "D"},
        )
    )
    events = [m for m in received if "event_id" in m]
    assert [e["sequence"] for e in events] == [1, 2, 3, 4]
    assert len({e["event_id"] for e in events}) == len(events)


@pytest.mark.asyncio
async def test_unsubscribe_and_disconnect_cleanup(db):
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    received: list[dict] = []

    async def sender(message):
        received.append(message)

    sub_id = await hub.subscribe(
        aggregate_type="conversation",
        aggregate_id="conv-x",
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )
    assert hub.active_subscription_count == 1
    await hub.unsubscribe(sub_id)
    assert hub.active_subscription_count == 0

    await hub.subscribe(
        aggregate_type="conversation",
        aggregate_id="conv-y",
        after_sequence=0,
        sender=sender,
        connection_id="conn-2",
    )
    await hub.subscribe(
        aggregate_type="conversation",
        aggregate_id="conv-z",
        after_sequence=0,
        sender=sender,
        connection_id="conn-2",
    )
    assert hub.active_subscription_count == 2
    await hub.disconnect("conn-2")
    assert hub.active_subscription_count == 0


@pytest.mark.asyncio
async def test_replay_live_race_durable_lower_sequence_not_skipped(db):
    """Durable 72 committed but not yet dispatched; live 73 arrives first.

    The hub must drain the durable replay under the subscription lock before
    handling the live envelope so the received sequences are exactly
    ``[72, 73]`` once — never ``[73]`` with 72 permanently skipped.
    """
    repo = SqlOutboxRepository(db.session_factory)
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    received: list[dict] = []

    async def sender(message):
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-race",
        after_sequence=71,
        sender=sender,
        connection_id="conn-1",
    )

    # Durable 72 exists in SQL but has not been dispatched yet.
    await repo.save(_outbox_record(aggregate_id="agg-race", sequence_number=72))

    # Live 73 arrives first (dispatcher ordering).
    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="TaskStatusUpdated",
            aggregate_type="task",
            aggregate_id="agg-race",
            sequence=73,
            payload={"status": "completed"},
        )
    )

    events = [m for m in received if "event_id" in m]
    assert [e["sequence"] for e in events] == [72, 73]
    assert len(events) == 2

    # Re-publishing the same live envelope must not duplicate delivery.
    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="TaskStatusUpdated",
            aggregate_type="task",
            aggregate_id="agg-race",
            sequence=73,
            payload={"status": "completed"},
        )
    )
    events = [m for m in received if "event_id" in m]
    assert [e["sequence"] for e in events] == [72, 73]


def _msg_kind(message: dict) -> str:
    """Classify a hub message as a control message or a canonical event."""
    if message.get("type") in ("subscribed", "catchup_complete"):
        return str(message["type"])
    return "event"


@pytest.mark.asyncio
async def test_no_live_event_precedes_catchup_complete(db):
    """A concurrent live publisher can never deliver before catchup_complete.

    The subscribe critical section holds the subscription lock while sending
    ``catchup_complete`` and only then marks replay complete, so a publisher
    waiting on that lock observes the control message first.  The sender
    blocks on the catchup_complete send to make the race deterministic.
    """
    conversation_id = "phase6-order"
    await _seed_conversation(db, conversation_id, ["A"])

    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    received: list[dict] = []
    release_catchup = asyncio.Event()

    class BlockingControlSender:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(self, message: dict) -> None:
            self.calls += 1
            if message.get("type") == "catchup_complete":
                await release_catchup.wait()
            received.append(message)

    sender = BlockingControlSender()
    subscribe_task = asyncio.create_task(
        hub.subscribe(
            aggregate_type="conversation",
            aggregate_id=conversation_id,
            after_sequence=0,
            sender=sender,
            connection_id="conn-1",
        )
    )

    # Wait until subscribe is blocked sending catchup_complete while still
    # holding the subscription lock (subscribed + replay event + control).
    deadline = time.monotonic() + 3.0
    while sender.calls < 3:
        if time.monotonic() > deadline:
            break
        await async_deterministic_sleep(0.01)
    assert sender.calls >= 3

    # A live publisher now races the pending catchup_complete control message.
    publish_task = asyncio.create_task(
        hub.publish(
            EventEnvelope(
                event_id=str(uuid.uuid4()),
                event_type="terminal_output",
                aggregate_type="conversation",
                aggregate_id=conversation_id,
                sequence=2,
                payload={"output": "B"},
            )
        )
    )
    await async_deterministic_sleep(0.05)  # let publish block on the subscription lock

    release_catchup.set()
    await asyncio.gather(subscribe_task, publish_task)

    kinds = [_msg_kind(m) for m in received]
    assert kinds == ["subscribed", "event", "catchup_complete", "event"]
    assert [m["sequence"] for m in received if "event_id" in m] == [1, 2]


@pytest.mark.asyncio
async def test_send_failure_does_not_advance_cursor_live(db):
    """A failed live send must not advance the cursor so the event can retry."""
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    received: list[dict] = []
    fail_next_event = True

    async def sender(message: dict) -> None:
        nonlocal fail_next_event
        if "event_id" in message and fail_next_event:
            fail_next_event = False
            raise RuntimeError("send failed")
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-live-fail",
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )

    envelope = EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type="TaskStatusUpdated",
        aggregate_type="task",
        aggregate_id="agg-live-fail",
        sequence=1,
        payload={"status": "completed"},
    )
    # First publish: send fails, cursor must not advance.
    await hub.publish(envelope)
    assert [m for m in received if "event_id" in m] == []

    # Retry the same envelope: send succeeds, event delivered exactly once.
    await hub.publish(envelope)
    events = [m for m in received if "event_id" in m]
    assert len(events) == 1
    assert events[0]["sequence"] == 1


@pytest.mark.asyncio
async def test_send_failure_does_not_advance_cursor_replay(db):
    """A failed replay send must not advance the cursor so the event can retry."""
    repo = SqlOutboxRepository(db.session_factory)
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    received: list[dict] = []
    fail_next_event = True

    async def sender(message: dict) -> None:
        nonlocal fail_next_event
        if "event_id" in message and fail_next_event:
            fail_next_event = False
            raise RuntimeError("send failed")
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-replay-fail",
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )

    # Commit a durable event AFTER the initial catch-up so it is only
    # delivered through a later replay drain.
    await repo.save(_outbox_record(aggregate_id="agg-replay-fail", sequence_number=1))

    # First publish triggers a replay drain whose send fails; the live
    # envelope must not be delivered either.
    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="TaskStatusUpdated",
            aggregate_type="task",
            aggregate_id="agg-replay-fail",
            sequence=2,
            payload={"status": "completed"},
        )
    )
    assert [m for m in received if "event_id" in m] == []

    # Second publish drains the durable event successfully, then delivers the
    # live envelope in strict ascending order.
    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="TaskStatusUpdated",
            aggregate_type="task",
            aggregate_id="agg-replay-fail",
            sequence=2,
            payload={"status": "completed"},
        )
    )
    events = [m for m in received if "event_id" in m]
    assert [e["sequence"] for e in events] == [1, 2]


@pytest.mark.asyncio
async def test_repeated_subscribe_same_stream_replaces(db):
    """Repeated subscribe for the same stream on one connection replaces the
    previous subscription instead of creating duplicate delivery."""
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    first_received: list[dict] = []
    second_received: list[dict] = []

    async def first_sender(message):
        first_received.append(message)

    async def second_sender(message):
        second_received.append(message)

    first = await hub.subscribe(
        aggregate_type="conversation",
        aggregate_id="conv-x",
        after_sequence=0,
        sender=first_sender,
        connection_id="conn-1",
    )
    second = await hub.subscribe(
        aggregate_type="conversation",
        aggregate_id="conv-x",
        after_sequence=0,
        sender=second_sender,
        connection_id="conn-1",
    )
    assert first != second
    assert hub.active_subscription_count == 1

    await hub.publish(
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="terminal_output",
            aggregate_type="conversation",
            aggregate_id="conv-x",
            sequence=1,
            payload={"output": "A"},
        )
    )
    assert len([m for m in first_received if "event_id" in m]) == 0
    events = [m for m in second_received if "event_id" in m]
    assert len(events) == 1
    assert events[0]["sequence"] == 1


@pytest.mark.asyncio
async def test_catchup_complete_precedes_concurrent_live_delivery():
    """A live publisher waiting on replay cannot overtake catch-up completion."""

    replay_started = asyncio.Event()
    release_replay = asyncio.Event()

    class BlockingReplay:
        async def events_after(
            self,
            aggregate_type: str,
            aggregate_id: str,
            after_sequence: int = 0,
            limit: int = 500,
        ) -> list[EventEnvelope]:
            replay_started.set()
            await release_replay.wait()
            return []

    hub = RealtimeHub(BlockingReplay())
    received: list[dict] = []

    async def sender(message):
        received.append(message)

    subscribe_task = asyncio.create_task(
        hub.subscribe(
            aggregate_type="task",
            aggregate_id="agg-order",
            after_sequence=0,
            sender=sender,
            connection_id="conn-order",
        )
    )
    await replay_started.wait()
    publish_task = asyncio.create_task(
        hub.publish(
            EventEnvelope(
                event_id=str(uuid.uuid4()),
                event_type="TaskStatusUpdated",
                aggregate_type="task",
                aggregate_id="agg-order",
                sequence=1,
                payload={"status": "completed"},
            )
        )
    )
    await async_deterministic_sleep(0)
    release_replay.set()
    await asyncio.gather(subscribe_task, publish_task)

    assert [message.get("type", "event") for message in received] == [
        "subscribed",
        "catchup_complete",
        "event",
    ]


@pytest.mark.asyncio
async def test_failed_live_send_does_not_advance_cursor():
    """A transient sender failure leaves the event eligible for redelivery."""

    class EmptyReplay:
        async def events_after(
            self,
            aggregate_type: str,
            aggregate_id: str,
            after_sequence: int = 0,
            limit: int = 500,
        ) -> list[EventEnvelope]:
            return []

    hub = RealtimeHub(EmptyReplay())
    received: list[dict] = []
    fail_next_event = True

    async def sender(message):
        nonlocal fail_next_event
        if "event_id" in message and fail_next_event:
            fail_next_event = False
            raise ConnectionError("transient websocket send failure")
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-retry",
        after_sequence=0,
        sender=sender,
        connection_id="conn-retry",
    )
    envelope = EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type="TaskStatusUpdated",
        aggregate_type="task",
        aggregate_id="agg-retry",
        sequence=1,
        payload={"status": "completed"},
    )

    await hub.publish(envelope)
    assert not [message for message in received if "event_id" in message]
    await hub.publish(envelope)

    events = [message for message in received if "event_id" in message]
    assert [message["sequence"] for message in events] == [1]


def test_root_ws_unsubscribe_by_stream_identity(db):
    """The frontend unsubscribes by aggregate stream identity, not
    subscription_id."""
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected
        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
            "after_sequence": 0,
        })
        subscribed = socket.receive_json()
        sub_id = subscribed["subscription_id"]
        socket.receive_json()  # catchup_complete

        socket.send_json({
            "type": "unsubscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
        })
        unsubscribed = socket.receive_json()
        assert unsubscribed["type"] == "unsubscribed"
        assert unsubscribed["subscription_id"] == sub_id
        assert unsubscribed["aggregate_type"] == "conversation"
        assert unsubscribed["aggregate_id"] == "conv-x"
        assert hub.active_subscription_count == 0


def test_root_ws_repeated_subscribe_stale_id_unsubscribe_keeps_current(db):
    """Unsubscribing by a stale subscription id must not remove the current
    subscription for the same stream.

    A repeated subscribe replaces the previous subscription in the hub, so the
    endpoint must track only the current subscription id per stream.  A stale
    id is treated as unknown and the current subscription survives.
    """
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected

        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
            "after_sequence": 0,
        })
        first = socket.receive_json()
        first_sub_id = first["subscription_id"]
        socket.receive_json()  # catchup_complete

        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
            "after_sequence": 0,
        })
        second = socket.receive_json()
        second_sub_id = second["subscription_id"]
        socket.receive_json()  # catchup_complete

        assert first_sub_id != second_sub_id
        assert hub.active_subscription_count == 1

        # Unsubscribe by the stale id: the current subscription must survive.
        socket.send_json({"type": "unsubscribe", "subscription_id": first_sub_id})
        err = socket.receive_json()
        assert err["type"] == "error"
        assert err["error"] == "unknown_subscription"
        assert hub.active_subscription_count == 1

        # Unsubscribe by stream identity removes the current subscription.
        socket.send_json({
            "type": "unsubscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
        })
        unsubscribed = socket.receive_json()
        assert unsubscribed["type"] == "unsubscribed"
        assert unsubscribed["subscription_id"] == second_sub_id
        assert hub.active_subscription_count == 0


def test_root_ws_repeated_subscribe_cleanup_targets_current_only(db):
    """Disconnect cleanup must only unsubscribe the current subscription."""
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    main_app.state.container = SimpleNamespace(db=db, realtime_hub=hub)
    client = TestClient(main_app)
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # connected
        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
            "after_sequence": 0,
        })
        socket.receive_json()  # subscribed
        socket.receive_json()  # catchup_complete
        socket.send_json({
            "type": "subscribe",
            "aggregate_type": "conversation",
            "aggregate_id": "conv-x",
            "after_sequence": 0,
        })
        socket.receive_json()  # subscribed
        socket.receive_json()  # catchup_complete
        assert hub.active_subscription_count == 1
    # After the socket closes, the finally block must have cleaned up exactly
    # the current subscription.
    assert hub.active_subscription_count == 0


# ── outbox -> dispatcher -> hub -> fake UI sender E2E ──────────────────────


@pytest.mark.asyncio
async def test_outbox_publisher_to_hub_e2e(db):
    repo = SqlOutboxRepository(db.session_factory)
    dispatcher = EventDispatcher()
    hub = RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory))
    dispatcher.subscribe("*", hub.publish)
    publisher = OutboxEventPublisher(outbox_repo=repo, dispatcher=dispatcher.dispatch)

    received: list[dict] = []

    async def sender(message):
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-1",
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )

    record = _outbox_record(aggregate_id="agg-1", sequence_number=1)
    await repo.save(record)

    published = await publisher.publish_pending()
    assert published == 1

    events = [m for m in received if "event_id" in m]
    assert len(events) == 1
    assert events[0]["event_id"] == record.event_id
    assert events[0]["aggregate_type"] == "task"
    assert events[0]["aggregate_id"] == "agg-1"
    assert events[0]["sequence"] == 1
    assert events[0]["payload"] == {"status": "completed"}

    # Second publish round: record already published, nothing new delivered.
    published_again = await publisher.publish_pending()
    assert published_again == 0
    assert len([m for m in received if "event_id" in m]) == 1


# ── read-only SQL fallback relay ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_fallback_observes_committed_rows_without_claiming(db):
    repo = SqlOutboxRepository(db.session_factory)
    hub = RealtimeHub(
        SqlRealtimeReplayAdapter(db.session_factory),
        fallback_interval_seconds=0.05,
    )
    await hub.start()
    received: list[dict] = []

    async def sender(message):
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-fb",
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )

    record = _outbox_record(aggregate_id="agg-fb", sequence_number=1)
    await repo.save(record)

    deadline = time.monotonic() + 3.0
    while not any(m.get("event_id") == record.event_id for m in received):
        if time.monotonic() > deadline:
            break
        await async_deterministic_sleep(0.02)

    assert any(m.get("event_id") == record.event_id for m in received)

    # The relay is read-only: the row is still pending, never claimed/published.
    counts = await repo.get_status_counts()
    assert counts["pending"] == 1
    assert counts["publishing"] == 0
    assert counts["published"] == 0
    await hub.stop()


@pytest.mark.asyncio
async def test_sql_fallback_paginates_large_backlog(db):
    """Fallback catch-up drains a backlog larger than one page in a single
    tick instead of leaving events for an arbitrary later tick."""
    repo = SqlOutboxRepository(db.session_factory)
    hub = RealtimeHub(
        SqlRealtimeReplayAdapter(db.session_factory),
        fallback_interval_seconds=0.05,
        replay_page_size=2,
    )
    await hub.start()
    received: list[dict] = []

    async def sender(message):
        received.append(message)

    await hub.subscribe(
        aggregate_type="task",
        aggregate_id="agg-fb-page",
        after_sequence=0,
        sender=sender,
        connection_id="conn-1",
    )

    # Commit a backlog larger than one page AFTER the initial catch-up so the
    # fallback loop must paginate to drain it.
    for seq in range(1, 6):
        await repo.save(_outbox_record(aggregate_id="agg-fb-page", sequence_number=seq))

    deadline = time.monotonic() + 3.0
    while len([m for m in received if "event_id" in m]) < 5:
        if time.monotonic() > deadline:
            break
        await async_deterministic_sleep(0.02)

    events = [m for m in received if "event_id" in m]
    assert [e["sequence"] for e in events] == [1, 2, 3, 4, 5]
    await hub.stop()


# ── conversation compatibility endpoint ────────────────────────────────────


def test_conversation_compat_endpoint_uses_hub(db):
    conversation_id = "phase6-compat"
    asyncio.run(_seed_conversation(db, conversation_id, ["A", "B", "C"]))

    app = FastAPI()
    app.include_router(conversation_streams_router)
    app.state.container = SimpleNamespace(
        db=db,
        realtime_hub=RealtimeHub(SqlRealtimeReplayAdapter(db.session_factory)),
    )
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/conversations/{conversation_id}") as socket:
            events = [socket.receive_json() for _ in range(3)]

    assert [event["data"]["output"] for event in events] == ["A", "B", "C"]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert all(event["is_replay"] is True for event in events)
    assert all(event["conversation_id"] == conversation_id for event in events)
    assert all(event["event_id"] and event["idempotency_key"] for event in events)


def test_conversation_compat_endpoint_fails_closed_without_hub(db):
    app = FastAPI()
    app.include_router(conversation_streams_router)
    app.state.container = SimpleNamespace(db=db)
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/conversations/phase6-no-hub") as socket:
                socket.receive_json()


# ── source guard: retired polling loop ─────────────────────────────────────


def test_conversation_streams_no_longer_polls_sql():
    source = Path(conversation_streams_module.__file__).read_text(encoding="utf-8")
    assert "asyncio.sleep" not in source
    assert "MultiAgentRepository" not in source
    assert "conversation_events_after" not in source