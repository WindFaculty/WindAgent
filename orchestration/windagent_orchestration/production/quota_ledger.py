"""
Append-only quota ledger for the Durable Production Workflow (plan 05 §19.3,
gate VP19_COST_AND_QUOTA_CONTROL_VERIFIED).

Entry types:

    ESTIMATED, RESERVED, SUBMITTED, OBSERVED_DEBIT, RELEASED, ADJUSTED, UNKNOWN

Rules enforced here:

- the ledger is append-only — entries are never mutated or deleted;
- adjustments require a reason AND a source;
- an observed debit is never overwritten: a duplicate observation for the
  same (request_hash, source, amount) is idempotent and does NOT double
  count (replay-safe — gate VP19);
- reservation/submission are idempotent by dedup_key, so replaying an
  outbox/event stream never double-reserves;
- totals are derived from the append-only entries (never stored mutable
  counters), so the ledger can always be reconciled by re-deriving from the
  entries alone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

QUOTA_LEDGER_SCHEMA_VERSION = "1.0.0"


class QuotaEntryType(str, Enum):
    """Append-only ledger entry kinds (plan 05 §19.3)."""

    ESTIMATED = "ESTIMATED"
    RESERVED = "RESERVED"
    SUBMITTED = "SUBMITTED"
    OBSERVED_DEBIT = "OBSERVED_DEBIT"
    RELEASED = "RELEASED"
    ADJUSTED = "ADJUSTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class QuotaLedgerEntry:
    """One immutable ledger entry (§19.3)."""

    entry_id: str
    entry_type: QuotaEntryType
    run_id: str
    request_hash: str
    amount: int  # credits; non-negative for debit/release, signed for ADJUSTED
    reason: str = ""
    source: str = ""  # required for ADJUSTED
    dedup_key: str = ""  # idempotency key for replay safety
    recorded_at: float = 0.0


class QuotaLedger:
    """Append-only, replay-safe quota ledger (§19.3)."""

    def __init__(
        self,
        entries: Optional[List[QuotaLedgerEntry]] = None,
        *,
        clock: Optional[object] = None,
        id_fn: Optional[object] = None,
    ) -> None:
        self._entries: List[QuotaLedgerEntry] = list(entries or [])
        self._clock = clock
        self._id_fn = id_fn

    # -- append (public) -------------------------------------------------------
    def record(
        self,
        *,
        entry_type: QuotaEntryType,
        run_id: str,
        request_hash: str,
        amount: int,
        reason: str = "",
        source: str = "",
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        """Append one entry; duplicate dedup_key is ignored (idempotent).

        Returns the appended entry, or the EXISTING entry with the same
        dedup_key when the write is a replay (no second entry is created —
        the ledger never double counts through replay).

        Callers should pass an explicit dedup_key to make replay idempotent;
        when omitted, the key defaults to ``<TYPE>:<request_hash>`` so a
        repeated write for the same request is still a no-op.
        """
        effective_key = dedup_key or f"{entry_type.value}:{request_hash}"
        existing = self.find_by_dedup(effective_key)
        if existing is not None:
            return existing
        entry = self._build(entry_type, run_id, request_hash, amount, reason, source, effective_key)
        self._entries.append(entry)
        return entry

    def estimate(
        self,
        *,
        run_id: str,
        request_hash: str,
        amount: int,
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        return self.record(
            entry_type=QuotaEntryType.ESTIMATED, run_id=run_id,
            request_hash=request_hash, amount=amount, reason="estimate",
            dedup_key=dedup_key,
        )

    def reserve(
        self,
        *,
        run_id: str,
        request_hash: str,
        amount: int,
        estimate_hash: str = "",
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        return self.record(
            entry_type=QuotaEntryType.RESERVED, run_id=run_id,
            request_hash=request_hash, amount=amount,
            reason=f"reserved against {estimate_hash}" if estimate_hash else "reserved",
            dedup_key=dedup_key,
        )

    def submit(
        self,
        *,
        run_id: str,
        request_hash: str,
        amount: int,
        external_id: str = "",
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        return self.record(
            entry_type=QuotaEntryType.SUBMITTED, run_id=run_id,
            request_hash=request_hash, amount=amount,
            reason=f"submitted external_id={external_id}" if external_id else "submitted",
            dedup_key=dedup_key,
        )

    def observe_debit(
        self,
        *,
        run_id: str,
        request_hash: str,
        amount: int,
        source: str,
        external_id: str = "",
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        """Record an observed (actual) debit — never overwritten.

        The same observation (same dedup_key) is idempotent: replaying the
        provider result does not double-debit. Observed debits are not
        editable; corrections must be recorded as ADJUSTED entries.
        """
        if not source:
            raise ValidationError(
                "observed debit requires a source",
                code="WINDAGENT_ERR_VALIDATION",
            )
        return self.record(
            entry_type=QuotaEntryType.OBSERVED_DEBIT, run_id=run_id,
            request_hash=request_hash, amount=amount, reason="observed debit",
            source=source, dedup_key=dedup_key,
        )

    def release(
        self,
        *,
        run_id: str,
        request_hash: str,
        amount: int,
        reason: str = "released unused reserve",
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        return self.record(
            entry_type=QuotaEntryType.RELEASED, run_id=run_id,
            request_hash=request_hash, amount=amount, reason=reason,
            dedup_key=dedup_key,
        )

    def adjust(
        self,
        *,
        run_id: str,
        request_hash: str,
        amount: int,
        reason: str,
        source: str,
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        """Append an adjustment (signed amount) with reason + source.

        An adjustment never rewrites an observed debit — it only appends a
        new entry that the totals derivation accounts for.
        """
        if not reason:
            raise ValidationError(
                "adjustment requires a reason", code="WINDAGENT_ERR_VALIDATION"
            )
        if not source:
            raise ValidationError(
                "adjustment requires a source", code="WINDAGENT_ERR_VALIDATION"
            )
        return self.record(
            entry_type=QuotaEntryType.ADJUSTED, run_id=run_id,
            request_hash=request_hash, amount=amount, reason=reason,
            source=source, dedup_key=dedup_key,
        )

    def unknown(
        self,
        *,
        run_id: str,
        request_hash: str,
        reason: str = "cost state unknown",
        dedup_key: str = "",
    ) -> QuotaLedgerEntry:
        return self.record(
            entry_type=QuotaEntryType.UNKNOWN, run_id=run_id,
            request_hash=request_hash, amount=0, reason=reason,
            dedup_key=dedup_key,
        )

    # -- queries ----------------------------------------------------------------
    def entries(self) -> List[QuotaLedgerEntry]:
        return list(self._entries)

    def find_by_dedup(self, dedup_key: str) -> Optional[QuotaLedgerEntry]:
        for e in self._entries:
            if e.dedup_key == dedup_key:
                return e
        return None

    def by_request(self, request_hash: str) -> List[QuotaLedgerEntry]:
        return [e for e in self._entries if e.request_hash == request_hash]

    def total_reserved(self) -> int:
        return sum(e.amount for e in self._entries if e.entry_type == QuotaEntryType.RESERVED)

    def total_released(self) -> int:
        return sum(e.amount for e in self._entries if e.entry_type == QuotaEntryType.RELEASED)

    def total_submitted(self) -> int:
        return sum(e.amount for e in self._entries if e.entry_type == QuotaEntryType.SUBMITTED)

    def total_observed_debit(self) -> int:
        return sum(e.amount for e in self._entries if e.entry_type == QuotaEntryType.OBSERVED_DEBIT)

    def total_adjusted(self) -> int:
        return sum(e.amount for e in self._entries if e.entry_type == QuotaEntryType.ADJUSTED)

    def committed(self) -> int:
        """Reserved minus released (what the run is still on the hook for)."""
        return self.total_reserved() - self.total_released()

    def balance(self) -> int:
        """Committed minus observed debit plus signed adjustments.

        A positive balance is credit still owed/allocated; a negative one is
        a deficit that must trigger circuit/open states in the policy layer.
        """
        return self.committed() - self.total_observed_debit() + self.total_adjusted()

    # -- serialization -----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": QUOTA_LEDGER_SCHEMA_VERSION,
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "entry_type": e.entry_type.value,
                    "run_id": e.run_id,
                    "request_hash": e.request_hash,
                    "amount": e.amount,
                    "reason": e.reason,
                    "source": e.source,
                    "dedup_key": e.dedup_key,
                    "recorded_at": e.recorded_at,
                }
                for e in self._entries
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuotaLedger":
        entries = []
        for raw in data.get("entries", []):
            entries.append(
                QuotaLedgerEntry(
                    entry_id=raw["entry_id"],
                    entry_type=QuotaEntryType(raw["entry_type"]),
                    run_id=raw["run_id"],
                    request_hash=raw["request_hash"],
                    amount=raw["amount"],
                    reason=raw.get("reason", ""),
                    source=raw.get("source", ""),
                    dedup_key=raw.get("dedup_key", ""),
                    recorded_at=raw.get("recorded_at", 0.0),
                )
            )
        return cls(entries)

    # -- internal ---------------------------------------------------------------
    def _build(
        self,
        entry_type: QuotaEntryType,
        run_id: str,
        request_hash: str,
        amount: int,
        reason: str,
        source: str,
        dedup_key: str,
    ) -> QuotaLedgerEntry:
        if entry_type == QuotaEntryType.ADJUSTED and amount == 0:
            raise ValidationError(
                "adjustment amount must be non-zero", code="WINDAGENT_ERR_VALIDATION"
            )
        recorded_at = 0.0
        if self._clock is not None and hasattr(self._clock, "__call__"):
            recorded_at = float(self._clock())
        entry_id = ""
        if self._id_fn is not None and hasattr(self._id_fn, "__call__"):
            entry_id = str(self._id_fn())
        if not entry_id:
            entry_id = f"q_{uuid.uuid4().hex[:16]}"
        return QuotaLedgerEntry(
            entry_id=entry_id,
            entry_type=entry_type,
            run_id=run_id,
            request_hash=request_hash,
            amount=amount,
            reason=reason,
            source=source,
            dedup_key=dedup_key or f"{entry_type.value}:{request_hash}",
            recorded_at=recorded_at,
        )


__all__ = [
    "QUOTA_LEDGER_SCHEMA_VERSION",
    "QuotaEntryType",
    "QuotaLedgerEntry",
    "QuotaLedger",
]
