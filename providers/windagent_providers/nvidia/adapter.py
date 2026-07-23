"""
Thin NVIDIA NIM Vendor Adapter inheriting from OpenAICompatibleTransport.
Overrides NVIDIA-specific base URL and authorization.
"""

from __future__ import annotations
from typing import Dict, Optional
import httpx

from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport


class NvidiaNimAdapter(OpenAICompatibleTransport):
    """Thin Vendor Adapter for NVIDIA NIM endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(
            provider_name="nvidia",
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
