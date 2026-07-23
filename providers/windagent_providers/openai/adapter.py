"""
Thin OpenAI Vendor Adapter inheriting from OpenAICompatibleTransport.
Overrides OpenAI-specific base URL, authentication headers, and organization headers.
"""

from __future__ import annotations
from typing import Dict, Optional
import httpx

from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport


class OpenAIProviderAdapter(OpenAICompatibleTransport):
    """Thin Vendor Adapter for OpenAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        organization: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        extra_headers: Dict[str, str] = {}
        if organization:
            extra_headers["OpenAI-Organization"] = organization

        super().__init__(
            provider_name="openai",
            base_url=base_url,
            api_key=api_key,
            default_headers=extra_headers,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
