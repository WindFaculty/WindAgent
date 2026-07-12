"""Phase 3 — Partial stream audit (ban_ke_hoach §6).

When a provider stream is interrupted before completion, the partial output
is saved for audit only. It must NOT enter the canonical chat transcript.
Only a complete, retried turn is shown to the user.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from db.database import Database
from db.models import PartialArtifactORM


async def save_partial_artifact(
    db: Database,
    *,
    content_text: str,
    attempt_id: Optional[int] = None,
    agent_session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    provider_binding_id: Optional[str] = None,
    error_class: Optional[str] = None,
) -> str:
    """Persist partial output as audit_only. Returns artifact id."""
    artifact_id = f"part_{uuid.uuid4().hex}"
    async with db.session() as s:
        s.add(PartialArtifactORM(
            id=artifact_id,
            attempt_id=attempt_id,
            agent_session_id=agent_session_id,
            turn_id=turn_id,
            content_text=content_text,
            provider_binding_id=provider_binding_id,
            error_class=error_class,
            visibility="audit_only",
            created_at=datetime.now(timezone.utc),
        ))
    return artifact_id
