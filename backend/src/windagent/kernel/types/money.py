"""A precise, currency-aware monetary value object."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..errors import DomainError

_CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")


class CurrencyMismatchError(DomainError):
    """Raised when arithmetic is attempted across different currencies."""

    default_code = "currency_mismatch"

    def __init__(self, left: str, right: str) -> None:
        super().__init__(
            f"currency mismatch: {left} and {right}",
            context={"left_currency": left, "right_currency": right},
        )


@dataclass(frozen=True, slots=True, init=False)
class Money:
    """An exact amount in a three-letter ISO-style currency code.

    The kernel never rounds implicitly: rounding rules are a policy concern of
    the owning module, which can create a new ``Money`` once its policy has
    been applied.
    """

    amount: Decimal
    currency: str

    def __init__(self, amount: Decimal | int | str | float, currency: str) -> None:
        object.__setattr__(self, "amount", _coerce_amount(amount))
        object.__setattr__(self, "currency", _normalize_currency(currency))

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal("0"), currency)

    def add(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: Money) -> Money:
        self._require_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def negated(self) -> Money:
        return Money(-self.amount, self.currency)

    def _require_same_currency(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("money arithmetic requires another Money value")
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)

    def __add__(self, other: Money) -> Money:
        return self.add(other)

    def __sub__(self, other: Money) -> Money:
        return self.subtract(other)

    def __neg__(self) -> Money:
        return self.negated()

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


def _coerce_amount(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, bool):
        raise TypeError("money amount cannot be a boolean")
    if isinstance(value, float):
        raise TypeError("money amount must not be a float; use Decimal or a string")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid money amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError("money amount must be finite")
    return amount


def _normalize_currency(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("currency must be a string")
    currency = value.strip().upper()
    if not _CURRENCY_PATTERN.fullmatch(currency):
        raise ValueError("currency must be a three-letter alphabetic code")
    return currency
