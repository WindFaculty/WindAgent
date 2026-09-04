"""Audit event and in-memory sink contracts."""

from __future__ import annotations

from datetime import timedelta

import pytest
from windagent.kernel.ids import ActorId
from windagent.kernel.time import FrozenClock, normalize_utc, utc_now
from windagent.platform.security import AuditEvent, InMemoryAuditSink, PolicyEffect

FROZEN_NOW = normalize_utc(utc_now())


def _event(**overrides: object) -> AuditEvent:
    values: dict[str, object] = {
        "action": "job:submit",
        "resource_type": "job",
        "outcome": PolicyEffect.DENY.value,
        "actor_id": ActorId.new(),
        "reason": "frozen",
        "details": {"policy_id": "freeze-deny"},
    }
    values.update(overrides)
    return AuditEvent(**values)  # type: ignore[arg-type]


def test_audit_event_to_dict_is_json_safe() -> None:
    document = _event().to_dict()
    assert document["action"] == "job:submit"
    assert document["outcome"] == "deny"
    assert document["details"] == {"policy_id": "freeze-deny"}
    assert isinstance(document["occurred_at"], str)


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "  "},
        {"outcome": ""},
        {"actor_id": "not-an-actor"},
        {"details": "not-a-mapping"},
    ],
)
def test_audit_event_rejects_invalid_input(overrides: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _event(**overrides)


async def test_sink_keeps_arrival_order() -> None:
    sink = InMemoryAuditSink()
    first = _event(reason="first")
    second = _event(reason="second")
    await sink.record(first)
    await sink.record(second)
    assert sink.events == (first, second)


async def test_sink_is_bounded_by_max_events() -> None:
    sink = InMemoryAuditSink(max_events=2)
    events = [_event(reason=str(index)) for index in range(4)]
    for event in events:
        await sink.record(event)
    assert sink.events == tuple(events[-2:])


def test_sink_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError):
        InMemoryAuditSink(max_events=0)


async def test_sink_rejects_non_events() -> None:
    sink = InMemoryAuditSink()
    with pytest.raises(TypeError):
        await sink.record("not-an-event")  # type: ignore[arg-type]


def test_occurred_at_is_normalized_to_utc() -> None:
    naive_target = FROZEN_NOW.astimezone().replace(tzinfo=None)
    with pytest.raises(ValueError):
        AuditEvent(
            action="a",
            resource_type="r",
            outcome="allow",
            occurred_at=naive_target,
        )
    shifted = _event(occurred_at=FROZEN_NOW + timedelta(hours=1))
    assert shifted.occurred_at == normalize_utc(FROZEN_NOW + timedelta(hours=1))


def test_frozen_clock_produces_stable_audit_stamps() -> None:
    clock = FrozenClock(FROZEN_NOW)
    event = AuditEvent(
        action="a",
        resource_type="r",
        outcome="allow",
        occurred_at=clock.now(),
    )
    assert event.occurred_at == FROZEN_NOW
