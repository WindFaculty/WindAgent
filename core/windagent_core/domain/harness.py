"""Continual Harness Domain Models (Phase 10 — ban_ke_hoach_v1 §15, §16, §24).

Defines the core HarnessEntry, HarnessVersion, RefinementProposal entities,
entry kinds, lifecycle states, version chain invariants, and transition helpers.

Invariants:
- All domain records are immutable (frozen).
- Base system instructions, core security policy, permission model, audit policy,
  and promotion policy are strictly IMMUTABLE and cannot be altered by supplemental harness entries.
- Refinement flow is preview-first: /refine -> preview diff -> evaluate -> experiment -> promote -> commit HarnessVersion.
- Each HarnessVersion records its parent_version, exact diff, supporting evidence,
  evaluation results, and promotion decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HarnessEntryKind(str, Enum):
    """Kinds of supplemental harness entries (ban_ke_hoach_v1 §15)."""
    PROMPT_RULE = "prompt_rule"
    MEMORY_REF = "memory_ref"
    SKILL_REF = "skill_ref"
    SUBAGENT_SPEC = "subagent_spec"
    ROUTING_POLICY = "routing_policy"


class HarnessVersionStatus(str, Enum):
    """Lifecycle states of a harness version."""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    ROLLED_BACK = "rolled_back"


class RefinementStatus(str, Enum):
    """Lifecycle states of a refinement proposal (ban_ke_hoach_v1 §16)."""
    PREVIEW = "preview"
    EVALUATED = "evaluated"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class HarnessEntry(BaseModel):
    """Immutable domain entity representing a single supplemental harness entry.

    Entries can be prompt rules, memory references, skill references, subagent specs,
    or routing policies.
    """
    entry_id: str = Field(description="Unique entry identifier (e.g. 'hent_...').")
    kind: HarnessEntryKind = Field(description="Kind of harness entry.")
    name: str = Field(description="Human-readable entry name / key identifier.")
    content: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured content payload (rule text, reference IDs, configuration).",
    )
    priority: int = Field(
        default=100,
        ge=0,
        description="Priority order when assembling prompt or context (lower number = higher priority).",
    )
    enabled: bool = Field(default=True, description="Whether this entry is currently active/enabled.")
    scope: str = Field(default="project", description="Scope of application (e.g. 'project', 'global', 'local').")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension metadata.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def toggle(self, enabled: bool) -> HarnessEntry:
        """Returns a copy with updated enabled flag."""
        return self.model_copy(update={"enabled": enabled})

    def with_content(self, new_content: Dict[str, Any]) -> HarnessEntry:
        """Returns a copy with updated content."""
        return self.model_copy(update={"content": new_content})


class HarnessVersion(BaseModel):
    """Immutable domain entity representing a versioned continual harness state.

    Tracks a snapshot of supplemental entries, parent version link, exact diff,
    empirical evidence provenance, evaluation results, and promotion decisions.
    """
    version_id: str = Field(description="Unique harness version identifier (e.g. 'harness_v18').")
    version_number: int = Field(ge=1, description="Sequential integer version number.")
    parent_version: Optional[str] = Field(
        default=None,
        description="Version ID of the parent harness version (None for root/baseline v1).",
    )
    status: HarnessVersionStatus = Field(
        default=HarnessVersionStatus.DRAFT,
        description="Current lifecycle status.",
    )
    entries: List[HarnessEntry] = Field(
        default_factory=list,
        description="List of supplemental harness entries active in this version.",
    )
    diff: Dict[str, Any] = Field(
        default_factory=dict,
        description="Exact diff of additions, modifications, and deletions relative to parent version.",
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Evidence IDs (learning candidates, experiences, evaluations) supporting this version.",
    )
    promotion_decision: Dict[str, Any] = Field(
        default_factory=dict,
        description="Promotion decision record, rationale, and authority that approved this version.",
    )
    evaluation_set: Dict[str, Any] = Field(
        default_factory=dict,
        description="Benchmark and evaluation scores validating performance against baseline.",
    )
    created_by: str = Field(default="system", description="Author or agent identity that created this version.")
    project_id: Optional[str] = Field(default=None, description="Associated project ID if project-scoped.")
    domain: Optional[str] = Field(default=None, description="Domain classification (e.g. 'youtube', 'coding').")
    is_active: bool = Field(default=False, description="Whether this is the currently active version in its scope.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extension metadata.")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last updated timestamp in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def activate(self) -> HarnessVersion:
        """Transitions version to ACTIVE state."""
        return self.model_copy(
            update={
                "status": HarnessVersionStatus.ACTIVE,
                "is_active": True,
                "updated_at": utc_now(),
            }
        )

    def archive(self) -> HarnessVersion:
        """Transitions version to ARCHIVED state."""
        return self.model_copy(
            update={
                "status": HarnessVersionStatus.ARCHIVED,
                "is_active": False,
                "updated_at": utc_now(),
            }
        )

    def rollback(self, reason: str) -> HarnessVersion:
        """Transitions version to ROLLED_BACK state due to detected performance regression."""
        if not reason or not reason.strip():
            raise ValueError("Rollback reason cannot be empty.")

        updated_meta = dict(self.metadata)
        updated_meta["rollback_reason"] = reason.strip()
        updated_meta["rolled_back_at"] = utc_now().isoformat()

        return self.model_copy(
            update={
                "status": HarnessVersionStatus.ROLLED_BACK,
                "is_active": False,
                "metadata": updated_meta,
                "updated_at": utc_now(),
            }
        )

    def with_entry(self, entry: HarnessEntry) -> HarnessVersion:
        """Returns a new HarnessVersion with an entry added or updated."""
        existing_entries = [e for e in self.entries if e.entry_id != entry.entry_id]
        existing_entries.append(entry)
        return self.model_copy(
            update={
                "entries": existing_entries,
                "updated_at": utc_now(),
            }
        )

    def without_entry(self, entry_id: str) -> HarnessVersion:
        """Returns a new HarnessVersion with the specified entry removed."""
        filtered_entries = [e for e in self.entries if e.entry_id != entry_id]
        return self.model_copy(
            update={
                "entries": filtered_entries,
                "updated_at": utc_now(),
            }
        )

    def assert_invariants(self) -> bool:
        """Validates domain invariants for harness versions."""
        if self.version_number < 1:
            raise ValueError(f"Harness version_number must be >= 1, got {self.version_number}")
        if not self.version_id or not self.version_id.strip():
            raise ValueError("Harness version_id cannot be empty.")
        if self.version_number > 1 and not self.parent_version:
            raise ValueError(f"Harness version {self.version_id} (v{self.version_number}) must have a parent_version.")
        return True


class RefinementProposal(BaseModel):
    """Immutable domain entity representing a proposed harness refinement (/refine).

    Implements preview-first workflow: generates exact diff preview, holds evaluation
    results, and produces a new HarnessVersion only upon promotion.
    """
    refinement_id: str = Field(description="Unique refinement proposal identifier (e.g. 'ref_...').")
    target_harness_version: str = Field(description="Version ID of base harness being refined.")
    candidate_ids: List[str] = Field(
        default_factory=list,
        description="Learning candidate IDs driving this refinement.",
    )
    proposed_entries: List[HarnessEntry] = Field(
        default_factory=list,
        description="Proposed supplemental harness entries to add or update.",
    )
    preview_diff: Dict[str, Any] = Field(
        default_factory=dict,
        description="Exact preview diff showing additions, modifications, and deletions.",
    )
    status: RefinementStatus = Field(
        default=RefinementStatus.PREVIEW,
        description="Current proposal status (PREVIEW -> EVALUATED -> PROMOTED / REJECTED).",
    )
    evaluation_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Evaluation scores and comparison metrics against baseline.",
    )
    project_id: Optional[str] = Field(default=None, description="Project scope ID.")
    created_by: str = Field(default="system", description="Author or agent identity.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extension metadata.")

    created_at: datetime = Field(default_factory=utc_now, description="Creation timestamp in UTC.")
    updated_at: datetime = Field(default_factory=utc_now, description="Last updated timestamp in UTC.")

    model_config = ConfigDict(frozen=True, extra="forbid")

    def mark_evaluated(self, evaluation_results: Dict[str, Any]) -> RefinementProposal:
        """Transitions proposal to EVALUATED state with test / benchmark results."""
        if self.status not in (RefinementStatus.PREVIEW, RefinementStatus.EVALUATED):
            raise ValueError(f"Cannot evaluate proposal {self.refinement_id} from status {self.status.value}")

        return self.model_copy(
            update={
                "status": RefinementStatus.EVALUATED,
                "evaluation_results": evaluation_results,
                "updated_at": utc_now(),
            }
        )

    def reject(self, reason: str) -> RefinementProposal:
        """Transitions proposal to REJECTED state."""
        if not reason or not reason.strip():
            raise ValueError("Rejection reason cannot be empty.")

        updated_meta = dict(self.metadata)
        updated_meta["rejection_reason"] = reason.strip()
        updated_meta["rejected_at"] = utc_now().isoformat()

        return self.model_copy(
            update={
                "status": RefinementStatus.REJECTED,
                "metadata": updated_meta,
                "updated_at": utc_now(),
            }
        )

    def promote(
        self,
        new_version_id: str,
        new_version_number: int,
        base_version: HarnessVersion,
        promotion_authority: str = "promotion_gate",
    ) -> HarnessVersion:
        """Promotes proposal and creates a new immutable HarnessVersion linked in the version chain."""
        if self.status != RefinementStatus.EVALUATED:
            raise ValueError(
                f"Proposal {self.refinement_id} must be in EVALUATED status to be promoted, currently {self.status.value}"
            )

        # Merge base entries with proposed entries
        entry_map: Dict[str, HarnessEntry] = {e.entry_id: e for e in base_version.entries}
        for pe in self.proposed_entries:
            entry_map[pe.entry_id] = pe

        new_entries = sorted(entry_map.values(), key=lambda e: e.priority)

        promotion_record = {
            "refinement_id": self.refinement_id,
            "promoted_by": promotion_authority,
            "promoted_at": utc_now().isoformat(),
            "candidate_ids": self.candidate_ids,
        }

        return HarnessVersion(
            version_id=new_version_id,
            version_number=new_version_number,
            parent_version=base_version.version_id,
            status=HarnessVersionStatus.DRAFT,
            entries=new_entries,
            diff=self.preview_diff,
            evidence=list(self.candidate_ids),
            promotion_decision=promotion_record,
            evaluation_set=self.evaluation_results,
            created_by=self.created_by,
            project_id=self.project_id,
            is_active=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

