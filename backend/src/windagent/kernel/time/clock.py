"""Time abstractions that keep domain logic deterministic and UTC-only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Source of timezone-aware UTC timestamps."""

    def now(self) -> datetime:
        """Return the current instant in UTC."""


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


def normalize_utc(value: datetime) -> datetime:
    """Validate an aware datetime and normalize it to UTC."""

    if not isinstance(value, datetime):
        raise TypeError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SystemClock:
    """The production clock, backed solely by the Python standard library."""

    def now(self) -> datetime:
        return utc_now()


@dataclass(frozen=True, slots=True)
class FrozenClock:
    """A deterministic clock useful for unit tests and replayed workflows."""

    instant: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", normalize_utc(self.instant))

    def now(self) -> datetime:
        return self.instant
