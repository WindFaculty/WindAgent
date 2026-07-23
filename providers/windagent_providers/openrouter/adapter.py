"""
Thin OpenRouter Vendor Adapter inheriting from OpenAICompatibleTransport.
Overrides OpenRouter-specific base URL, headers (HTTP-Referer, X-Title), and auth.
"""

from __future__ import annotations
from typing import Optional
import httpx

from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport


class OpenRouterAdapter(OpenAICompatibleTransport):
    """Thin Vendor Adapter for OpenRouter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        site_url: str = "https://windagent.ai",
        site_name: str = "WindAgent",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        extra_headers = {
            "HTTP-Referer": site_url,
            "X-Title": site_name,
        }
        super().__init__(
            provider_name="openrouter",
            base_url=base_url,
            api_key=api_key,
            default_headers=extra_headers,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
