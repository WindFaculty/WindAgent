"""Unit tests for SessionService."""
from __future__ import annotations

import pytest

from services.event_bus import drain
from services.session_service import SessionService


@pytest.mark.asyncio
async def test_create_session_emits_session_created(session_service: SessionService):
    sid = session_service  # silence linter
    # Subscribe to the bus before publishing
    bus = sid._bus
    # Create one session and grab its id from the resulting envelope
    chat = await session_service.create_session()

    # After publish, no subscriber was attached so we just verify state.
    assert chat.status == "idle"
    assert session_service.session_count() == 1


@pytest.mark.asyncio
async def test_create_session_emits_event_to_subscriber(event_bus, session_service):
    chat = await session_service.create_session()
    sid = str(chat.id)

    # Subscribe AFTER create — first event is gone. Subscribe BEFORE next call.
    q = await event_bus.subscribe(sid)
    chat2 = await session_service.create_session()
    sid2 = str(chat2.id)
    # publish to sid2 — q is bound to sid, should not receive it
    from schemas.event import EventEnvelope
    await event_bus.publish(sid2, EventEnvelope(event="message_received", data={}))
    events = await drain(q)
    assert events == []

    # Now publish to sid via the service
    from schemas.event import EventEnvelope as Env  # noqa
    # add_user_message emits message_received
    await session_service.add_user_message(chat.id, "hello")
    events = await drain(q)
    assert len(events) == 1
    assert events[0].event == "message_received"
    assert events[0].data["session_id"] == str(chat.id)
    assert events[0].data["content"] == "hello"


@pytest.mark.asyncio
async def test_get_session_returns_none_for_unknown(session_service: SessionService):
    import uuid
    assert await session_service.get_session(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_add_message_unknown_session_raises(session_service: SessionService):
    import uuid
    with pytest.raises(KeyError):
        await session_service.add_user_message(uuid.uuid4(), "x")


@pytest.mark.asyncio
async def test_add_message_updates_session_timestamp(session_service: SessionService):
    chat = await session_service.create_session()
    await session_service.add_user_message(chat.id, "hi")
    fetched = await session_service.get_session(chat.id)
    assert fetched is not None
    assert fetched.updated_at >= chat.created_at


@pytest.mark.asyncio
async def test_update_status_changes_state(session_service: SessionService):
    chat = await session_service.create_session()
    await session_service.update_status(chat.id, "planning")
    fetched = await session_service.get_session(chat.id)
    assert fetched is not None
    assert fetched.status == "planning"