"""Runtime adapter construction for a selected provider endpoint."""

from __future__ import annotations

from typing import Any, Callable

from windagent_providers.base.errors import ProviderUnavailableFailure
from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport
class EndpointAdapterResolver:
    """Build an adapter from a routed endpoint without persisting credentials.

    The current conversation execution path supports OpenAI-compatible and
    Ollama endpoints.  Other protocol modes fail as a normal provider attempt,
    allowing an exact-equivalent binding to continue while never switching the
    canonical model.
    """

    _SUPPORTED_PROTOCOLS = {"openai", "openai_compatible", "ollama"}

    def __init__(self, decrypt_credentials: Callable[[str], str]) -> None:
        """Receive credential decryption from the composition boundary."""
        self._decrypt_credentials = decrypt_credentials

    def __call__(self, candidate: Any) -> OpenAICompatibleTransport:
        protocol_mode = str(getattr(candidate, "protocol_mode", "openai")).lower()
        if protocol_mode not in self._SUPPORTED_PROTOCOLS:
            raise ProviderUnavailableFailure(
                f"Unsupported conversation endpoint protocol: {protocol_mode}",
                provider_id=str(candidate.provider_name),
            )
        ciphertext = candidate.credential_ciphertext or ""
        return OpenAICompatibleTransport(
            provider_name=str(candidate.provider_name),
            base_url=str(candidate.base_url),
            api_key=self._decrypt_credentials(ciphertext) if ciphertext else "",
            stream_generate=protocol_mode == "ollama",
            default_payload={"think": False} if protocol_mode == "ollama" else None,
        )
