"""
Unit Tests for WindAgent Event Model V2 (Phase 3 & Phase 14).
Tests canonical EventEnvelope validation, serialization, replay filtering,
event deduplication, and payload secret redaction.
Legacy WebSocket compatibility tests moved to tests/unit/api/test_legacy_event_mappers.py.
"""

import pytest
from windagent_core.domain.types import EventId, SessionId
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.events.processor import (
    redact_event_payload, EventDeduplicator, ReplayFilter
)


def test_event_envelope_creation():
    sid = SessionId.generate()
    eid = EventId.generate()
    envelope = EventEnvelope(
        event_id=eid,
        event_type=EventCatalog.STEP_STARTED,
        session_id=sid,
        sequence=42,
        payload={"step_name": "Read File", "order": 1},
    )
    assert envelope.sequence == 42
    assert envelope.schema_version == 1

    d = envelope.to_dict()
    assert d["event_id"] == str(eid)
    assert d["event_type"] == EventCatalog.STEP_STARTED
    assert d["sequence"] == 42

    reconstructed = EventEnvelope.from_dict(d)
    assert reconstructed.event_id == eid
    assert reconstructed.event_type == EventCatalog.STEP_STARTED
    assert reconstructed.sequence == 42


def test_replay_filter_by_after_sequence():
    sid = SessionId.generate()
    events = [
        EventEnvelope(event_id=EventId.generate(), event_type=EventCatalog.STEP_STARTED, session_id=sid, sequence=seq, payload={"seq": seq})
        for seq in range(1, 11)
    ]

    filtered = ReplayFilter.filter_events(events, after_sequence=5)
    assert len(filtered) == 5
    assert [e.sequence for e in filtered] == [6, 7, 8, 9, 10]

    filtered_zero = ReplayFilter.filter_events(events, after_sequence=0)
    assert len(filtered_zero) == 10


def test_event_deduplication():
    dedup = EventDeduplicator()
    sid = SessionId.generate()
    eid = EventId.generate()

    env1 = EventEnvelope(event_id=eid, event_type=EventCatalog.STEP_STARTED, session_id=sid, sequence=1, payload={})
    env2 = EventEnvelope(event_id=EventId.generate(), event_type=EventCatalog.STEP_STARTED, session_id=sid, sequence=1, payload={})
    env3 = EventEnvelope(event_id=EventId.generate(), event_type=EventCatalog.STEP_STARTED, session_id=sid, sequence=2, payload={})

    assert not dedup.is_duplicate(env1)
    dedup.mark_processed(env1)

    assert dedup.is_duplicate(env1)
    assert dedup.is_duplicate(env2)

    assert not dedup.is_duplicate(env3)


def test_event_payload_redaction():
    raw_payload = {
        "step_name": "API Authentication",
        "api_key": "«redacted:sk-...»",
        "nested": {
            "password": "user1234password",
            "normal_field": "public_data",
        },
        "tokens": ["normal_token", {"bearer_token": "secret_bearer"}],
    }

    redacted = redact_event_payload(raw_payload)
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["password"] == "***REDACTED***"
    assert redacted["nested"]["normal_field"] == "public_data"
    assert redacted["step_name"] == "API Authentication"
