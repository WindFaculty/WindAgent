"""Google Gemini API / Google AI Studio provider client implementation."""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional
import httpx

from services.provider_clients.base import ProviderOfflineError, ProviderResponseError

log = logging.getLogger(__name__)


class GoogleGeminiClient:
    """Client for Google AI Studio / Gemini API."""

    def __init__(
        self,
        provider_id: str,
        base_url: str = "https://generativelanguage.googleapis.com",
        api_key_env: Optional[str] = "GOOGLE_AI_STUDIO_API_KEY",
        api_key: Optional[str] = None,
        timeout: float = 15.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.api_key = api_key
        self.timeout = timeout
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    def has_api_key(self) -> bool:
        if self.api_key:
            return True
        if not self.api_key_env:
            return False
        return bool(os.environ.get(self.api_key_env))

    def _get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if not self.api_key_env:
            return ""
        return os.environ.get(self.api_key_env, "")

    async def list_models(self) -> List[Dict[str, Any]]:
        """List Gemini models via v1beta/models."""
        if not self.has_api_key():
            log.warning("Missing API key for Google Gemini, cannot fetch models")
            return []

        key = self._get_api_key()
        # Use v1beta endpoint
        url = f"{self.base_url}/v1beta/models?key={key}"
        try:
            resp = await self._http.get(url)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise ProviderOfflineError(f"Gemini API unreachable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(f"HTTP error on list_models: {exc}") from exc

        if resp.status_code != 200:
            raise ProviderResponseError(
                f"Gemini API returned HTTP {resp.status_code} on list_models: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            raw_models = data.get("models", [])
            result = []
            for m in raw_models:
                name = m.get("name", "")
                if not name:
                    continue
                # The name field is usually: "models/gemini-2.5-flash"
                m_id = name.split("/")[-1]
                
                # Deduce capabilities
                caps = ["chat"]
                name_lower = name.lower()
                if "flash" in name_lower or "lite" in name_lower:
                    caps.append("fast")
                if "pro" in name_lower:
                    caps.append("reasoning")
                if "vision" in name_lower:
                    caps.append("vision")
                
                # Context limit
                input_limit = m.get("inputTokenLimit", 1048576)
                
                result.append({
                    "model_id": m_id,
                    "display_name": m.get("displayName", m_id),
                    "context_window": input_limit,
                    "capabilities": caps,
                    "raw": m
                })
            return result
        except Exception as exc:
            raise ProviderResponseError(f"Failed to parse Gemini models: {exc}") from exc

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
    ) -> str:
        """Execute chat content generation via generateContent."""
        if not self.has_api_key():
            raise ProviderResponseError("API key missing for Google Gemini")

        key = self._get_api_key()
        # Build URL. Model_id might need to be prefixed with models/ if it isn't
        full_model_id = model_id if model_id.startswith("models/") else f"models/{model_id}"
        url = f"{self.base_url}/v1beta/{full_model_id}:generateContent?key={key}"

        # Map messages to Gemini structure (contents)
        # Gemini roles: "user" | "model"
        gemini_contents = []
        for msg in messages:
            role = "user"
            if msg.get("role") == "assistant":
                role = "model"
            elif msg.get("role") == "system":
                # System instructions are placed in a different config in Gemini,
                # but for simplicity we will treat it as a user message or we can skip/prepend.
                # Let's map it as a systemInstruction structure if possible, but standard generateContent
                # payload can support user role for everything.
                role = "user"

            gemini_contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}]
            })

        payload: Dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": temperature,
            }
        }
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        try:
            resp = await self._http.post(url, json=payload, headers={"Content-Type": "application/json"})
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise ProviderOfflineError(f"Gemini API unreachable: {exc}") from exc

        if resp.status_code == 429:
            raise ProviderResponseError(f"Google Gemini Rate limit exceeded (HTTP 429)")

        if resp.status_code != 200:
            raise ProviderResponseError(
                f"Google Gemini API returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            raise ProviderResponseError(f"Failed to parse Gemini generation envelope: {exc}") from exc

    async def get_quota(self) -> Dict[str, Any]:
        """Gemini basic quota placeholder."""
        return {
            "rpm_limit": 15,  # Free tier default
            "rpd_limit": 1500,
            "tpm_limit": 1000000,
            "remaining_requests_today": None,
            "remaining_tokens_today": None,
            "remaining_credit": None,
            "reset_at": None,
        }
