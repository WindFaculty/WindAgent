"""Ollama adapter: the credentialless local OpenAI-compatible shim.

EXTRACT_LOGIC of the frozen ``providers/windagent_providers/ollama/adapter.py``
plus the resolver's Ollama-specific defaults: SSE-based generation with the
reasoning fallback, a large local-context default payload, response-format
suppression (the shim distorts json_schema output), and long local timeouts.
"""

from __future__ import annotations

from typing import Any

from .openai_compatible import OpenAICompatibleTransport

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_KEEP_ALIVE = "5m"
DEFAULT_NUM_CTX = 16384


class OllamaProviderAdapter(OpenAICompatibleTransport):
    """Local Ollama endpoint over its OpenAI-compatible shim."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        timeout_seconds: float = DEFAULT_TIMEOUT_S,
        num_ctx: int = DEFAULT_NUM_CTX,
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            provider_name="ollama",
            base_url=base_url,
            api_key=None,
            timeout_seconds=timeout_seconds,
            # Ollama's json_schema mode distorts structural copying and can
            # return empty content on streamed long outputs; the caller
            # validates structured output post-hoc instead.
            supports_response_format=False,
            stream_generate=True,
            default_payload={"think": False, "num_ctx": num_ctx, "keep_alive": keep_alive},
            **kwargs,
        )
