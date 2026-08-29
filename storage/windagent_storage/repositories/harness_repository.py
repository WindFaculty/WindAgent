"""Continual Harness & Refinement Proposal Repository (Async SQL) for Phase 10 (ban_ke_hoach_v1 §15, §16, §24)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windagent_core.domain.harness import (
    HarnessEntry,
    HarnessEntryKind,
    HarnessVersion,
    HarnessVersionStatus,
    RefinementProposal,
    RefinementStatus,
)
from windagent_storage.orm.harness_models import HarnessVersionORM, RefinementProposalORM

logger = logging.getLogger("windagent.storage.repositories.harness")


class HarnessRepository:
    """Durable async repository for storing and querying HarnessVersions and RefinementProposals."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _version_to_domain(self, orm: HarnessVersionORM) -> HarnessVersion:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        raw_entries = _parse_json(orm.entries_json, [])
        entries = []
        for e in raw_entries:
            if isinstance(e, dict):
                entries.append(
                    HarnessEntry(
                        entry_id=e.get("entry_id", ""),
                        kind=HarnessEntryKind(e.get("kind", "prompt_rule")),
                        name=e.get("name", ""),
                        content=e.get("content", {}),
                        priority=e.get("priority", 100),
                        enabled=e.get("enabled", True),
                        scope=e.get("scope", "project"),
                        metadata=e.get("metadata", {}),
                    )
                )

        return HarnessVersion(
            version_id=orm.id,
            version_number=orm.version_number,
            parent_version=orm.parent_version,
            status=HarnessVersionStatus(orm.status),
            entries=entries,
            diff=_parse_json(orm.diff_json, {}),
            evidence=_parse_json(orm.evidence_json, []),
            promotion_decision=_parse_json(orm.promotion_decision_json, {}),
            evaluation_set=_parse_json(orm.evaluation_set_json, {}),
            created_by=orm.created_by,
            project_id=orm.project_id,
            domain=orm.domain,
            is_active=bool(orm.is_active),
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _refinement_to_domain(self, orm: RefinementProposalORM) -> RefinementProposal:
        def _parse_json(val: Optional[str], default: Any) -> Any:
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        raw_entries = _parse_json(orm.proposed_entries_json, [])
        entries = []
        for e in raw_entries:
            if isinstance(e, dict):
                entries.append(
                    HarnessEntry(
                        entry_id=e.get("entry_id", ""),
                        kind=HarnessEntryKind(e.get("kind", "prompt_rule")),
                        name=e.get("name", ""),
                        content=e.get("content", {}),
                        priority=e.get("priority", 100),
                        enabled=e.get("enabled", True),
                        scope=e.get("scope", "project"),
                        metadata=e.get("metadata", {}),
                    )
                )

        return RefinementProposal(
            refinement_id=orm.id,
            target_harness_version=orm.target_harness_version,
            candidate_ids=_parse_json(orm.candidate_ids_json, []),
            proposed_entries=entries,
            preview_diff=_parse_json(orm.preview_diff_json, {}),
            status=RefinementStatus(orm.status),
            evaluation_results=_parse_json(orm.evaluation_results_json, {}),
            project_id=orm.project_id,
            created_by=orm.created_by,
            metadata=_parse_json(orm.metadata_json, {}),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def save_version(
        self,
        version: Union[HarnessVersion, Dict[str, Any]],
    ) -> HarnessVersion:
        """Persists or updates a HarnessVersion record."""
        if not isinstance(version, HarnessVersion):
            version = HarnessVersion.model_validate(version)

        now = datetime.now(timezone.utc)
        entries_json = json.dumps([e.model_dump() for e in version.entries], default=str)
        diff_json = json.dumps(version.diff, default=str)
        evidence_json = json.dumps(version.evidence, default=str)
        promotion_json = json.dumps(version.promotion_decision, default=str)
        eval_json = json.dumps(version.evaluation_set, default=str)
        metadata_json = json.dumps(version.metadata, default=str)

        existing = await self._session.get(HarnessVersionORM, version.version_id)
        if not existing:
            orm = HarnessVersionORM(
                id=version.version_id,
                version_number=version.version_number,
                parent_version=version.parent_version,
                status=version.status.value,
                entries_json=entries_json,
                diff_json=diff_json,
                evidence_json=evidence_json,
                promotion_decision_json=promotion_json,
                evaluation_set_json=eval_json,
                created_by=version.created_by,
                project_id=version.project_id,
                domain=version.domain,
                is_active=version.is_active,
                metadata_json=metadata_json,
                created_at=version.created_at or now,
                updated_at=version.updated_at or now,
            )
            self._session.add(orm)
            await self._session.flush()
            return version

        existing.version_number = version.version_number
        existing.parent_version = version.parent_version
        existing.status = version.status.value
        existing.entries_json = entries_json
        existing.diff_json = diff_json
        existing.evidence_json = evidence_json
        existing.promotion_decision_json = promotion_json
        existing.evaluation_set_json = eval_json
        existing.created_by = version.created_by
        existing.project_id = version.project_id
        existing.domain = version.domain
        existing.is_active = version.is_active
        existing.metadata_json = metadata_json
        existing.updated_at = now
        await self._session.flush()
        return version

    async def get_version_by_id(self, version_id: str) -> Optional[HarnessVersion]:
        """Retrieves a single HarnessVersion by ID."""
        orm = await self._session.get(HarnessVersionORM, version_id)
        if not orm:
            return None
        return self._version_to_domain(orm)

    async def get_version(self, version_id: str) -> Optional[HarnessVersion]:
        """Retrieves a single HarnessVersion by ID (conforms to HarnessRepositoryProtocol)."""
        return await self.get_version_by_id(version_id)

    async def get_active_version(
        self,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Optional[HarnessVersion]:
        """Retrieves the currently active HarnessVersion for a project or global scope."""
        stmt = select(HarnessVersionORM).where(HarnessVersionORM.is_active == True)  # noqa: E712
        if project_id:
            stmt = stmt.where(HarnessVersionORM.project_id == project_id)
        if domain:
            stmt = stmt.where(HarnessVersionORM.domain == domain)

        stmt = stmt.order_by(HarnessVersionORM.version_number.desc()).limit(1)
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        if not orm:
            return None
        return self._version_to_domain(orm)

    async def set_active_version(
        self,
        version_id: str,
        project_id: Optional[str] = None,
    ) -> HarnessVersion:
        """Sets target version as active, deactivating previously active versions in the scope."""
        target = await self._session.get(HarnessVersionORM, version_id)
        if not target:
            raise ValueError(f"Harness version {version_id} not found.")

        # Deactivate all active versions in matching scope
        deactivate_stmt = update(HarnessVersionORM).where(HarnessVersionORM.is_active == True)  # noqa: E712
        if project_id:
            deactivate_stmt = deactivate_stmt.where(HarnessVersionORM.project_id == project_id)
        else:
            deactivate_stmt = deactivate_stmt.where(HarnessVersionORM.project_id == target.project_id)

        deactivate_stmt = deactivate_stmt.values(is_active=False, status=HarnessVersionStatus.ARCHIVED.value)
        await self._session.execute(deactivate_stmt)

        # Activate target
        target.is_active = True
        target.status = HarnessVersionStatus.ACTIVE.value
        target.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return self._version_to_domain(target)

    async def list_versions(
        self,
        project_id: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[HarnessVersionStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[HarnessVersion]:
        """Lists harness versions ordered by version_number descending."""
        stmt = select(HarnessVersionORM)
        if project_id:
            stmt = stmt.where(HarnessVersionORM.project_id == project_id)
        if domain:
            stmt = stmt.where(HarnessVersionORM.domain == domain)
        if status:
            stmt = stmt.where(HarnessVersionORM.status == status.value)

        stmt = stmt.order_by(HarnessVersionORM.version_number.desc(), HarnessVersionORM.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        res = await self._session.execute(stmt)
        return [self._version_to_domain(r) for r in res.scalars().all()]

    async def rollback_version(
        self,
        version_id: str,
        reason: str,
        fallback_to_parent: bool = True,
    ) -> HarnessVersion:
        """Marks version as ROLLED_BACK and optionally re-activates its parent version."""
        target = await self._session.get(HarnessVersionORM, version_id)
        if not target:
            raise ValueError(f"Harness version {version_id} not found.")

        now = datetime.now(timezone.utc)
        target.status = HarnessVersionStatus.ROLLED_BACK.value
        target.is_active = False
        try:
            meta = json.loads(target.metadata_json or "{}")
        except Exception:
            meta = {}
        meta["rollback_reason"] = reason
        meta["rolled_back_at"] = now.isoformat()
        target.metadata_json = json.dumps(meta, default=str)
        target.updated_at = now

        if fallback_to_parent and target.parent_version:
            parent = await self._session.get(HarnessVersionORM, target.parent_version)
            if parent:
                parent.is_active = True
                parent.status = HarnessVersionStatus.ACTIVE.value
                parent.updated_at = now

        await self._session.flush()
        return self._version_to_domain(target)

    async def delete_version(self, version_id: str) -> bool:
        """Deletes a harness version record."""
        orm = await self._session.get(HarnessVersionORM, version_id)
        if not orm:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

    async def save_refinement(
        self,
        proposal: Union[RefinementProposal, Dict[str, Any]],
    ) -> RefinementProposal:
        """Persists or updates a RefinementProposal record."""
        if not isinstance(proposal, RefinementProposal):
            proposal = RefinementProposal.model_validate(proposal)

        now = datetime.now(timezone.utc)
        cand_ids_json = json.dumps(proposal.candidate_ids, default=str)
        entries_json = json.dumps([e.model_dump() for e in proposal.proposed_entries], default=str)
        diff_json = json.dumps(proposal.preview_diff, default=str)
        eval_json = json.dumps(proposal.evaluation_results, default=str)
        meta_json = json.dumps(proposal.metadata, default=str)

        existing = await self._session.get(RefinementProposalORM, proposal.refinement_id)
        if not existing:
            orm = RefinementProposalORM(
                id=proposal.refinement_id,
                target_harness_version=proposal.target_harness_version,
                candidate_ids_json=cand_ids_json,
                proposed_entries_json=entries_json,
                preview_diff_json=diff_json,
                status=proposal.status.value,
                evaluation_results_json=eval_json,
                project_id=proposal.project_id,
                created_by=proposal.created_by,
                metadata_json=meta_json,
                created_at=proposal.created_at or now,
                updated_at=proposal.updated_at or now,
            )
            self._session.add(orm)
            await self._session.flush()
            return proposal

        existing.target_harness_version = proposal.target_harness_version
        existing.candidate_ids_json = cand_ids_json
        existing.proposed_entries_json = entries_json
        existing.preview_diff_json = diff_json
        existing.status = proposal.status.value
        existing.evaluation_results_json = eval_json
        existing.project_id = proposal.project_id
        existing.created_by = proposal.created_by
        existing.metadata_json = meta_json
        existing.updated_at = now
        await self._session.flush()
        return proposal

    async def get_refinement_by_id(self, refinement_id: str) -> Optional[RefinementProposal]:
        """Retrieves a single RefinementProposal by ID."""
        orm = await self._session.get(RefinementProposalORM, refinement_id)
        if not orm:
            return None
        return self._refinement_to_domain(orm)

    async def list_refinements(
        self,
        project_id: Optional[str] = None,
        target_version: Optional[str] = None,
        status: Optional[RefinementStatus] = None,
        limit: int = 100,
    ) -> List[RefinementProposal]:
        """Lists refinement proposals matching criteria."""
        stmt = select(RefinementProposalORM)
        if project_id:
            stmt = stmt.where(RefinementProposalORM.project_id == project_id)
        if target_version:
            stmt = stmt.where(RefinementProposalORM.target_harness_version == target_version)
        if status:
            stmt = stmt.where(RefinementProposalORM.status == status.value)

        stmt = stmt.order_by(RefinementProposalORM.created_at.desc()).limit(limit)
        res = await self._session.execute(stmt)
        return [self._refinement_to_domain(r) for r in res.scalars().all()]

    async def update_refinement_status(
        self,
        refinement_id: str,
        new_status: RefinementStatus,
        eval_results: Optional[Dict[str, Any]] = None,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> Optional[RefinementProposal]:
        """Updates refinement proposal status and optional evaluation / metadata."""
        orm = await self._session.get(RefinementProposalORM, refinement_id)
        if not orm:
            return None

        orm.status = new_status.value
        if eval_results is not None:
            orm.evaluation_results_json = json.dumps(eval_results, default=str)
        if metadata_update:
            try:
                meta = json.loads(orm.metadata_json or "{}")
            except Exception:
                meta = {}
            meta.update(metadata_update)
            orm.metadata_json = json.dumps(meta, default=str)

        orm.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return self._refinement_to_domain(orm)

    async def delete_refinement(self, refinement_id: str) -> bool:
        """Deletes a refinement proposal record."""
        orm = await self._session.get(RefinementProposalORM, refinement_id)
        if not orm:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

