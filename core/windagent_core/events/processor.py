"""
Event Processors for WindAgent Architecture V2:
- Payload secret redaction
- Event deduplication (idempotency tracking)
- Cursor-based event replay filtering (after_seq)
"""

from __future__ import annotations
from typing import Any, Dict, List, Set, Tuple

from windagent_core.events.envelope import EventEnvelope

SENSITIVE_KEYS = {
    "password", "secret", "api_key", "token", "auth", "authorization",
    "secret_key", "encryption_key", "private_key", "bearer"
}


def redact_event_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redacts secret/sensitive key values in event payloads."""
    redacted: Dict[str, Any] = {}
    for key, val in payload.items():
        key_lower = str(key).lower()
        if any(s in key_lower for s in SENSITIVE_KEYS):
            redacted[key] = "***REDACTED***"
        elif isinstance(val, dict):
            redacted[key] = redact_event_payload(val)
        elif isinstance(val, list):
            redacted[key] = [
                redact_event_payload(item) if isinstance(item, dict) else item
                for item in val
            ]
        else:
            redacted[key] = val
    return redacted


class EventDeduplicator:
    """Tracks processed event IDs or (session_id, sequence) pairs to enforce idempotency."""
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self._seen_ids: Set[str] = set()
        self._seen_seqs: Set[Tuple[str, int]] = set()

    def is_duplicate(self, envelope: EventEnvelope) -> bool:
        eid = str(envelope.event_id)
        seq_key = (str(envelope.session_id), envelope.sequence)

        if eid in self._seen_ids or (envelope.sequence > 0 and seq_key in self._seen_seqs):
            return True
        return False

    def mark_processed(self, envelope: EventEnvelope) -> None:
        eid = str(envelope.event_id)
        seq_key = (str(envelope.session_id), envelope.sequence)

        self._seen_ids.add(eid)
        if envelope.sequence > 0:
            self._seen_seqs.add(seq_key)

        # Simple eviction if history exceeds max
        if len(self._seen_ids) > self.max_history:
            self._seen_ids.clear()
            self._seen_seqs.clear()


class ReplayFilter:
    """Filters a stream or list of events by after_sequence cursor."""
    @staticmethod
    def filter_events(events: List[EventEnvelope], after_sequence: int = 0) -> List[EventEnvelope]:
        """Returns only events with sequence > after_sequence, sorted by sequence ascending."""
        filtered = [e for e in events if e.sequence > after_sequence]
        filtered.sort(key=lambda e: e.sequence)
        return filtered
