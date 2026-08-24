"""Google Gemini Live transport — Phase 4 (ban_ke_hoach_v1.md Section 8).

Separated from the HTTP generateContent adapter (adapter.py) — this transport
owns the Live API (WebSocket BidiGenerateContent) only.

Conceptually:
    GoogleGeminiProviderAdapter  →  generateContent (HTTP)
    GoogleGeminiLiveProvider     →  Live API (WebSocket, ephemeral token)

The server (WindAgent API) never proxies the Live session — it only mints
ephemeral tokens via token_service.py and validates LIVE_DIRECTOR capability.
The WebSocket itself lives in desktop TypeScript (LiveDirectorClient).

This module defines the Python-side Live session wiring used by tools/tests
and by any future server-side session validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from windagent_providers.google.live.capability import (
    LIVE_DIRECTOR_MODEL_ID,
    LIVE_DIRECTOR_REQUIRED_CAPS,
    canonical_live_model_id,
    is_live_model,
)
from windagent_providers.google.live.contracts import BootstrapResponse
from windagent_providers.google.live.token_service import EphemeralToken, EphemeralTokenService
from windagent_providers.google.live.session import LiveSessionConfig


LIVE_WEBSOCKET_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService/BidiGenerateContent"
)


@dataclass(frozen=True)
class LiveSetupMessage:
    """First BidiGenerateContent setup message sent over the Live socket.

    Mirrors the SDK's setup payload — model + generationConfig + systemInstruction
    + tools (Director constrained manifest).
    """

    model: str
    system_instruction: Optional[str] = None
    generation_config: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"setup": {"model": self.model}}
        if self.system_instruction:
            payload["setup"]["systemInstruction"] = {"parts": [{"text": self.system_instruction}]}
        if self.generation_config:
            payload["setup"]["generationConfig"] = self.generation_config
        if self.tools is not None:
            payload["setup"]["tools"] = self.tools
        return payload


class GoogleGeminiLiveProvider:
    """Live API transport for Gemini Live Director.

    No HTTP generateContent calls — only WebSocket Bidi session helpers.
    Auth is via ephemeral token (header, never query string) — see token_service.py.
    """

    provider_name = "google"
    live_model_id = LIVE_DIRECTOR_MODEL_ID
    websocket_url = LIVE_WEBSOCKET_URL

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model_id: str = LIVE_DIRECTOR_MODEL_ID,
    ) -> None:
        self.api_key = api_key
        self.model_id = canonical_live_model_id(model_id)
        self._token_service = EphemeralTokenService(
            provider_id=self.provider_name,
            model_id=self.model_id,
        )

    # ─── Capability ──────────────────────────────────────────────────────────

    def has_live_capability(self) -> bool:
        return is_live_model(self.model_id)

    def required_capabilities(self) -> frozenset[str]:
        return LIVE_DIRECTOR_REQUIRED_CAPS

    # ─── Token minting (server-side) ───────────────────────────────────────

    def mint_ephemeral_token(
        self,
        *,
        execution_plan_hash: str,
        session_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> EphemeralToken:
        return self._token_service.mint(
            execution_plan_hash=execution_plan_hash,
            session_id=session_id,
            ttl_seconds=ttl_seconds,
        )

    def build_session_config(
        self,
        *,
        session_id: str,
        execution_plan_hash: str,
        ephemeral_token: str,
        expires_at: datetime,
    ) -> LiveSessionConfig:
        return LiveSessionConfig(
            session_id=session_id,
            provider_id=self.provider_name,
            model_id=self.model_id,
            ephemeral_token=ephemeral_token,
            execution_plan_hash=execution_plan_hash,
            expires_at=expires_at,
        )

    # ─── WebSocket helpers (used by desktop client or tests) ────────────────

    def build_websocket_url(self) -> str:
        return self.websocket_url

    def build_setup_message(
        self,
        *,
        system_instruction: str,
        director_tools: Optional[List[Dict[str, Any]]] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> LiveSetupMessage:
        return LiveSetupMessage(
            model=f"models/{self.model_id}",
            system_instruction=system_instruction,
            generation_config=generation_config,
            tools=director_tools,
        )

    def build_bootstrap_response(
        self,
        *,
        session_id: str,
        execution_plan_hash: str,
        token: EphemeralToken,
        display_name: str = "Gemini 3 Flash Live",
    ) -> BootstrapResponse:
        return BootstrapResponse(
            session_id=session_id,
            provider_id=self.provider_name,
            model_id=self.model_id,
            token=token.token,
            expires_at=token.expires_at,
            execution_plan_hash=execution_plan_hash,
            display_name=display_name,
        )


__all__ = [
    "GoogleGeminiLiveProvider",
    "LiveSetupMessage",
    "LIVE_WEBSOCKET_URL",
]
