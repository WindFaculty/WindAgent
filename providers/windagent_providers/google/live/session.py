"""Live Director session wiring — Phase 6 (ban_ke_hoach_v1.md Section 11).

Conceptually:

    GoogleGeminiProviderAdapter  ->  generateContent (HTTP)
    GoogleGeminiLiveProvider     ->  Live API (WebSocket, ephemeral token)

This module defines the *server* side of the Live session: what the
WindAgent API stores for a director session and how the desktop client
should be configured to connect directly to Google.

The actual WebSocket lives in desktop TypeScript
(frontend/app/src/features/live-record/live-director/) — not here.

See also windagent_core/domain/live_record/runtime.DirectorSessionRecord
which is the durable row for a director session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LiveSessionConfig:
    """Ephemeral credentials the desktop needs to open the Live socket."""

    session_id: str
    provider_id: str
    model_id: str
    ephemeral_token: str
    execution_plan_hash: str
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


# Keep in sync with frontend live-director/types.ts DEFAULT_RESUMPTION_POLICY
DEFAULT_RESUMPTION_POLICY = {
    "enabled": True,
    "max_attempts": 5,
    "backoff_ms": 1000,
    "retain_cue": True,
    "no_replay_of_success": True,
}

DEFAULT_FRAME_SAMPLER = {
    "mode": "event-driven",
    "fps": 1,
    "downscale": {"width": 1280, "height": 720},
    "format": "JPEG",
}
