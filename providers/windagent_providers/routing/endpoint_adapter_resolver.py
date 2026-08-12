"""Runtime adapter construction for a selected provider endpoint."""

from __future__ import annotations

from typing import Any, Callable

from windagent_providers.base.errors import ProviderUnavailableFailure
from windagent_providers.google import GoogleGeminiProviderAdapter
from windagent_providers.openai_compatible.transport import OpenAICompatibleTransport
class EndpointAdapterResolver:
    """Build an adapter from a routed endpoint without persisting credentials.

    The current conversation execution path supports OpenAI-compatible,
    Ollama and native Google Gemini endpoints.  Other protocol modes fail as
    a normal provider attempt, allowing an exact-equivalent binding to
    continue while never switching the canonical model.
    """

    _SUPPORTED_PROTOCOLS = {"openai", "openai_compatible", "ollama", "google"}

    def __init__(self, decrypt_credentials: Callable[[str], str]) -> None:
        """Receive credential decryption from the composition boundary."""
        self._decrypt_credentials = decrypt_credentials

    def __call__(self, candidate: Any) -> Any:
        protocol_mode = str(getattr(candidate, "protocol_mode", "openai")).lower()
        if protocol_mode not in self._SUPPORTED_PROTOCOLS:
            raise ProviderUnavailableFailure(
                f"Unsupported conversation endpoint protocol: {protocol_mode}",
                provider_id=str(candidate.provider_name),
            )
        ciphertext = candidate.credential_ciphertext or ""
        if protocol_mode == "google":
            # Native Gemini generateContent adapter. Long structured story
            # generations (full screenplay JSON) routinely exceed the 30s
            # default read timeout, so the Google path uses the same 300s
            # ceiling as local Ollama.
            return GoogleGeminiProviderAdapter(
                api_key=self._decrypt_credentials(ciphertext) if ciphertext else "",
                base_url=str(candidate.base_url),
                timeout_seconds=300.0,
            )
        return OpenAICompatibleTransport(
            provider_name=str(candidate.provider_name),
            base_url=str(candidate.base_url),
            api_key=self._decrypt_credentials(ciphertext) if ciphertext else "",
            stream_generate=protocol_mode == "ollama",
            # Ollama default context (4096) truncates long structured prompts
            # (canon ledgers + output skeletons); the model then burns the
            # budget on reasoning and finishes with length-truncated JSON.
            default_payload={"think": False, "num_ctx": 16384} if protocol_mode == "ollama" else None,
            # Ollama json_schema mode drifts structural copies and can emit
            # empty streamed content; the story boundary enforces the schema
            # post-hoc regardless (STORY_SCHEMA_FAILURE, fail-closed).
            supports_response_format=protocol_mode != "ollama",
            # Local model reloads after idle: first-token latency can exceed
            # the 30s default read timeout.
            timeout_seconds=300.0 if protocol_mode == "ollama" else 30.0,
        )
