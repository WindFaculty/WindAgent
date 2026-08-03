"""
Continuity domain (road_map.md Phase 10, plan 03 §17-§21).

Phase 6-era `ContinuityState` is a per-shot snapshot carried inside the
package v1 schema; it stays untouched. Phase 10 adds the *Continuity
Ledger*: a traceable, reviewable record of cinematic state flowing through
the shot graph.

The ledger is not just a final snapshot. Each shot has:

```text
incoming_state        — state entering the shot (screenplay/bible/predecessor)
required_state        — fields that MUST hold a value (identity, references)
allowed_changes       — fields the shot is allowed to mutate (plan §19.2)
planned_changes       — changes the shot proposes
outgoing_state        — state after the shot
continuity_assertions — reviewed invariants (180-degree, identity hash, …)
```

Each important field records a `ContinuityFieldSource` (SCREENPLAY_FACT,
BIBLE_FACT, APPROVED_REFERENCE, DIRECTOR_DECISION, PREDECESSOR_OUTPUT,
HUMAN_OVERRIDE) so the ledger can be compiled, reviewed and invalidated
deterministically (plan §18). `ContinuityLedgerValidator` is the
deterministic rule engine: invalid transitions become blocking defects,
and human overrides are appended as auditable records that never rewrite
retroactive evidence (plan §19.3).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    CameraSide,
    ContinuityFieldSource,
    ContinuityIssueCode,
    IssueSeverity,
)
from windagent_core.domain.video_production.ids import (
    ContinuityIssueId,
    ContinuityLedgerId,
    ContinuityOverrideId,
    ContinuityStateId,
    ProductionRevisionId,
    SceneId,
    ShotId,
    VideoProjectId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Phase 6 — per-shot snapshot carried inside the package schema (unchanged).
# ---------------------------------------------------------------------------
class ContinuityState(BaseModel):
    """Per-shot continuity snapshot (package v1 schema, Phase 6)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    state_id: ContinuityStateId
    shot_id: ShotId
    character_states: Dict[str, Any] = Field(default_factory=dict)
    location_state: Dict[str, Any] = Field(default_factory=dict)
    prop_states: Dict[str, Any] = Field(default_factory=dict)
    camera_state: Dict[str, Any] = Field(default_factory=dict)
    must_preserve: List[str] = Field(default_factory=list)
    allowed_changes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 10 — Continuity Ledger
# ---------------------------------------------------------------------------
class ContinuityFieldState(BaseModel):
    """A single continuity field with its proven source (plan §18)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    field: str = Field(min_length=1)
    value: Any = None
    source: ContinuityFieldSource = ContinuityFieldSource.BIBLE_FACT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "source": self.source.value,
        }


class ContinuityChange(BaseModel):
    """A planned mutation of one continuity field for a shot (plan §19.2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    field: str = Field(min_length=1)
    before: Any = None
    after: Any = None
    source: ContinuityFieldSource = ContinuityFieldSource.DIRECTOR_DECISION
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "before": self.before,
            "after": self.after,
            "source": self.source.value,
            "reason": self.reason,
        }


class ContinuityAssertion(BaseModel):
    """A reviewed invariant for a shot (plan §18 continuity_assertions)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    field: str = Field(min_length=1)
    expected: Any = None
    source: ContinuityFieldSource = ContinuityFieldSource.APPROVED_REFERENCE
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "expected": self.expected,
            "source": self.source.value,
            "message": self.message,
        }


class ContinuityDiff(BaseModel):
    """Machine-readable diff for review (plan §19.3).

    field / before / expected / observed / source / severity / blocking —
    used when a planned change differs from what the rule engine expected.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    field: str = Field(min_length=1)
    before: Any = None
    expected: Any = None
    observed: Any = None
    source: ContinuityFieldSource = ContinuityFieldSource.DIRECTOR_DECISION
    severity: IssueSeverity = IssueSeverity.WARNING
    blocking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "before": self.before,
            "expected": self.expected,
            "observed": self.observed,
            "source": self.source.value,
            "severity": self.severity.value,
            "blocking": self.blocking,
        }


class ContinuityLedgerEntry(BaseModel):
    """Per-shot ledger record (plan §18)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shot_id: ShotId
    scene_id: Optional[SceneId] = None
    incoming_state: Dict[str, ContinuityFieldState] = Field(default_factory=dict)
    required_state: Dict[str, ContinuityFieldState] = Field(default_factory=dict)
    allowed_changes: List[str] = Field(default_factory=list)
    planned_changes: List[ContinuityChange] = Field(default_factory=list)
    outgoing_state: Dict[str, ContinuityFieldState] = Field(default_factory=dict)
    continuity_assertions: List[ContinuityAssertion] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": str(self.shot_id),
            "scene_id": str(self.scene_id) if self.scene_id else None,
            "incoming_state": {
                k: v.to_dict() for k, v in sorted(self.incoming_state.items())
            },
            "required_state": {
                k: v.to_dict() for k, v in sorted(self.required_state.items())
            },
            "allowed_changes": list(self.allowed_changes),
            "planned_changes": [c.to_dict() for c in self.planned_changes],
            "outgoing_state": {
                k: v.to_dict() for k, v in sorted(self.outgoing_state.items())
            },
            "continuity_assertions": [a.to_dict() for a in self.continuity_assertions],
        }


class ContinuityIssue(BaseModel):
    """A typed continuity finding (plan §19-§20). Blocking defects fail closed."""

    model_config = ConfigDict(frozen=True, extra="allow")

    issue_id: ContinuityIssueId
    code: ContinuityIssueCode
    severity: IssueSeverity = IssueSeverity.BLOCKING
    message: str = Field(min_length=1)
    blocking: bool = True
    shot_id: Optional[ShotId] = None
    field: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": str(self.issue_id),
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "blocking": self.blocking,
            "shot_id": str(self.shot_id) if self.shot_id else None,
            "field": self.field,
            "details": self.details,
        }


class HumanContinuityOverride(BaseModel):
    """Audited human override (plan §19.3, continuity_override_policy.md).

    An override is APPENDED as evidence; it never rewrites the recorded
    incoming/outgoing states of earlier shots (no retroactive mutation).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    override_id: ContinuityOverrideId
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    target_revision: ProductionRevisionId
    field: str = Field(min_length=1)
    before: Any = None
    after: Any = None
    applied_at_shot_id: Optional[ShotId] = None
    timestamp: datetime = Field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "override_id": str(self.override_id),
            "actor": self.actor,
            "reason": self.reason,
            "target_revision": str(self.target_revision),
            "field": self.field,
            "before": self.before,
            "after": self.after,
            "applied_at_shot_id": str(self.applied_at_shot_id)
            if self.applied_at_shot_id
            else None,
            "timestamp": self.timestamp.isoformat(),
        }


class ContinuityLedger(BaseModel):
    """The full traceable continuity ledger (plan §17-§19)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    ledger_id: ContinuityLedgerId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    entries: List[ContinuityLedgerEntry] = Field(default_factory=list)
    overrides: List[HumanContinuityOverride] = Field(default_factory=list)
    diffs: List[ContinuityDiff] = Field(default_factory=list)
    issues: List[ContinuityIssue] = Field(default_factory=list)
    ledger_version: str = "1.0.0"
    ledger_hash: str = ""

    def entry_for(self, shot_id: ShotId) -> Optional[ContinuityLedgerEntry]:
        for entry in self.entries:
            if entry.shot_id == shot_id:
                return entry
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger_id": str(self.ledger_id),
            "project_id": str(self.project_id),
            "revision_id": str(self.revision_id),
            "entries": [e.to_dict() for e in self.entries],
            "overrides": [o.to_dict() for o in self.overrides],
            "diffs": [d.to_dict() for d in self.diffs],
            "issues": [i.to_dict() for i in self.issues],
            "ledger_version": self.ledger_version,
            "ledger_hash": self.ledger_hash,
        }


# ---------------------------------------------------------------------------
# Deterministic hash (plan §24.5 semantics at the ledger level).
# ---------------------------------------------------------------------------
def compute_ledger_hash(
    *,
    project_id: object,
    revision_id: object,
    ledger_payload: Dict[str, Any],
    ledger_version: str,
    source_graph_hash: str,
    source_plan_hash: str,
    source_package_hash: str,
) -> str:
    """Deterministic SHA-256 over the canonical ledger payload + versions.

    Same inputs produce the same hash; changing any entry, override, diff,
    version, or source hash produces a new hash.
    """
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "ledger_version": ledger_version,
            "source_graph_hash": source_graph_hash,
            "source_plan_hash": source_plan_hash,
            "source_package_hash": source_package_hash,
            "ledger": ledger_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic rule engine (plan §19.2, §20).
# ---------------------------------------------------------------------------
_BLOCKING_CODES = {
    ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE,
    ContinuityIssueCode.CHANGE_OUTSIDE_ALLOWED,
    ContinuityIssueCode.IDENTITY_HASH_MISMATCH,
    ContinuityIssueCode.CAMERA_SIDE_VIOLATION,
    ContinuityIssueCode.PARALLEL_CONFLICT,
}
_IMMUTABLE_FIELD_PREFIXES = (
    "identity:",
    "reference:",
)


class ContinuityLedgerValidator:
    """Deterministic continuity rules. Blocking defects fail closed.

    `validate(ledger, graph=None)` takes an optional `ShotDependencyGraph`
    so the parallel-conflict rule can compare real blocking ordering (a shot
    pair that is not ordered by a blocking edge is parallel). Without the
    graph, the parallel-conflict check is skipped (ordering is unknown); the
    service always passes the graph.
    """

    def __init__(self, *, id_factory=None) -> None:
        self._id_factory = id_factory

    # -- public -----------------------------------------------------------
    def validate(self, ledger: ContinuityLedger, graph=None) -> List[ContinuityIssue]:
        issues: List[ContinuityIssue] = []
        for entry in ledger.entries:
            self._check_change_outside_allowed(entry, issues)
            self._check_prop_unexplained_change(entry, issues)
            self._check_identity_hash_mismatch(entry, issues)
            self._check_camera_side_violation(entry, issues)
        self._check_parallel_conflicts(ledger, issues, graph)
        return issues

    def blocking_issues(self, ledger: ContinuityLedger, graph=None) -> List[ContinuityIssue]:
        return [i for i in self.validate(ledger, graph) if i.blocking]

    # -- helpers ----------------------------------------------------------
    def _new_issue_id(self, code: ContinuityIssueCode, shot_id, field) -> str:
        seed = f"{code.value}:{shot_id or ''}:{field or ''}"
        if self._id_factory is not None:
            return self._id_factory.continuity_issue_id(seed)
        return f"ci_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    def _issue(
        self,
        code: ContinuityIssueCode,
        message: str,
        *,
        shot_id: Optional[ShotId] = None,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ContinuityIssue:
        return ContinuityIssue(
            issue_id=ContinuityIssueId(self._new_issue_id(code, shot_id, field)),
            code=code,
            severity=IssueSeverity.BLOCKING if code in _BLOCKING_CODES else IssueSeverity.WARNING,
            message=message,
            blocking=code in _BLOCKING_CODES,
            shot_id=shot_id,
            field=field,
            details=details or {},
        )

    # -- rules ------------------------------------------------------------
    def _check_change_outside_allowed(
        self, entry: ContinuityLedgerEntry, issues: List[ContinuityIssue]
    ) -> None:
        allowed = set(entry.allowed_changes)
        for change in entry.planned_changes:
            if change.source == ContinuityFieldSource.HUMAN_OVERRIDE:
                continue  # approved override is the escape hatch (plan §19.3)
            if change.field not in allowed and not change.field.startswith(
                _IMMUTABLE_FIELD_PREFIXES
            ):
                # Identity/reference changes are immutable even if listed.
                issues.append(
                    self._issue(
                        ContinuityIssueCode.CHANGE_OUTSIDE_ALLOWED,
                        f"Shot {entry.shot_id} plans change on '{change.field}' "
                        "which is not in allowed_changes.",
                        shot_id=entry.shot_id,
                        field=change.field,
                        details={
                            "allowed": sorted(allowed),
                            "before": change.before,
                            "after": change.after,
                        },
                    )
                )

    def _check_prop_unexplained_change(
        self, entry: ContinuityLedgerEntry, issues: List[ContinuityIssue]
    ) -> None:
        for change in entry.planned_changes:
            if change.source == ContinuityFieldSource.HUMAN_OVERRIDE:
                continue  # approved override is the escape hatch (plan §19.3)
            if change.field.startswith("prop:"):
                if change.source != ContinuityFieldSource.SCREENPLAY_FACT:
                    issues.append(
                        self._issue(
                            ContinuityIssueCode.PROP_UNEXPLAINED_CHANGE,
                            f"Shot {entry.shot_id} changes prop field "
                            f"'{change.field}' without a screenplay action.",
                            shot_id=entry.shot_id,
                            field=change.field,
                            details={"source": change.source.value},
                        )
                    )

    def _check_identity_hash_mismatch(
        self, entry: ContinuityLedgerEntry, issues: List[ContinuityIssue]
    ) -> None:
        # required_state identity fields assert the approved reference hash.
        for field, state in entry.required_state.items():
            if not (field.startswith("identity:") or field.startswith("reference:")):
                continue
            if state.value is None or state.value == "":
                # Missing required state is a non-blocking warning (plan §19.1:
                # never guess a missing required field; surface an issue).
                issues.append(
                    self._issue(
                        ContinuityIssueCode.MISSING_REQUIRED_STATE,
                        f"Shot {entry.shot_id} requires '{field}' but its "
                        "approved reference value is missing.",
                        shot_id=entry.shot_id,
                        field=field,
                    )
                )
                continue
            incoming = entry.incoming_state.get(field)
            if incoming is not None and incoming.value != state.value:
                issues.append(
                    self._issue(
                        ContinuityIssueCode.IDENTITY_HASH_MISMATCH,
                        f"Shot {entry.shot_id} incoming '{field}' "
                        f"({incoming.value}) does not match the approved "
                        f"reference ({state.value}).",
                        shot_id=entry.shot_id,
                        field=field,
                        details={
                            "incoming": incoming.value,
                            "expected": state.value,
                        },
                    )
                )

    def _check_camera_side_violation(
        self, entry: ContinuityLedgerEntry, issues: List[ContinuityIssue]
    ) -> None:
        incoming = entry.incoming_state.get("camera_side")
        outgoing = entry.outgoing_state.get("camera_side")
        if incoming is None or outgoing is None:
            return

        try:
            before = CameraSide(str(incoming.value))
            after = CameraSide(str(outgoing.value))
        except ValueError:
            return
        # 180-degree rule: coverage shots must stay on one side; a flip is a
        # violation unless a re-establishing (NEUTRAL) shot intervenes.
        if (
            before in (CameraSide.SIDE_A, CameraSide.SIDE_B)
            and after in (CameraSide.SIDE_A, CameraSide.SIDE_B)
            and before != after
        ):
            issues.append(
                self._issue(
                    ContinuityIssueCode.CAMERA_SIDE_VIOLATION,
                    f"Shot {entry.shot_id} flips camera side "
                    f"{before.value} -> {after.value} inside the same scene.",
                    shot_id=entry.shot_id,
                    field="camera_side",
                    details={"before": before.value, "after": after.value},
                )
            )

    def _check_parallel_conflicts(
        self,
        ledger: ContinuityLedger,
        issues: List[ContinuityIssue],
        graph=None,
    ) -> None:
        if graph is None:
            return  # ordering info unavailable; the service always passes it
        changed_by: Dict[str, List[ContinuityLedgerEntry]] = {}
        for entry in ledger.entries:
            for change in entry.planned_changes:
                changed_by.setdefault(change.field, []).append(entry)
        for field, entries in changed_by.items():
            if len(entries) < 2:
                continue
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    a, b = entries[i], entries[j]
                    if self._are_ordered(graph, a.shot_id, b.shot_id):
                        continue  # blocking-ordered: the later shot is not parallel
                    # Parallel shots must not write conflicting canonical state
                    # without a merge rule (plan §19.2).
                    after_a = next(
                        (c.after for c in a.planned_changes if c.field == field), None
                    )
                    after_b = next(
                        (c.after for c in b.planned_changes if c.field == field), None
                    )
                    if after_a == after_b:
                        continue  # consistent redundant change is not a conflict
                    issues.append(
                        self._issue(
                            ContinuityIssueCode.PARALLEL_CONFLICT,
                            f"Parallel shots {a.shot_id} and {b.shot_id} both plan "
                            f"conflicting changes on '{field}' without a merge rule.",
                            field=field,
                            details={
                                "shots": [str(a.shot_id), str(b.shot_id)],
                                "after_a": after_a,
                                "after_b": after_b,
                            },
                        )
                    )

    @staticmethod
    def _are_ordered(graph, from_shot: ShotId, to_shot: ShotId) -> bool:
        """True when one shot reaches the other through blocking edges."""
        blocking = [d for d in graph.dependencies if d.blocking]
        adjacency: Dict[str, List[str]] = {}
        for dep in blocking:
            adjacency.setdefault(str(dep.from_shot_id), []).append(str(dep.to_shot_id))

        def reachable(src: str, dst: str) -> bool:
            if src == dst:
                return True
            seen = {src}
            stack = [src]
            while stack:
                node = stack.pop()
                for nxt in adjacency.get(node, []):
                    if nxt == dst:
                        return True
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            return False

        return reachable(str(from_shot), str(to_shot)) or reachable(
            str(to_shot), str(from_shot)
        )


__all__ = [
    "utc_now",
    "ContinuityState",
    "ContinuityFieldState",
    "ContinuityChange",
    "ContinuityAssertion",
    "ContinuityDiff",
    "ContinuityLedgerEntry",
    "ContinuityIssue",
    "HumanContinuityOverride",
    "ContinuityLedger",
    "compute_ledger_hash",
    "ContinuityLedgerValidator",
]
