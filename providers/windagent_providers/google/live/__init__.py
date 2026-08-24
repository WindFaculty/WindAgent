"""Google Gemini Live transport — Phase 4/5 (ban_ke_hoach_v1.md).

Desktop owns the WebSocket client (Desktop → Gemini direct via ephemeral token).
This package owns the server-side helpers: capability probe, token minting, and
session wiring. It does NOT proxy the Live session itself — it only issues
short-lived tokens constrained to the exact LIVE_DIRECTOR model/config.

See:
- windagent_core/contracts/providers/model_capabilities.py (LIVE_API gate)
- docs/live_record/tool_contract.md
- frontend/app/src/features/live-record/live-director/types.ts
"""

from windagent_providers.google.live.capability import (
    LIVE_DIRECTOR_MODEL_ID,
    LIVE_DIRECTOR_DISPLAY_NAME,
    is_live_model,
)
from windagent_providers.google.live.token_service import (
    EphemeralToken,
    EphemeralTokenService,
)
from windagent_providers.google.live.adapter import (
    GoogleGeminiLiveProvider,
    LIVE_WEBSOCKET_URL,
)

__all__ = [
    "LIVE_DIRECTOR_MODEL_ID",
    "LIVE_DIRECTOR_DISPLAY_NAME",
    "is_live_model",
    "EphemeralToken",
    "EphemeralTokenService",
    "GoogleGeminiLiveProvider",
    "LIVE_WEBSOCKET_URL",
]
