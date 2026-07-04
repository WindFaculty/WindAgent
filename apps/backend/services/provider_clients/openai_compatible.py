"""OpenAI-compatible model provider client implementation."""
from __future__ import annotations

import os
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from services.provider_clients.base import ProviderOfflineError, ProviderResponseError

log = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """Client for any OpenAI-compatible API gateway (OpenRouter, NIM, ZenMux, Nara, etc.)."""

    def __init__(
        self,
        provider_id: str,
        base_url: str,
        api_key_env: Optional[str] = None,
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

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        api_key = self.api_key or (os.environ.get(self.api_key_env, "") if self.api_key_env else "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def list_models(self) -> List[Dict[str, Any]]:
        """List models using standard GET /models endpoint."""
        if not self.has_api_key():
            # If no API key, return empty list gracefully (do not crash)
            log.warning("Missing API key for provider %s, cannot fetch models", self.provider_id)
            return []

        url = f"{self.base_url}/models"
        try:
            resp = await self._http.get(url, headers=self._get_headers())
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise ProviderOfflineError(f"Provider {self.provider_id} unreachable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(f"HTTP error on list_models: {exc}") from exc

        if resp.status_code != 200:
            raise ProviderResponseError(
                f"Provider {self.provider_id} returned HTTP {resp.status_code} on list_models: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            raw_models = data.get("data", [])
            result = []
            for m in raw_models:
                m_id = m.get("id")
                if not m_id:
                    continue
                
                # Deduce capabilities based on model name
                name_lower = m_id.lower()
                caps = ["chat"]
                if "coder" in name_lower or "code" in name_lower:
                    caps.append("coding")
                if "r1" in name_lower or "reason" in name_lower or "think" in name_lower:
                    caps.append("reasoning")
                if "vl" in name_lower or "vision" in name_lower:
                    caps.append("vision")
                
                result.append({
                    "model_id": m_id,
                    "display_name": m.get("name", m_id),
                    "context_window": m.get("context_length", m.get("context_window", None)),
                    "capabilities": caps,
                    "raw": m
                })
            return result
        except Exception as exc:
            raise ProviderResponseError(f"Failed to parse models envelope: {exc}") from exc

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
    ) -> str:
        """Execute chat completion request using POST /chat/completions."""
        if not self.has_api_key():
            raise ProviderResponseError(f"API key missing for provider {self.provider_id}")

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = self._get_headers()
        try:
            resp = await self._http.post(url, json=payload, headers=headers)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise ProviderOfflineError(f"Provider {self.provider_id} unreachable: {exc}") from exc

        if resp.status_code == 429:
            # Handle rate limits
            retry_after = resp.headers.get("Retry-After")
            err_msg = f"Rate limit exceeded (HTTP 429) for {self.provider_id}"
            if retry_after:
                err_msg += f". Retry after: {retry_after}s"
            raise ProviderResponseError(err_msg)

        if resp.status_code != 200:
            raise ProviderResponseError(
                f"Provider {self.provider_id} returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderResponseError(f"Failed to parse completion envelope: {exc}") from exc

    async def get_quota(self) -> Dict[str, Any]:
        """Fetch basic quota/usage mock/header snapshot."""
        # By default, OpenAI-compatible APIs don't have a single unified quota API,
        # but we return empty placeholder that can be filled by headers or manual snapshots.
        return {
            "rpm_limit": None,
            "rpd_limit": None,
            "tpm_limit": None,
            "remaining_requests_today": None,
            "remaining_tokens_today": None,
            "remaining_credit": None,
            "reset_at": None,
        }
