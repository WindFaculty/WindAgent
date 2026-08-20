"""Provider adapter creation for the provider-management seam (Phase 10).

``ProviderAdapterFactory`` builds a real provider adapter from endpoint probe
material. The factory is injectable: composition roots pass the credential
decryptor and may pass a controlled ``httpx.AsyncClient`` so tests can exercise
the real adapter code path against a local/mock HTTP transport without any real
external credential or network egress.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import httpx

from windagent_core.contracts.providers.provider_management import ProviderProbeMaterial
from windagent_providers.anthropic import AnthropicProviderAdapter
from windagent_providers.google import GoogleGeminiProviderAdapter
from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport


class ProviderAdapterFactory:
    """Build a provider adapter from probe material (injectable transport)."""

    _SUPPORTED_PROTOCOLS = {
        "openai",
        "openai_compatible",
        "anthropic",
        "ollama",
        "google",
        "gemini",
    }

    def __init__(
        self,
        decrypt_credentials: Callable[[str], str],
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Receive credential decryption and an optional controlled HTTP client.

        ``http_client`` is the test seam: when provided, every adapter built by
        this factory routes its network calls through that client (local/mock
        transport). Production composition passes ``None`` so adapters create
        their own real clients.
        """
        self._decrypt_credentials = decrypt_credentials
        self._http_client = http_client

    def create(self, material: ProviderProbeMaterial) -> Any:
        """Return a real adapter for the probe material.

        Raises ``ProviderUnavailableFailure`` for unsupported protocol modes so
        the probe fails closed instead of fabricating a result.
        """
        from windagent_providers.base.errors import ProviderUnavailableFailure

        protocol_mode = str(material.protocol_mode).lower()
        if protocol_mode not in self._SUPPORTED_PROTOCOLS:
            raise ProviderUnavailableFailure(
                f"Unsupported probe endpoint protocol: {protocol_mode}",
                provider_id=material.vendor_id,
            )
        ciphertext = material.credential_ciphertext or ""
        api_key = self._decrypt_credentials(ciphertext) if ciphertext else ""
        if protocol_mode == "anthropic":
            return AnthropicProviderAdapter(
                api_key=api_key,
                base_url=material.base_url,
                timeout_seconds=30.0,
                http_client=self._http_client,
            )
        if protocol_mode in {"google", "gemini"}:
            return GoogleGeminiProviderAdapter(
                api_key=api_key,
                base_url=material.base_url,
                timeout_seconds=30.0,
                http_client=self._http_client,
            )
        return OpenAICompatibleTransport(
            provider_name=material.provider_name,
            base_url=material.base_url,
            api_key=api_key,
            http_client=self._http_client,
            stream_generate=protocol_mode == "ollama",
            default_payload=(
                {"think": False, "num_ctx": 16384} if protocol_mode == "ollama" else None
            ),
            supports_response_format=protocol_mode != "ollama",
            timeout_seconds=300.0 if protocol_mode == "ollama" else 30.0,
        )


__all__ = ["ProviderAdapterFactory"]
