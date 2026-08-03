"""
Phase 10 — Continuity Ledger (plan 03 §17-§21).

The `ContinuityLedgerService` turns a package + Phase 9 shot graph into a
traceable, reviewable continuity ledger: per-shot incoming/required/outgoing
state with proven sources, allowed + planned changes, continuity assertions,
audited human overrides and machine-readable diffs. Blocking defects (unexplained
prop change, change outside allowed set, identity/reference hash mismatch,
180-degree camera-side violation, parallel-branch conflict) are recorded and
fail closed before rendering. Fully deterministic — never calls a provider.
"""

from windagent_intelligence.video.continuity.models import ContinuityLedgerReceipt
from windagent_intelligence.video.continuity.service import ContinuityLedgerService

__all__ = ["ContinuityLedgerService", "ContinuityLedgerReceipt"]
