"""
Unit Tests for WindAgent Event Model V2 (Phase 3):
- EventEnvelope V2 validation & serialization
- Legacy WebSocket compatibility parity for all 41 inventory events
- Replay filtering by after_seq
- Event deduplication & idempotency tracking
- Payload secret redaction
- Unknown event tolerance
"""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest

from windagent_core.domain.types import EventId, SessionId
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_core.events.compatibility import (
    LEGACY_TO_V2_MAP, v2_event_to_legacy_dict, legacy_dict_to_v2_event
)
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
    assert envelope.schema_version == "2.0"

    d = envelope.to_dict()
    assert d["event_id"] == str(eid)
    assert d["event_type"] == EventCatalog.STEP_STARTED
    assert d["sequence"] == 42

    reconstructed = EventEnvelope.from_dict(d)
    assert reconstructed.event_id == eid
    assert reconstructed.event_type == EventCatalog.STEP_STARTED
    assert reconstructed.sequence == 42


def test_legacy_inventory_events_parity():
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    inventory_file = root_dir / "artifacts" / "architecture_v2" / "baseline" / "event_inventory.json"
    
    assert inventory_file.exists(), f"Phase 0 event inventory artifact missing at {inventory_file}"

    with open(inventory_file, "r", encoding="utf-8") as f:
        inventory_data = json.load(f)

    legacy_events = inventory_data.get("events", [])
    assert len(legacy_events) >= 41, f"Expected at least 41 legacy events, got {len(legacy_events)}"

    sid = SessionId.generate()

    for idx, event_item in enumerate(legacy_events):
        legacy_name = event_item["name"]
        sample_legacy_dict = {
            "event": legacy_name,
            "timestamp": "2026-07-23T05:00:00.000Z",
            "seq": idx + 1,
            "data": {"sample_param": f"value_{idx}"},
        }

        # Deserialization to V2 EventEnvelope
        v2_envelope = legacy_dict_to_v2_event(sample_legacy_dict, session_id=sid)
        assert v2_envelope.sequence == idx + 1
        assert v2_envelope.payload == {"sample_param": f"value_{idx}"}

        # Re-serialization back to legacy dict format
        reserialized_legacy = v2_event_to_legacy_dict(v2_envelope)
        assert reserialized_legacy["event"] == legacy_name
        assert reserialized_legacy["seq"] == idx + 1
        assert reserialized_legacy["data"] == {"sample_param": f"value_{idx}"}


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

    # Same sequence or same ID should be marked as duplicate
    assert dedup.is_duplicate(env1)
    assert dedup.is_duplicate(env2)

    # New sequence should not be duplicate
    assert not dedup.is_duplicate(env3)


def test_event_payload_redaction():
    raw_payload = {
        "step_name": "API Authentication",
        "api_key": "sk-proj-super-secret-key",
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


def test_unknown_event_tolerance():
    unknown_legacy_dict = {
        "event": "future_unknown_event_v9",
        "timestamp": "2026-07-23T05:00:00.000Z",
        "seq": 999,
        "data": {"future_key": "future_val"},
    }

    # Deserialization must not crash
    v2_env = legacy_dict_to_v2_event(unknown_legacy_dict)
    assert v2_env.event_type == "future_unknown_event_v9"

    # Reserialization must retain event name
    legacy_out = v2_event_to_legacy_dict(v2_env)
    assert legacy_out["event"] == "future_unknown_event_v9"
    assert legacy_out["seq"] == 999
