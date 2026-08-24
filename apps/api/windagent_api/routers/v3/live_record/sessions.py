"""Director session bootstrap router (/api/v3/live-record/sessions).

Phase 5 — Ephemeral token bootstrap (ban_ke_hoach_v1.md Section 10):

    Desktop --Start--> WindAgent API --Resolve LIVE_DIRECTOR--> issue ephemeral token --Desktop--> Google Live API

Token invariants (never persisted / never logged / never returned via GET /
one-session use / constrained to exact model/config) are enforced by the
application service and by providers.google.live.token_service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from windagent_api.routers.v3.live_record.dependencies import (
    get_live_record_service,
    require_idempotency_key,
)
from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)

router = APIRouter(prefix="/live-record/sessions", tags=["live-record"])


class BootstrapSessionRequest(BaseModel):
    episode_id: str = Field(min_length=1)
    execution_plan_id: str = Field(min_length=1)
    current_episode_revision_id: str | None = None


@router.post("/bootstrap", status_code=201)
async def bootstrap_session(
    body: BootstrapSessionRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Issue an ephemeral LIVE_DIRECTOR token for Desktop → Gemini direct.

    Request is POST only; token never appears on GET. One call = one session.
    The plan must be FROZEN and not stale (Principle A) or the call fails
    closed with 409/422.
    """
    return await service.bootstrap_director_session(
        episode_id=body.episode_id,
        execution_plan_id=body.execution_plan_id,
        current_episode_revision_id=body.current_episode_revision_id,
        idempotency_key=idempotency_key,
    )


@router.get("/{session_id}")
async def get_session(
    session_id: str = Path(min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Inspect a director session (never returns raw token)."""
    return await service.get_director_session(session_id)


@router.post("/{session_id}/token-refresh", status_code=201)
async def refresh_session_token(
    session_id: str = Path(min_length=1),
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Re-mint an ephemeral LIVE_DIRECTOR token for a reconnecting desktop.

    Section 24/§35: takes outlive the ~30-minute token TTL, so resumption must
    pair with refresh. The fresh token is bound to the same model + frozen
    plan_hash; it appears only in this response (POST-only, never logged).
    """
    return await service.refresh_director_token(
        session_id_raw=session_id,
        idempotency_key=idempotency_key,
    )
