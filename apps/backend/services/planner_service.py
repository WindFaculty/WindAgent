"""Phase 4 — PlannerService.

Owns the model interaction loop:

  1. Send user text to the model with a strict JSON-only system prompt.
  2. Parse + validate the response (tool_name whitelist, params shape).
  3. If invalid, send ONE repair prompt and try again.
  4. If still invalid OR model is offline, fall back to the rule-based
     parser for the two demo phrases.
  5. Surface enough metadata (model, latency, used_fallback, error) for
     the workflow event + /models/health endpoint.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from services.model_client import (
    ChatMessage,
    ModelClient,
    ModelOfflineError,
    ModelResponseError,
)
from services.tool_registry import list_tool_names

if TYPE_CHECKING:
    from services.workflow_service import IntentDraft


log = logging.getLogger(__name__)


# ---------- System prompt ----------

# Kept tight — Qwen3 4B Q4 is small and follows structured instructions
# better when the schema is spelled out verbatim.
SYSTEM_PROMPT = """You are a local desktop workflow planner.

Your job: convert the user's natural-language instruction into a SEQUENTIAL
workflow expressed as JSON.

Available tools (use ONLY these names):
- open_app        — open a Windows application. params: {"app": "notepad|calc|mspaint|edge|explorer"}
- open_url        — open a URL in a browser. params: {"url": "https://..."}
- type_text       — type text into the focused window. params: {"text": "...", "method": "type|paste"}
- hotkey          — press a keyboard shortcut. params: {"keys": ["ctrl", "s"]}
- press_key       — press a single key. params: {"key": "Enter"}
- click_xy        — click at screen coordinates. params: {"x": 100, "y": 200, "button": "left|right|middle"}
- scroll          — scroll the mouse wheel. params: {"clicks": 3, "direction": "up|down|left|right"}
- screenshot      — save a screenshot artifact. params: {"name": "optional_name"}
- wait            — sleep for N seconds. params: {"seconds": 1.0}

Output format — return ONLY this JSON shape, nothing else:
{
  "steps": [
    {
      "name": "human readable description",
      "tool_name": "one of the tools above",
      "params": { ... tool-specific params ... }
    }
  ]
}

Rules:
- Never invent tool names. If nothing fits, return {"steps": []}.
- Output ONLY the JSON object. No prose, no markdown fences, no commentary.
"""


REPAIR_PROMPT_TEMPLATE = """Your previous answer was not valid JSON or referenced an
unknown tool. Fix it.

Required schema (return ONLY this JSON, nothing else):
{schema}

Available tools: {tools}

User instruction was:
{user_text}

Your previous (bad) answer was:
{bad_answer}

Return corrected JSON only.
"""


# ---------- Result dataclass ----------

@dataclass
class PlanResult:
    steps: List[Dict[str, Any]] = field(default_factory=list)
    used_fallback: bool = False
    model: str = ""
    latency_ms: int = 0
    error: Optional[str] = None  # only set when no usable workflow was produced

    @property
    def is_empty(self) -> bool:
        return not self.steps


# ---------- Validation ----------

_TOOL_WHITELIST = set(list_tool_names())


def _try_parse(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON parse. Strips ```json fences if the model adds them."""
    if not raw:
        return None
    text = raw.strip()
    # Strip markdown code fences if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _validate(parsed: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Validate parsed JSON against the workflow schema.

    Returns the cleaned step dicts, or None if invalid.
    """
    if not isinstance(parsed, dict):
        return None
    steps_raw = parsed.get("steps")
    if not isinstance(steps_raw, list):
        return None
    cleaned: List[Dict[str, Any]] = []
    for step in steps_raw:
        if not isinstance(step, dict):
            return None
        name = step.get("name")
        tool = step.get("tool_name")
        params = step.get("params", {})
        if not isinstance(name, str) or not name.strip():
            return None
        if not isinstance(tool, str) or tool not in _TOOL_WHITELIST:
            return None
        if not isinstance(params, dict):
            return None
        cleaned.append({
            "name": name.strip(),
            "tool_name": tool,
            "params": dict(params),
        })
    return cleaned


# ---------- Service ----------

class PlannerService:
    """Orchestrates model.chat() → validate → repair → fallback."""

    def __init__(
        self,
        client: ModelClient,
        *,
        system_prompt: str = SYSTEM_PROMPT,
        enable_repair: bool = True,
        enable_fallback: bool = True,
    ) -> None:
        self._client = client
        self._system_prompt = system_prompt
        self._enable_repair = enable_repair
        self._enable_fallback = enable_fallback

    @property
    def client(self) -> ModelClient:
        return self._client

    async def plan(self, user_text: str) -> PlanResult:
        """Plan a workflow from a natural-language instruction.

        Never raises — always returns a PlanResult. The frontend decides
        whether to act on `is_empty` + `error`.
        """
        start = time.perf_counter()
        # Round 1: try the model.
        try:
            raw = await self._client.chat(
                [
                    ChatMessage(role="system", content=self._system_prompt),
                    ChatMessage(role="user", content=user_text),
                ]
            )
        except ModelOfflineError as exc:
            return self._fallback(user_text, start, error=str(exc))
        except ModelResponseError as exc:
            return self._fallback(user_text, start, error=str(exc))

        parsed = _try_parse(raw)
        cleaned = _validate(parsed) if parsed is not None else None
        if cleaned:
            return PlanResult(
                steps=cleaned,
                used_fallback=False,
                model=self._client.model,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )

        # Round 2: repair prompt (one retry).
        if self._enable_repair:
            try:
                repaired_raw = await self._client.chat([
                    ChatMessage(role="system", content=self._system_prompt),
                    ChatMessage(
                        role="user",
                        content=REPAIR_PROMPT_TEMPLATE.format(
                            schema=json.dumps({
                                "steps": [
                                    {"name": "...", "tool_name": "...", "params": {}}
                                ]
                            }, indent=2),
                            tools=", ".join(sorted(_TOOL_WHITELIST)),
                            user_text=user_text,
                            bad_answer=raw[:600],
                        ),
                    ),
                ])
            except (ModelOfflineError, ModelResponseError) as exc:
                return self._fallback(
                    user_text, start, error=f"repair failed: {exc}"
                )
            parsed = _try_parse(repaired_raw)
            cleaned = _validate(parsed) if parsed is not None else None
            if cleaned:
                return PlanResult(
                    steps=cleaned,
                    used_fallback=False,
                    model=self._client.model,
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

        # Model produced no usable steps (validation failed or empty
        # steps). Fall back to rule-based parser, which may rescue the
        # two demo phrases.
        return self._fallback(
            user_text, start,
            error="model output did not pass validation",
        )

    def _fallback(
        self,
        user_text: str,
        start: float,
        *,
        error: Optional[str] = None,
    ) -> PlanResult:
        """Run the rule-based parser. Always returns a PlanResult."""
        # Lazy import to avoid circular dependency with workflow_service.
        from services.workflow_service import parse_intent

        if not self._enable_fallback:
            return PlanResult(
                steps=[],
                used_fallback=False,
                model=self._client.model,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=error,
            )
        draft = parse_intent(user_text)
        return PlanResult(
            steps=list(draft.steps),
            used_fallback=True,
            model=self._client.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=error,
        )

    async def health(self) -> Dict[str, Any]:
        return await self._client.health()