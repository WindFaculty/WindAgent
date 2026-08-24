"""Live bootstrap contracts — Phase 5 (ban_ke_hoach_v1.md Section 10).

Request/response shapes for POST /api/v3/live-record/sessions/bootstrap.

The API resolves LIVE_DIRECTOR via Provider + Model Routing, checks that
Google provider is configured, has live capability, and that the execution
plan is FROZEN and not stale. Only then it mints an ephemeral token.

Token field:
- never persisted
- never logged
- never returned via GET
- one-session use
- constrained to exact model/config
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BootstrapRequest(BaseModel):
    """POST /api/v3/live-record/sessions/bootstrap"""

    model_config = ConfigDict(extra="forbid")

    episode_id: str = Field(min_length=1)
    execution_plan_id: str = Field(min_length=1)
    # Optional override: the episode's current revision for staleness check.
    # If omitted the service checks against the plan's own episode_revision_id
    # alone (i.e., no staleness — the plan is authoritative).
    current_episode_revision_id: Optional[str] = None


class BootstrapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    provider_id: str
    model_id: str  # e.g. gemini-3.1-flash-live-preview
    token: str
    expires_at: datetime
    execution_plan_hash: str
    # UI-facing display label (may differ from wire model_id)
    display_name: str = "Gemini 3 Flash Live"
