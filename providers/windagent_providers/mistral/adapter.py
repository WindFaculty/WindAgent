"""
Thin Mistral Vendor Adapter inheriting from OpenAICompatibleTransport.
Overrides Mistral OpenAI-compatible base URL and headers.
"""

from __future__ import annotations
from typing import Optional
import httpx

from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport


class MistralProviderAdapter(OpenAICompatibleTransport):
    """Thin Vendor Adapter for Mistral AI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.mistral.ai/v1",
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(
            provider_name="mistral",
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
