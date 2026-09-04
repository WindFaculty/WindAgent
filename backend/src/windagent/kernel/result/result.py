"""A small, immutable typed result value."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from ..errors import DomainError, ResultUnwrapError

U = TypeVar("U")

_MISSING = object()


@dataclass(frozen=True, slots=True, init=False)
class Result[T]:
    """Represents exactly one of a successful value or a ``DomainError``."""

    _value: T | object
    _error: DomainError | None

    def __init__(self, *, value: T | object = _MISSING, error: DomainError | None = None) -> None:
        has_value = value is not _MISSING
        has_error = error is not None
        if has_value == has_error:
            raise ValueError("a Result must contain exactly one of value or error")
        if has_error and not isinstance(error, DomainError):
            raise TypeError("a failed Result must contain a DomainError")

        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_error", error)

    @classmethod
    def ok(cls, value: T) -> Result[T]:
        """Create a successful result; ``None`` is a valid success value."""

        return cls(value=value)

    @classmethod
    def success(cls, value: T) -> Result[T]:
        """Alias for :meth:`ok`."""

        return cls.ok(value)

    @classmethod
    def fail(cls, error: DomainError) -> Result[T]:
        """Create a failed result."""

        return cls(error=error)

    @classmethod
    def failure(cls, error: DomainError) -> Result[T]:
        """Alias for :meth:`fail`."""

        return cls.fail(error)

    @classmethod
    def err(cls, error: DomainError) -> Result[T]:
        """Alias for :meth:`fail`, matching common result terminology."""

        return cls.fail(error)

    @property
    def is_ok(self) -> bool:
        return self._error is None

    @property
    def is_success(self) -> bool:
        return self.is_ok

    @property
    def is_error(self) -> bool:
        return not self.is_ok

    @property
    def is_failure(self) -> bool:
        return self.is_error

    @property
    def value(self) -> T:
        """Return the success value or raise ``ResultUnwrapError``."""

        if self._error is not None:
            raise ResultUnwrapError("cannot read value from a failed Result") from self._error
        return cast(T, self._value)

    @property
    def error(self) -> DomainError:
        """Return the failure or raise ``ResultUnwrapError`` on success."""

        if self._error is None:
            raise ResultUnwrapError("cannot read error from a successful Result")
        return self._error

    def unwrap(self) -> T:
        """Return the success value, preserving the underlying failure as cause."""

        return self.value

    def expect(self, message: str) -> T:
        """Return the success value or raise with the caller-provided context."""

        if self._error is not None:
            raise ResultUnwrapError(message) from self._error
        return cast(T, self._value)

    def map(self, transform: Callable[[T], U]) -> Result[U]:
        """Map a success value without touching a failure."""

        if self._error is not None:
            return cast(Result[U], self)
        return Result.ok(transform(cast(T, self._value)))

    def bind(self, transform: Callable[[T], Result[U]]) -> Result[U]:
        """Chain a function that itself returns a ``Result``."""

        if self._error is not None:
            return cast(Result[U], self)

        result = transform(cast(T, self._value))
        if not isinstance(result, Result):
            raise TypeError("Result.bind transform must return a Result")
        return result

    def map_error(self, transform: Callable[[DomainError], DomainError]) -> Result[T]:
        """Map a failure while preserving a success value."""

        if self._error is None:
            return self

        mapped = transform(self._error)
        if not isinstance(mapped, DomainError):
            raise TypeError("Result.map_error transform must return a DomainError")
        return Result.fail(mapped)

    def recover(self, transform: Callable[[DomainError], T]) -> Result[T]:
        """Turn a failure into a success using an explicit recovery function."""

        if self._error is None:
            return self
        return Result.ok(transform(self._error))

    def __bool__(self) -> bool:
        return self.is_ok
