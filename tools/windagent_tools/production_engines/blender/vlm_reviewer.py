"""VP3D Phase 22 - OpenRouter VLM reviewer port (Stage K §3 item 3, §7 risk).

Optional vision-model reviewer for the Phase 22 ``ContentReviewer``: the
deterministic metrics run first, this port runs after and merges a structured
outcome.  Everything is FAIL-CLOSED (Stage K test matrix: a reviewer/VLM
timeout must never become a PASS):

- no ``OPENROUTER_API_KEY``      -> {"error": ...}   -> VLM_REVIEW_TIMEOUT
- HTTP error / timeout / bad JSON -> {"timed_out": True} -> VLM_REVIEW_TIMEOUT
- model returns structured JSON  -> merged as a VLM finding with the model's
                                    confidence; low confidence -> REQUIRES_HUMAN

Risk pinning (§7): model id + prompt template hash are module constants and
every outcome records them, so a drifted model/version or prompt change is
visible in evidence instead of silently changing review behaviour.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

import httpx

MODEL_ID = "qwen/qwen3.7-flash"
BASE_URL = "https://openrouter.ai/api/v1"
ENV_API_KEY = "OPENROUTER_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 60.0

PROMPT_TEMPLATE = """You are a technical reviewer for 3D animation renders.
Review the media context below and return STRICT JSON only, no prose:
{"code": "short finding code", "severity": "BLOCKING|WARNING|INFO",
 "entity": "affected entity id", "confidence": 0.0-1.0,
 "evidence": {"note": "one sentence"}, "suggested_repair": "repair scope"}
If nothing is wrong, return {"code": "VLM_OK", "severity": "INFO",
 "confidence": 0.0, "evidence": {"note": "ok"}, "suggested_repair": ""}.
Media context:
__DIMENSION__

__CONTEXT__"""

PROMPT_HASH = hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()


class OpenRouterVlmReviewer:
    """Minimal OpenRouter chat-completions reviewer (no streaming).

    Injected ``http`` transport (httpx.Client-like) keeps tests offline;
    default is a real httpx.Client against OpenRouter.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = MODEL_ID,
        base_url: str = BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http: Optional[Any] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(ENV_API_KEY, "")
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self._http = http

    # ------------------------------------------------------------------
    def to_outcome(self, result: Dict[str, Any]) -> dict:
        """Shape the merged result exactly like ContentReviewer expects."""
        if result.get("error") or result.get("timed_out"):
            return {
                "timed_out": True,
                "dimension": str(result.get("dimension") or "all"),
                "error": str(result.get("error") or "timeout"),
            }
        return {
            "code": str(result.get("code") or "VLM_FINDING"),
            "severity": str(result.get("severity") or "WARNING"),
            "entity": str(result.get("entity") or "render"),
            "confidence": float(result.get("confidence") or 0.0),
            "evidence": dict(result.get("evidence") or {}),
            "suggested_repair": str(result.get("suggested_repair") or "human_review"),
        }

    def review(self, media_context: Dict[str, Any]) -> dict:
        """Call OpenRouter; NEVER raises.  Returns the outcome dict.

        Outcome records model + prompt hash (Stage K §7 pinning) in
        evidence when the model answers; failures carry the pin too.
        """
        pin = {"model": self.model, "prompt_hash": PROMPT_HASH}
        if not self.api_key:
            return self.to_outcome(
                {
                    "error": f"{ENV_API_KEY} not configured",
                    "dimension": media_context.get("dimension", "all"),
                }
            ) | {"evidence": {**pin, "error": "no api key"}}

        dimension = media_context.get("dimension", "all")
        prompt = (
            PROMPT_TEMPLATE.replace("__DIMENSION__", dimension).replace(
                "__CONTEXT__",
                json.dumps(media_context, ensure_ascii=False)[:4000],
            )
        )
        try:
            client = self._http or httpx.Client(timeout=self.timeout_seconds)
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            result = json.loads(content)  # model must return STRICT JSON
            return self.to_outcome(result) | {
                "evidence": {
                    **dict(result.get("evidence") or {}),
                    **pin,
                    "api_model": str(payload.get("model") or self.model),
                }
            }
        except Exception as exc:  # noqa: BLE001 - fail closed on ANY failure
            return self.to_outcome(
                {"timed_out": True, "dimension": dimension, "error": str(exc)}
            ) | {"evidence": {**pin, "error": str(exc)}}


__all__ = [
    "MODEL_ID",
    "BASE_URL",
    "ENV_API_KEY",
    "DEFAULT_TIMEOUT_SECONDS",
    "PROMPT_TEMPLATE",
    "PROMPT_HASH",
    "OpenRouterVlmReviewer",
]
