"""Base abstract provider client and common exceptions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ProviderOfflineError(Exception):
    """Raised when the provider endpoint cannot be reached."""
    pass


class ProviderResponseError(Exception):
    """Raised when the provider returns an error (4xx, 5xx, or invalid envelope)."""
    pass


class BaseProviderClient(Protocol):
    """Protocol defining interface for model provider API integration."""

    provider_id: str
    base_url: str
    api_key_env: Optional[str]

    def has_api_key(self) -> bool:
        """Returns True if the required API key env var is set and not empty."""
        ...

    async def list_models(self) -> List[Dict[str, Any]]:
        """List models available on this provider.

        Each dict should contain keys:
          - model_id: str (ID used in API requests)
          - display_name: str
          - context_window: Optional[int]
          - capabilities: List[str]
          - raw: Any (original provider response metadata)
        """
        ...

    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 1.0,
    ) -> str:
        """Execute chat completion request and return the string content."""
        ...

    async def get_quota(self) -> Dict[str, Any]:
        """Fetch current quota or usage state if supported by provider API.

        Should return a dictionary containing keys like:
          - rpm_limit, rpd_limit, tpm_limit
          - remaining_requests_today, remaining_tokens_today
          - remaining_credit, reset_at
        """
        ...
