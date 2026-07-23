# apps/backend/services/provider_v3_tool_translation.py
"""Bidirectional tool call/schema translation for LegacyClientV3Adapter."""
from __future__ import annotations

import json
from typing import Any, Dict, List


def _openai_function(tool: Dict[str, Any]) -> Dict[str, Any]:
    if "function" in tool:
        return tool["function"]
    return tool


def to_openai_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize any incoming tool description to strict OpenAI format."""
    out = []
    for t in tools:
        fn = _openai_function(t)
        out.append(
            {
                "type": "function",
                "function": {
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get(
                        "parameters", {"type": "object", "properties": {}}
                    ),
                },
            }
        )
    return out


def to_anthropic_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OpenAI tool format -> Anthropic Messages API tool format."""
    result = []
    for t in to_openai_tools(tools):
        fn = t["function"]
        result.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            }
        )
    return result


def to_ollama_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OpenAI tool format -> Ollama /api/chat tool format."""
    return to_openai_tools(tools)


def normalize_tool_result(
    raw: Any, provider: str
) -> List[Dict[str, Any]]:
    """Convert a provider-specific tool response into OpenAI-style tool_calls."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if provider == "anthropic":
            if item.get("type") == "tool_use":
                normalized.append(
                    {
                        "id": item.get("id", f"call-{idx}"),
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": json.dumps(item.get("input", {})),
                        },
                    }
                )
        elif provider == "ollama":
            fn = item.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, dict):
                args = json.dumps(args)
            normalized.append(
                {
                    "id": fn.get("id", f"call-ollama-{idx}"),
                    "type": "function",
                    "function": {"name": fn.get("name", ""), "arguments": args},
                }
            )
        else:
            # OpenAI-compatible / already normalized
            normalized.append(item)
    return normalized
