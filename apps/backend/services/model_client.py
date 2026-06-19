"""Phase 4 — Model client interface + Ollama + Mock implementations.

The ModelClient is the abstraction the PlannerService talks to. Two
implementations ship in MVP:

  - OllamaModelClient: real client, hits the OpenAI-compatible endpoint
    exposed by Ollama at http://localhost:11434/v1/chat/completions.
  - MockModelClient: deterministic fake used in tests and offline dev.

Both raise `ModelOfflineError` when the model is unreachable and
`ModelResponseError` when the model returns something the planner
cannot use (HTTP non-2xx, malformed envelope, etc.).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import httpx


log = logging.getLogger(__name__)


# ---------- Exceptions ----------

class ModelOfflineError(Exception):
    """Raised when the model provider cannot be reached."""


class ModelResponseError(Exception):
    """Raised when the provider is online but returns unusable output."""


# ---------- Data classes ----------

@dataclass(frozen=True)
class ChatMessage:
    role: str   # "system" | "user" | "assistant"
    content: str


# ---------- Protocol ----------

@runtime_checkable
class ModelClient(Protocol):
    """Minimal chat interface the PlannerService depends on."""

    name: str
    model: str

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        stream: bool = False,
        timeout: Optional[float] = None,
    ) -> str:
        """Send a chat completion request, return the assistant text."""
        ...

    async def health(self) -> Dict[str, Any]:
        """Return a small JSON dict describing provider status.

        Shape (per docs/api_contract.md /models/health):
          { "provider": str, "online": bool, "model": str,
            "latency_ms": Optional[int], "error": Optional[str] }
        """
        ...


# ---------- Ollama client ----------

class OllamaModelClient:
    """OpenAI-compatible client targeting Ollama's /v1/chat/completions.

    Default endpoint: http://localhost:11434/v1/chat/completions
    Default model:    qwen3:4b-q4 (per docs/models/README.md).
    """

    DEFAULT_BASE_URL = "http://localhost:11434/v1"
    DEFAULT_MODEL = "qwen3:4b-q4"
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.name = "ollama"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        stream: bool = False,
        timeout: Optional[float] = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],
            "stream": stream,
            # Ollama's OpenAI-compat layer respects response_format
            # when the underlying model supports it. We ask for JSON
            # to nudge Qwen into a parseable answer.
            "response_format": {"type": "json_object"},
        }
        try:
            resp = await self._http.post(
                url, json=payload, timeout=timeout or self.timeout
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise ModelOfflineError(f"ollama unreachable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ModelResponseError(f"http error: {exc}") from exc

        if resp.status_code != 200:
            raise ModelResponseError(
                f"ollama returned {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise ModelResponseError(
                f"unexpected ollama envelope: {exc}"
            ) from exc

    async def health(self) -> Dict[str, Any]:
        """Probe Ollama. Uses /v1/models which is cheaper than /chat."""
        start = time.perf_counter()
        try:
            resp = await self._http.get(
                f"{self.base_url}/models", timeout=2.0
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            return {
                "provider": self.name,
                "online": False,
                "model": self.model,
                "latency_ms": None,
                "error": str(exc),
            }
        except httpx.HTTPError as exc:
            return {
                "provider": self.name,
                "online": False,
                "model": self.model,
                "latency_ms": None,
                "error": str(exc),
            }

        latency_ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            return {
                "provider": self.name,
                "online": False,
                "model": self.model,
                "latency_ms": latency_ms,
                "error": f"http {resp.status_code}",
            }
        # Try to confirm the configured model is present.
        try:
            data = resp.json()
            ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
            if ids and self.model not in ids:
                return {
                    "provider": self.name,
                    "online": True,
                    "model": self.model,
                    "latency_ms": latency_ms,
                    "error": f"model not found (have: {ids})",
                }
        except Exception:  # noqa: BLE001
            pass
        return {
            "provider": self.name,
            "online": True,
            "model": self.model,
            "latency_ms": latency_ms,
            "error": None,
        }


# ---------- Mock client (tests + offline dev) ----------

class MockModelClient:
    """Deterministic fake ModelClient for tests.

    Configurable via `responses` (a list of canned outputs to return in
    order). Throws ModelOfflineError if `fail_with_offline=True`.

    Default canned responses cover the two demo phrases so most tests
    can use the mock without setting up responses explicitly.
    """

    name = "mock"

    DEFAULT_RESPONSES: Dict[str, str] = {
        # Notepad demo
        "Mở Notepad và gõ Hello": json.dumps({
            "steps": [
                {"name": "Open Notepad", "tool_name": "open_app",
                 "params": {"app": "notepad"}},
                {"name": "Type text", "tool_name": "type_text",
                 "params": {"text": "Hello", "method": "paste"}},
            ]
        }),
        "Mở trang google.com trên Edge": json.dumps({
            "steps": [
                {"name": "Open Edge", "tool_name": "open_app",
                 "params": {"app": "edge"}},
                {"name": "Navigate to URL", "tool_name": "open_url",
                 "params": {"url": "https://google.com"}},
            ]
        }),
    }

    def __init__(
        self,
        *,
        model: str = "mock:qwen3:4b-q4",
        responses: Optional[List[str]] = None,
        fail_with_offline: bool = False,
        fail_with_response_error: bool = False,
        latency_ms: int = 50,
    ) -> None:
        self.model = model
        self._responses = list(responses) if responses is not None else []
        self._call_count = 0
        self.fail_with_offline = fail_with_offline
        self.fail_with_response_error = fail_with_response_error
        self.latency_ms = latency_ms
        self.calls: List[List[ChatMessage]] = []

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        stream: bool = False,
        timeout: Optional[float] = None,
    ) -> str:
        self.calls.append(list(messages))
        # Simulate network latency.
        await asyncio.sleep(self.latency_ms / 1000.0)

        if self.fail_with_offline:
            raise ModelOfflineError("mock offline")

        if self.fail_with_response_error:
            raise ModelResponseError("mock response error")

        # If explicit responses are set, use them.
        if self._responses:
            idx = min(self._call_count, len(self._responses) - 1)
            self._call_count += 1
            return self._responses[idx]

        # Otherwise, look up by the LAST user message.
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        if last_user in self.DEFAULT_RESPONSES:
            return self.DEFAULT_RESPONSES[last_user]

        # Fallback to "no steps" so the planner falls back to its own
        # rule-based parser.
        return json.dumps({"steps": []})

    async def health(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "online": not self.fail_with_offline,
            "model": self.model,
            "latency_ms": self.latency_ms if not self.fail_with_offline else None,
            "error": "mock offline" if self.fail_with_offline else None,
        }