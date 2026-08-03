"""
Phase 10 — Continuity Ledger result types (plan 03 §17-§21).

`ContinuityLedgerReceipt` is the immutable result of
`ContinuityLedgerService.build`: the full traceable ledger (per-shot
incoming/required/outgoing state, allowed+planned changes, assertions,
human overrides and diffs), the deterministic ledger hash tied to the
source graph/plan/package hashes, and the typed continuity issues.

A blocking continuity issue means the revision cannot be rendered until the
defect is resolved (or an audited human override is recorded) — the ledger
never rewrites retroactive evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from windagent_core.domain.video_production.continuity import (
    ContinuityLedger,
    ContinuityIssue,
)


@dataclass(frozen=True)
class ContinuityLedgerReceipt:
    """Result of continuity ledger building — never a partial ledger."""

    ledger: ContinuityLedger
    issues: List[ContinuityIssue] = field(default_factory=list)
    ledger_hash: str = ""
    source_graph_hash: str = ""
    source_plan_hash: str = ""
    source_package_hash: str = ""
    ledger_version: str = "1.0.0"

    @property
    def blocking_issues(self) -> List[ContinuityIssue]:
        return [i for i in self.issues if i.blocking]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger": self.ledger.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "ledger_hash": self.ledger_hash,
            "source_graph_hash": self.source_graph_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_package_hash": self.source_package_hash,
            "ledger_version": self.ledger_version,
        }


__all__ = ["ContinuityLedgerReceipt"]
