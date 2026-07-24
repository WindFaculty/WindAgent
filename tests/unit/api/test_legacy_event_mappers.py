#!/usr/bin/env python3
"""
Unit tests for legacy WebSocket event compatibility adapter (Phase 14).

Verifies bidirectional mapping between canonical V2 EventEnvelope and legacy WebSocket shapes.
Legacy mappers live only at the API edge adapter boundary, not inside windagent_core.
"""

import json
from pathlib import Path

from windagent_core.domain.types import EventId, SessionId
from windagent_core.events.envelope import EventEnvelope
from windagent_core.events.catalog import EventCatalog
from windagent_api.adapters.legacy_event_mappers import (
    v2_event_to_legacy_dict, legacy_dict_to_v2_event
)


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

        v2_envelope = legacy_dict_to_v2_event(sample_legacy_dict, session_id=sid)
        assert v2_envelope.sequence == idx + 1
        assert v2_envelope.payload == {"sample_param": f"value_{idx}"}

        reserialized_legacy = v2_event_to_legacy_dict(v2_envelope)
        assert reserialized_legacy["event"] == legacy_name
        assert reserialized_legacy["seq"] == idx + 1
        assert reserialized_legacy["data"] == {"sample_param": f"value_{idx}"}


def test_unknown_event_tolerance():
    unknown_legacy_dict = {
        "event": "future_unknown_event_v9",
        "timestamp": "2026-07-23T05:00:00.000Z",
        "seq": 999,
        "data": {"future_key": "future_val"},
    }

    v2_env = legacy_dict_to_v2_event(unknown_legacy_dict)
    assert v2_env.event_type == "future_unknown_event_v9"

    legacy_out = v2_event_to_legacy_dict(v2_env)
    assert legacy_out["event"] == "future_unknown_event_v9"
    assert legacy_out["seq"] == 999
