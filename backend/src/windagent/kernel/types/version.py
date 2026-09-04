"""A non-negative immutable version for optimistic concurrency and schemas."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Version:
    """A monotonically incrementable non-negative integer value object."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("version must be an integer")
        if self.value < 0:
            raise ValueError("version must be non-negative")

    @classmethod
    def initial(cls) -> Version:
        return cls(0)

    def next(self) -> Version:
        return Version(self.value + 1)

    def __int__(self) -> int:
        return self.value
