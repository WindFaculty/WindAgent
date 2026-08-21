"""
Unified Change Proposal Domain Service & Aggregate (Stage F — UI37).

Enforces the Human Production Control Layer over AI/Agent proposed changes.
Guarantees AI cannot directly mutate screenplay, asset binding, license, or approval
state without explicit proposal, impact preview, and human/policy approval.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.screenplay_diff import ScreenplayDiffEngine
from windagent_core.domain.video_production.screenplay_impact import ProductionImpactAnalyzer
from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError, DomainError


class ProposalStatus(str, Enum):
    PENDING = "PENDING"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    APPLY_FAILED = "APPLY_FAILED"


class ProposalType(str, Enum):
    SCREENPLAY_CHANGE = "SCREENPLAY_CHANGE"
    ASSET_BINDING_CHANGE = "ASSET_BINDING_CHANGE"
    LICENSE_CHANGE = "LICENSE_CHANGE"
    ASSET_APPROVAL_CHANGE = "ASSET_APPROVAL_CHANGE"


class ProductionChangeProposal(BaseModel):
    proposal_id: str
    proposal_type: ProposalType
    project_id: str
    target_revision_id: str
    base_sequence: int = 1
    affected_entities: List[str] = Field(default_factory=list)
    candidate: Dict[str, Any] = Field(default_factory=dict)
    diff: Dict[str, Any] = Field(default_factory=dict)
    impact: Dict[str, Any] = Field(default_factory=dict)
    created_by_agent: str
    created_at: str
    status: ProposalStatus = ProposalStatus.PENDING
    decision_by: Optional[str] = None
    decision_at: Optional[str] = None
    decision_reason: Optional[str] = None
    resulting_command_id: Optional[str] = None
    resulting_revision_id: Optional[str] = None
    version: int = 1
    hash: str


def compute_proposal_hash(candidate_payload: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of proposal candidate payload."""
    serialized = json.dumps(candidate_payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class SensitiveOperationPolicy:
    """Policy engine enforcing human control boundaries over agent actions."""

    SENSITIVE_OPERATIONS = {
        ProposalType.SCREENPLAY_CHANGE,
        ProposalType.ASSET_BINDING_CHANGE,
        ProposalType.LICENSE_CHANGE,
        ProposalType.ASSET_APPROVAL_CHANGE,
    }

    @classmethod
    def is_agent_actor(cls, actor: str) -> bool:
        """Check if actor string represents an AI/agent."""
        actor_lower = actor.lower()
        return actor_lower.startswith("agent:") or "agent" in actor_lower or "ai" in actor_lower

    @classmethod
    def validate_command_execution(
        cls,
        operation_type: ProposalType,
        actor: str,
        approved_proposal: Optional[ProductionChangeProposal] = None,
    ) -> None:
        """Validate if actor can execute sensitive operation directly."""
        if cls.is_agent_actor(actor):
            if not approved_proposal or approved_proposal.status != ProposalStatus.APPROVED:
                raise PermissionDeniedError(
                    f"Agent actor '{actor}' cannot execute sensitive operation '{operation_type.value}' directly. "
                    "An approved proposal is required.",
                    code="AGENT_SENSITIVE_OPERATION_BLOCKED",
                )

    @classmethod
    def validate_approval_permissions(
        cls,
        proposal: ProductionChangeProposal,
        approver_actor: str,
        prohibit_self_approval: bool = True,
    ) -> None:
        """Enforce approval role and anti-self-approval rules."""
        if cls.is_agent_actor(approver_actor) and not cls.is_agent_actor(proposal.created_by_agent):
            raise PermissionDeniedError(
                f"Agent '{approver_actor}' cannot approve human-created proposal '{proposal.proposal_id}'.",
                code="AGENT_APPROVAL_DISALLOWED",
            )

        if prohibit_self_approval and cls.is_agent_actor(proposal.created_by_agent):
            if approver_actor.strip().lower() == proposal.created_by_agent.strip().lower():
                raise PermissionDeniedError(
                    f"Proposal creator agent '{proposal.created_by_agent}' cannot self-approve proposal '{proposal.proposal_id}'.",
                    code="SELF_APPROVAL_PROHIBITED",
                )


class UniversalProposalService:
    """Manages the creation, stale checking, approval, and rejection of ProductionChangeProposals."""

    _proposals_store: Dict[str, ProductionChangeProposal] = {}

    @classmethod
    def clear_store(cls) -> None:
        cls._proposals_store.clear()

    @classmethod
    def create_proposal(
        cls,
        project_id: str,
        proposal_type: ProposalType | str,
        target_revision_id: str,
        base_sequence: int,
        creator_actor: str,
        candidate_payload: Dict[str, Any],
        affected_entities: Optional[List[str]] = None,
        base_payload: Optional[Dict[str, Any]] = None,
    ) -> ProductionChangeProposal:
        if isinstance(proposal_type, str):
            proposal_type = ProposalType(proposal_type)

        proposal_id = f"prop_{uuid.uuid4().hex[:10]}"
        content_hash = compute_proposal_hash(candidate_payload)
        now_str = datetime.now(timezone.utc).isoformat()

        diff_dict: Dict[str, Any] = {}
        impact_dict: Dict[str, Any] = {}

        if base_payload and proposal_type == ProposalType.SCREENPLAY_CHANGE:
            diff_res = ScreenplayDiffEngine.compare(base_payload, candidate_payload)
            diff_dict = diff_res.model_dump()
            impact_res = ProductionImpactAnalyzer.analyze_impact(project_id, diff_res)
            impact_dict = impact_res.model_dump()
        else:
            diff_dict = {
                "changes_count": len(candidate_payload.keys()),
                "summary": f"Proposed candidate changes for {proposal_type.value}",
            }
            impact_dict = {
                "invalidation_intent": "INVALIDATE_SHOT_PLAN" if proposal_type == ProposalType.SCREENPLAY_CHANGE else "NONE",
                "affected_entities_count": len(affected_entities or []),
                "summary": "Impact assessment complete.",
            }

        proposal = ProductionChangeProposal(
            proposal_id=proposal_id,
            proposal_type=proposal_type,
            project_id=project_id,
            target_revision_id=target_revision_id,
            base_sequence=base_sequence,
            affected_entities=affected_entities or [],
            candidate=candidate_payload,
            diff=diff_dict,
            impact=impact_dict,
            created_by_agent=creator_actor,
            created_at=now_str,
            status=ProposalStatus.PENDING,
            version=1,
            hash=content_hash,
        )

        cls._proposals_store[proposal_id] = proposal
        return proposal

    @classmethod
    def get_proposal(cls, proposal_id: str) -> Optional[ProductionChangeProposal]:
        return cls._proposals_store.get(proposal_id)

    @classmethod
    def list_proposals(
        cls,
        project_id: Optional[str] = None,
        status: Optional[ProposalStatus | str] = None,
        proposal_type: Optional[ProposalType | str] = None,
    ) -> List[ProductionChangeProposal]:
        results = list(cls._proposals_store.values())
        if project_id:
            results = [p for p in results if p.project_id == project_id]
        if status:
            status_str = status.value if hasattr(status, "value") else str(status)
            results = [p for p in results if p.status.value == status_str]
        if proposal_type:
            pt_str = proposal_type.value if hasattr(proposal_type, "value") else str(proposal_type)
            results = [p for p in results if p.proposal_type.value == pt_str]
        return results

    @classmethod
    def evaluate_stale_status(
        cls,
        proposal_id: str,
        current_project_sequence: int,
    ) -> ProductionChangeProposal:
        proposal = cls._proposals_store.get(proposal_id)
        if not proposal:
            raise ValidationError(f"Proposal '{proposal_id}' not found.")

        if proposal.status == ProposalStatus.PENDING and current_project_sequence > proposal.base_sequence:
            proposal.status = ProposalStatus.REQUIRES_REVIEW
            proposal.version += 1

        return proposal

    @classmethod
    async def approve_proposal(
        cls,
        proposal_id: str,
        approver_actor: str,
        current_project_sequence: int,
        command_dispatcher: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
        reason: str = "Human approval",
    ) -> ProductionChangeProposal:
        proposal = cls._proposals_store.get(proposal_id)
        if not proposal:
            raise ValidationError(f"Proposal '{proposal_id}' not found.")

        # Check idempotent double-approve
        if proposal.status == ProposalStatus.APPROVED:
            return proposal

        if proposal.status in (ProposalStatus.REJECTED, ProposalStatus.SUPERSEDED, ProposalStatus.EXPIRED):
            raise DomainError(
                f"Cannot approve proposal '{proposal_id}' in terminal state '{proposal.status.value}'.",
                code="PROPOSAL_TERMINAL_STATE",
            )

        # Enforce content integrity hash
        current_hash = compute_proposal_hash(proposal.candidate)
        if current_hash != proposal.hash:
            proposal.status = ProposalStatus.APPLY_FAILED
            raise ValidationError(
                f"Proposal '{proposal_id}' candidate payload hash mismatch (tamper detected).",
                code="PROPOSAL_HASH_TAMPERED",
            )

        # Evaluate stale status
        if current_project_sequence > proposal.base_sequence:
            proposal.status = ProposalStatus.REQUIRES_REVIEW
            raise DomainError(
                f"Proposal '{proposal_id}' is stale. Target sequence has advanced to {current_project_sequence}. Review required.",
                code="PROPOSAL_STALE_REVIEW_REQUIRED",
            )

        # Enforce security policies
        SensitiveOperationPolicy.validate_approval_permissions(proposal, approver_actor)

        now_str = datetime.now(timezone.utc).isoformat()
        resulting_cmd_id = f"cmd_prop_{uuid.uuid4().hex[:8]}"
        resulting_rev_id = f"rev_{uuid.uuid4().hex[:8]}"

        # Dispatch canonical command if dispatcher provided
        if command_dispatcher:
            from windagent_core.domain.video_production.workspace import WorkspaceCommandRequest, WorkspaceCommandType
            cmd_type = WorkspaceCommandType.UPDATE_SCREENPLAY if proposal.proposal_type == ProposalType.SCREENPLAY_CHANGE else WorkspaceCommandType.UPDATE_ASSET
            req = WorkspaceCommandRequest(
                command_id=resulting_cmd_id,
                command_type=cmd_type,
                project_id=proposal.project_id,
                target_revision_id=proposal.target_revision_id,
                entity_id=proposal.affected_entities[0] if proposal.affected_entities else "entity_main",
                reason=reason,
                idempotency_key=idempotency_key or f"idem_prop_{proposal_id}",
                payload=proposal.candidate,
                client_context={"approved_proposal_id": proposal.proposal_id, "approver": approver_actor},
            )
            cmd_result = await command_dispatcher.dispatch(req)
            resulting_rev_id = cmd_result.get("updated_revision_id", resulting_rev_id)

        proposal.status = ProposalStatus.APPROVED
        proposal.decision_by = approver_actor
        proposal.decision_at = now_str
        proposal.decision_reason = reason
        proposal.resulting_command_id = resulting_cmd_id
        proposal.resulting_revision_id = resulting_rev_id
        proposal.version += 1

        return proposal

    @classmethod
    def reject_proposal(
        cls,
        proposal_id: str,
        rejector_actor: str,
        reason: str,
    ) -> ProductionChangeProposal:
        proposal = cls._proposals_store.get(proposal_id)
        if not proposal:
            raise ValidationError(f"Proposal '{proposal_id}' not found.")

        if proposal.status == ProposalStatus.APPROVED:
            raise DomainError(
                f"Cannot reject already approved proposal '{proposal_id}'.",
                code="PROPOSAL_ALREADY_APPROVED",
            )

        now_str = datetime.now(timezone.utc).isoformat()
        proposal.status = ProposalStatus.REJECTED
        proposal.decision_by = rejector_actor
        proposal.decision_at = now_str
        proposal.decision_reason = reason
        proposal.version += 1

        return proposal
