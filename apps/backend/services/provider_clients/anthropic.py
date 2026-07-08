"""Anthropic Claude API provider client implementation."""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional
import httpx

from services.provider_clients.base import ProviderOfflineError, ProviderResponseError

log = logging.getLogger(__name__)


class AnthropicClient:
    """Client for Anthropic Claude API."""

    def __init__(
        self,
        provider_id: str,
        base_url: str = "https://api.anthropic.com",
        api_key_env: Optional[str] = "ANTHROPIC_API_KEY",
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

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        api_key = self._get_api_key()
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    async def list_models(self) -> List[Dict[str, Any]]:
        """List Anthropic models, falling back to seeds if API is offline/empty."""
        fallback_models = [
            {
                "model_id": "claude-3-5-sonnet-20241022",
                "display_name": "Claude 3.5 Sonnet",
                "context_window": 200000,
                "capabilities": ["chat", "coding", "reasoning", "vision"],
                "raw": {}
            },
            {
                "model_id": "claude-3-5-haiku-20241022",
                "display_name": "Claude 3.5 Haiku",
                "context_window": 200000,
                "capabilities": ["chat", "coding", "fast"],
                "raw": {}
            },
            {
                "model_id": "claude-3-opus-20240229",
                "display_name": "Claude 3 Opus",
                "context_window": 200000,
                "capabilities": ["chat", "reasoning"],
                "raw": {}
            }
        ]

        if not self.has_api_key():
            log.warning("Missing API key for Anthropic, using default seed models")
            return fallback_models

        url = f"{self.base_url}/v1/models"
        try:
            resp = await self._http.get(url, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                raw_models = data.get("data", [])
                result = []
                for m in raw_models:
                    m_id = m.get("id")
                    if not m_id:
                        continue
                    
                    name_lower = m_id.lower()
                    caps = ["chat"]
                    if "sonnet" in name_lower or "opus" in name_lower:
                        caps.append("reasoning")
                    if "haiku" in name_lower or "fast" in name_lower:
                        caps.append("fast")
                    if "claude-3" in name_lower:
                        caps.append("vision")
                    
                    result.append({
                        "model_id": m_id,
                        "display_name": m.get("display_name", m_id),
                        "context_window": 200000,
                        "capabilities": caps,
                        "raw": m
                    })
                return result if result else fallback_models
        except Exception as exc:
            log.warning("Failed to fetch Anthropic models via API: %s. Using fallbacks.", exc)
            
        return fallback_models

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
    ) -> str:
        """Execute chat content generation via Anthropic Messages API."""
        if not self.has_api_key():
            raise ProviderResponseError("API key missing for Anthropic Claude")

        url = f"{self.base_url}/v1/messages"

        # Map system message
        system_instruction = None
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = content
            else:
                anthropic_messages.append({
                    "role": role if role in ("user", "assistant") else "user",
                    "content": content
                })

        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
        }
        if system_instruction:
            payload["system"] = system_instruction

        try:
            resp = await self._http.post(url, json=payload, headers=self._get_headers())
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise ProviderOfflineError(f"Anthropic API unreachable: {exc}") from exc

        if resp.status_code == 429:
            raise ProviderResponseError("Anthropic API Rate limit exceeded (HTTP 429)")

        if resp.status_code != 200:
            raise ProviderResponseError(
                f"Anthropic API returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            return data["content"][0]["text"]
        except Exception as exc:
            raise ProviderResponseError(f"Failed to parse Anthropic message envelope: {exc}") from exc

    async def get_quota(self) -> Dict[str, Any]:
        """Anthropic basic quota placeholder."""
        return {
            "rpm_limit": None,
            "rpd_limit": None,
            "tpm_limit": None,
            "remaining_requests_today": None,
            "remaining_tokens_today": None,
            "remaining_credit": None,
            "reset_at": None,
        }
