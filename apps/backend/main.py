"""
WindAgent Backend Compatibility Bootstrap Entrypoint (Phase 27 Evacuation).
Delegates all API routes and lifespans directly to windagent_api.main:app.
"""

from __future__ import annotations
import logging
from typing import Any, Dict
from fastapi import FastAPI

from windagent_api.main import app as v2_app

logger = logging.getLogger("windagent.backend.compatibility")
logger.info("Initializing legacy backend compatibility bootstrap delegating to V2 Canonical API.")

# Expose V2 app as backend app entrypoint
app = v2_app


class LegacyBackendCompatibilityInfo:
    """Metadata regarding legacy backend evacuation and deprecation timeline."""
    DEPRECATION_DEADLINE = "2026-12-31"
    CANONICAL_API_PACKAGE = "windagent_api"
    STATUS = "LEGACY_BACKEND_EVACUATED"


@app.get("/internal/legacy-status")
async def get_legacy_backend_status() -> Dict[str, Any]:
    return {
        "status": LegacyBackendCompatibilityInfo.STATUS,
        "canonical_package": LegacyBackendCompatibilityInfo.CANONICAL_API_PACKAGE,
        "deprecation_deadline": LegacyBackendCompatibilityInfo.DEPRECATION_DEADLINE,
        "evacuated": True,
    }
