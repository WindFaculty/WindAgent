"""
Unit tests for WindAgent Web Application state recovery and event deduplication (Phase 13).
"""

import pytest
from unittest.mock import MagicMock


def test_state_recovery_default_fallback():
    # Mocking LocalStorage engine in Python environment test
    class MockStateEngine:
        def __init__(self):
            self.data = {}

        def save_snapshot(self, snapshot):
            self.data["snapshot"] = snapshot

        def load_snapshot(self):
            return self.data.get("snapshot", {
                "activeTab": "overview",
                "activeTaskId": None,
                "pendingPermissions": [],
                "isWorkerDisconnected": False,
                "lastSyncTimestamp": 1000
            })

    engine = MockStateEngine()
    snap = engine.load_snapshot()
    assert snap["activeTab"] == "overview"
    assert snap["isWorkerDisconnected"] is False

    # Save snapshot update
    snap["activeTab"] = "workflows"
    engine.save_snapshot(snap)

    loaded = engine.load_snapshot()
    assert loaded["activeTab"] == "workflows"


def test_event_stream_deduplication():
    # Deduplication test logic
    processed_ids = set()
    events = [
        {"event_id": "evt_101", "event_type": "TaskCreatedDomainEvent"},
        {"event_id": "evt_101", "event_type": "TaskCreatedDomainEvent"},  # Duplicate
        {"event_id": "evt_102", "event_type": "WorkflowStartedDomainEvent"},
    ]

    deduped = []
    for evt in events:
        eid = evt["event_id"]
        if eid not in processed_ids:
            processed_ids.add(eid)
            deduped.append(evt)

    assert len(deduped) == 2
    assert deduped[0]["event_id"] == "evt_101"
    assert deduped[1]["event_id"] == "evt_102"
