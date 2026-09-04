"""Unit contracts for the Phase 2 clean-room kernel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from windagent.kernel import (
    ActorId,
    CausationId,
    CorrelationId,
    CurrencyMismatchError,
    DomainError,
    DomainEvent,
    EntityId,
    EventEnvelope,
    EventId,
    FrozenClock,
    Money,
    Result,
    ResultUnwrapError,
    Version,
    normalize_utc,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExampleCreated(DomainEvent):
    """A deliberately tiny event proving subclasses can add domain data."""

    entity_id: EntityId

    event_name = "example.created"


def test_identifiers_are_normalized_immutable_and_nominal() -> None:
    raw = "A0B1C2D3-E4F5-4A67-8123-123456789ABC"
    entity = EntityId(raw)

    assert str(entity) == "a0b1c2d3-e4f5-4a67-8123-123456789abc"
    assert entity.to_uuid().version == 4
    assert EntityId(str(entity)) == entity
    assert EntityId(str(entity)) != cast(EntityId, ActorId(str(entity)))
    assert EntityId.new() != EntityId.new()

    with pytest.raises(ValueError, match="invalid UUID"):
        EntityId("not-a-uuid")
    with pytest.raises(TypeError, match="UUID"):
        EntityId(cast(str, 42))


def test_domain_error_and_result_preserve_expected_failures() -> None:
    error = DomainError("cannot continue", code="operation_blocked", context={"attempt": 2})
    failed = Result[int].fail(error)

    assert error.to_dict() == {
        "code": "operation_blocked",
        "message": "cannot continue",
        "context": {"attempt": 2},
    }
    assert failed.is_failure and not failed
    assert failed.map(lambda value: value + 1).error is error
    assert failed.recover(lambda failure: len(failure.code)).value == len("operation_blocked")

    with pytest.raises(ResultUnwrapError, match="failed Result") as exc_info:
        failed.unwrap()
    assert exc_info.value.__cause__ is error


def test_result_supports_none_success_and_safe_composition() -> None:
    success = Result.ok(None)
    assert success.is_success and success.value is None
    assert Result.ok(3).map(lambda value: value + 4).value == 7
    assert Result.ok(3).bind(lambda value: Result.ok(str(value))).value == "3"

    with pytest.raises(ValueError, match="exactly one"):
        Result(value=1, error=DomainError("no"))
    with pytest.raises(TypeError, match="must return a Result"):
        Result.ok(1).bind(cast(Callable[[int], Result[int]], lambda value: value + 1))


def test_clock_contracts_require_aware_utc_timestamps() -> None:
    local_time = datetime(2026, 9, 1, 14, 0, tzinfo=timezone(timedelta(hours=7)))
    clock = FrozenClock(local_time)

    assert clock.now() == datetime(2026, 9, 1, 7, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(datetime(2026, 9, 1, 7, 0))


def test_money_is_decimal_exact_and_currency_aware() -> None:
    subtotal = Money("10.25", "usd")
    total = subtotal + Money(Decimal("2.75"), "USD")

    assert total == Money("13.00", "usd")
    assert str(Money.zero("eur")) == "0 EUR"
    with pytest.raises(TypeError, match="must not be a float"):
        Money(1.2, "USD")
    with pytest.raises(CurrencyMismatchError) as exc_info:
        subtotal + Money("1", "EUR")
    assert exc_info.value.code == "currency_mismatch"


def test_version_is_non_negative_ordered_and_incrementable() -> None:
    initial = Version.initial()

    assert int(initial) == 0
    assert initial.next() == Version(1)
    assert Version(1) < Version(2)
    with pytest.raises(ValueError, match="non-negative"):
        Version(-1)
    with pytest.raises(TypeError, match="integer"):
        Version(cast(int, True))


def test_event_envelope_preserves_event_metadata_and_freezes_payload() -> None:
    aggregate_id = EntityId.new()
    event = ExampleCreated(
        entity_id=aggregate_id,
        event_id=EventId.new(),
        occurred_at=datetime(2026, 9, 1, 14, 0, tzinfo=timezone(timedelta(hours=7))),
    )
    envelope = EventEnvelope.from_event(
        event,
        aggregate_type="example",
        aggregate_id=aggregate_id,
        sequence=0,
        payload={"items": ["one", {"count": 1}]},
        actor_id=ActorId.new(),
        correlation_id=CorrelationId.new(),
        causation_id=CausationId.new(),
    )

    assert envelope.event_id == event.event_id
    assert envelope.event_type == "example.created"
    assert envelope.occurred_at == datetime(2026, 9, 1, 7, 0, tzinfo=UTC)
    assert envelope.to_dict()["payload"] == {"items": ["one", {"count": 1}]}
    with pytest.raises(TypeError):
        cast(dict[str, object], envelope.payload)["other"] = "mutate"


def test_event_envelope_rejects_mismatched_identifier_types() -> None:
    with pytest.raises(TypeError, match="aggregate_id"):
        EventEnvelope(
            event_type="example.created",
            aggregate_type="example",
            aggregate_id=cast(EntityId, ActorId.new()),
            sequence=0,
        )
