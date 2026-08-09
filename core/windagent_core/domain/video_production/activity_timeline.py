"""
Production Activity Timeline Projection Engine (Stage F — UI38).

Converts technical domain events into a unified, human-readable production activity stream.
Ensures zero duplication, secret/path sanitization, correlation grouping, and idempotent replay convergence.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActivityCategory(str, Enum):
    SCRIPT = "SCRIPT"
    ASSET = "ASSET"
    BINDING = "BINDING"
    JOB = "JOB"
    PROPOSAL = "PROPOSAL"
    VALIDATION = "VALIDATION"
    SYSTEM = "SYSTEM"


class ActivityStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    WARNING = "WARNING"


class EntityLinkDTO(BaseModel):
    entity_id: str
    entity_type: str  # "SCENE" | "ASSET" | "REVISION" | "PROPOSAL" | "JOB"
    display_name: str


class ProductionActivity(BaseModel):
    activity_id: str
    project_id: str
    revision_id: str
    category: ActivityCategory
    actor: str
    title: str
    summary: str
    entity_links: List[EntityLinkDTO] = Field(default_factory=list)
    status: ActivityStatus = ActivityStatus.SUCCESS
    occurred_at: str
    source_event_ids: List[str] = Field(default_factory=list)
    correlation_id: str


def sanitize_text(text: str) -> str:
    """Sanitize secrets, prompt tokens, credentials, and absolute local file paths."""
    if not text:
        return text

    # Sanitize Windows and Unix absolute file paths
    text = re.sub(r"[A-Za-z]:\\[^\s:;\"']+", "[LOCAL_FILE_PATH]", text)
    text = re.sub(r"/(?:[a-zA-Z0-9._-]+/)+[a-zA-Z0-9._-]+", "[FILE_PATH]", text)

    # Sanitize API keys or secret tokens
    text = re.sub(r"(sk-[A-Za-z0-9_-]{10,})", "[REDACTED_API_KEY]", text)
    text = re.sub(r"(token_[A-Za-z0-9_-]{10,})", "[REDACTED_TOKEN]", text)

    return text


class ActivityProjector:
    """Projects domain event streams into idempotent, human-readable ProductionActivity projections."""

    _activity_store: Dict[str, ProductionActivity] = {}
    _event_processed_set: set[str] = set()

    @classmethod
    def clear_store(cls) -> None:
        cls._activity_store.clear()
        cls._event_processed_set.clear()

    @classmethod
    def project_event(
        cls,
        event_id: str,
        project_id: str,
        revision_id: str,
        event_type: str,
        actor: str,
        payload: Dict[str, Any],
        sequence: int = 1,
        correlation_id: Optional[str] = None,
        occurred_at: Optional[str] = None,
    ) -> Optional[ProductionActivity]:
        """Project a single domain event into a ProductionActivity record."""
        # Idempotency check: if event already processed, skip duplicate
        if event_id in cls._event_processed_set:
            # Find existing activity containing this event_id
            for act in cls._activity_store.values():
                if event_id in act.source_event_ids:
                    return act
            return None

        cls._event_processed_set.add(event_id)
        corr_id = correlation_id or f"corr_{event_id}"
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()

        category = ActivityCategory.SYSTEM
        title = f"Domain Event {event_type}"
        summary = f"Processed {event_type} event."
        entity_links: List[EntityLinkDTO] = []
        act_status = ActivityStatus.SUCCESS

        # Derive category, title, summary, entity_links from event_type and payload
        if "PROPOSAL" in event_type:
            category = ActivityCategory.PROPOSAL
            proposal_id = payload.get("proposal_id", "prop_unknown")
            prop_type = payload.get("proposal_type", "CHANGE")
            if "CREATED" in event_type or "SUBMITTED" in event_type:
                title = f"Proposal Created ({prop_type})"
                summary = f"Agent '{actor}' submitted proposal '{proposal_id}' for review."
            elif "APPROVED" in event_type:
                title = f"Proposal Approved ({proposal_id})"
                summary = f"Proposal '{proposal_id}' was approved by '{actor}'."
            elif "REJECTED" in event_type:
                title = f"Proposal Rejected ({proposal_id})"
                summary = f"Proposal '{proposal_id}' was rejected by '{actor}' with reason: {payload.get('reason', 'N/A')}"
                act_status = ActivityStatus.WARNING
            entity_links.append(EntityLinkDTO(entity_id=proposal_id, entity_type="PROPOSAL", display_name=f"Proposal {proposal_id}"))

        elif "SCREENPLAY" in event_type or "WORKSPACE_COMMAND_UPDATE_SCREENPLAY" in event_type:
            category = ActivityCategory.SCRIPT
            title = "Screenplay Updated"
            scene_id = payload.get("entity_id") or payload.get("scene_id", "sc_01")
            summary = f"Screenplay revision '{revision_id}' updated by '{actor}'."
            entity_links.append(EntityLinkDTO(entity_id=scene_id, entity_type="SCENE", display_name=f"Scene {scene_id}"))

        elif "ASSET" in event_type or "BINDING" in event_type:
            category = ActivityCategory.BINDING if "BINDING" in event_type else ActivityCategory.ASSET
            asset_id = payload.get("asset_id") or payload.get("entity_id", "ast_main")
            title = f"Asset Operation ({event_type})"
            summary = f"Asset '{asset_id}' modified by '{actor}'."
            entity_links.append(EntityLinkDTO(entity_id=asset_id, entity_type="ASSET", display_name=f"Asset {asset_id}"))

        elif "JOB" in event_type or "GENERATION" in event_type:
            category = ActivityCategory.JOB
            job_id = payload.get("job_id", "job_01")
            title = "Generation Job Event"
            summary = f"Job '{job_id}' status: {payload.get('status', 'RUNNING')}"
            entity_links.append(EntityLinkDTO(entity_id=job_id, entity_type="JOB", display_name=f"Job {job_id}"))

        # Sanitize summary and title
        title = sanitize_text(title)
        summary = sanitize_text(summary)

        # Check if existing activity with same correlation_id exists to aggregate technical events
        existing_activity: Optional[ProductionActivity] = None
        for act in cls._activity_store.values():
            if act.correlation_id == corr_id and act.category == category:
                existing_activity = act
                break

        if existing_activity:
            if event_id not in existing_activity.source_event_ids:
                existing_activity.source_event_ids.append(event_id)
            existing_activity.summary = sanitize_text(f"{existing_activity.summary} | {summary}")
            return existing_activity

        activity_id = f"act_{uuid.uuid4().hex[:10]}"
        activity = ProductionActivity(
            activity_id=activity_id,
            project_id=project_id,
            revision_id=revision_id,
            category=category,
            actor=actor,
            title=title,
            summary=summary,
            entity_links=entity_links,
            status=act_status,
            occurred_at=timestamp,
            source_event_ids=[event_id],
            correlation_id=corr_id,
        )

        cls._activity_store[activity_id] = activity
        return activity

    @classmethod
    def list_activities(
        cls,
        project_id: Optional[str] = None,
        category: Optional[ActivityCategory | str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ProductionActivity]:
        results = list(cls._activity_store.values())
        if project_id:
            results = [a for a in results if a.project_id == project_id]
        if category:
            cat_str = category.value if hasattr(category, "value") else str(category)
            results = [a for a in results if a.category.value == cat_str]

        # Sort descending by occurred_at
        results.sort(key=lambda x: x.occurred_at, reverse=True)
        return results[offset : offset + limit]

    @classmethod
    def replay_event_stream(cls, events: List[Dict[str, Any]]) -> List[ProductionActivity]:
        """Replay an event stream deterministically."""
        for evt in events:
            cls.project_event(
                event_id=evt["event_id"],
                project_id=evt.get("project_id", "proj_default"),
                revision_id=evt.get("revision_id", "rev_base"),
                event_type=evt.get("event_type", "UNKNOWN"),
                actor=evt.get("actor", "system"),
                payload=evt.get("payload", {}),
                sequence=evt.get("sequence", 1),
                correlation_id=evt.get("correlation_id"),
                occurred_at=evt.get("occurred_at"),
            )
        return cls.list_activities()
