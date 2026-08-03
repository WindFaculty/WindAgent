"""
Cost catalog for the Durable Production Workflow (plan 05 §19.1,
gate VP19_COST_AND_QUOTA_CONTROL_VERIFIED).

Prices/credits are provider configuration with effective dates and
provenance — never hard-coded into domain invariants (§18). Each entry:

    provider, model, operation/mode, duration/resolution tier,
    candidate semantics, estimated credit rule, effective_at,
    source/observed, confidence

Fail-closed rule (§19.1): a request with NO matching rule yields an
estimate with status UNKNOWN and blocks submit. The catalog is versioned:
a signature over all entries lets callers detect that an estimate (and any
approval bound to its estimate hash) became stale when the catalog changed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

COST_CATALOG_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class CostCatalogEntry:
    """One effective pricing rule (plan 05 §19.1)."""

    provider: str
    model: str
    operation: str  # e.g. "video_generation", "image_generation"
    mode: str = "standard"
    candidate_semantics: str = "per_candidate"  # per_candidate | per_request
    base_credits: int = 0
    per_second_credits: int = 0
    per_reference_credits: int = 0
    post_production_credits: int = 0
    effective_at: str = "1970-01-01"
    source: str = "observed"
    confidence: float = 1.0

    def signature(self) -> str:
        payload = json.dumps(
            {
                "provider": self.provider,
                "model": self.model,
                "operation": self.operation,
                "mode": self.mode,
                "candidate_semantics": self.candidate_semantics,
                "base_credits": self.base_credits,
                "per_second_credits": self.per_second_credits,
                "per_reference_credits": self.per_reference_credits,
                "post_production_credits": self.post_production_credits,
                "effective_at": self.effective_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CostCatalog:
    """Versioned, provenance-carrying cost catalog (plan 05 §19.1).

    Lookup is deterministic: exact match on provider/model/operation/mode,
    then the entry with the latest effective_at not after the caller's
    effective date. No match -> None (the estimator reports UNKNOWN and the
    budget policy blocks the submit).
    """

    def __init__(self, entries: Optional[List[CostCatalogEntry]] = None) -> None:
        self._entries: List[CostCatalogEntry] = list(entries or [])

    def entries(self) -> List[CostCatalogEntry]:
        return list(self._entries)

    def add(self, entry: CostCatalogEntry) -> None:
        self._entries.append(entry)

    def rule_for(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        mode: str = "standard",
        effective_at: str = "",
    ) -> Optional[CostCatalogEntry]:
        """Return the effective rule, or None when the rule is unknown.

        A request with an unknown rule is never estimated blindly: the caller
        must treat None as an UNKNOWN estimate and block the submit (§19.1).
        """
        candidates = [
            e
            for e in self._entries
            if e.provider == provider
            and e.model == model
            and e.operation == operation
            and e.mode == mode
        ]
        if not candidates:
            return None
        if effective_at:
            candidates = [e for e in candidates if e.effective_at <= effective_at]
            if not candidates:
                return None
        return max(candidates, key=lambda e: e.effective_at)

    def signature(self) -> str:
        """Deterministic fingerprint of the whole catalog (version + entries).

        An estimate stores the catalog signature it was computed against; when
        the signature changes, the estimate is stale (§19.2 — catalog change
        makes the old approval stale).
        """
        payload = json.dumps(
            {
                "schema_version": COST_CATALOG_SCHEMA_VERSION,
                "entries": [e.signature() for e in self._entries],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": COST_CATALOG_SCHEMA_VERSION,
            "signature": self.signature(),
            "entries": [
                {
                    "provider": e.provider,
                    "model": e.model,
                    "operation": e.operation,
                    "mode": e.mode,
                    "candidate_semantics": e.candidate_semantics,
                    "base_credits": e.base_credits,
                    "per_second_credits": e.per_second_credits,
                    "per_reference_credits": e.per_reference_credits,
                    "post_production_credits": e.post_production_credits,
                    "effective_at": e.effective_at,
                    "source": e.source,
                    "confidence": e.confidence,
                }
                for e in self._entries
            ],
        }


__all__ = [
    "COST_CATALOG_SCHEMA_VERSION",
    "CostCatalogEntry",
    "CostCatalog",
]
