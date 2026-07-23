# tests/unit/providers/test_provider_v3_tool_translation.py
from __future__ import annotations

import pytest

from services.provider_v3_tool_translation import (
    normalize_tool_result,
    to_anthropic_tools,
    to_ollama_tools,
    to_openai_tools,
)

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]


def test_to_openai_tools_already_formatted():
    out = to_openai_tools(OPENAI_TOOLS)
    assert out == OPENAI_TOOLS


def test_to_anthropic_tools():
    out = to_anthropic_tools(OPENAI_TOOLS)
    assert len(out) == 1
    assert out[0]["name"] == "get_weather"
    assert out[0]["input_schema"]["type"] == "object"


def test_to_ollama_tools():
    out = to_ollama_tools(OPENAI_TOOLS)
    assert len(out) == 1
    assert out[0]["function"]["name"] == "get_weather"


def test_normalize_tool_result_anthropic():
    raw = [
        {"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"location": "Hanoi"}}
    ]
    normalized = normalize_tool_result(raw, provider="anthropic")
    assert normalized[0]["id"] == "tu_1"
    assert normalized[0]["function"]["name"] == "get_weather"
    assert normalized[0]["function"]["arguments"] == '{"location": "Hanoi"}'


def test_normalize_tool_result_ollama():
    raw = {"function": {"name": "get_weather", "arguments": {"location": "Hanoi"}}}
    normalized = normalize_tool_result(raw, provider="ollama")
    assert normalized[0]["function"]["name"] == "get_weather"
    assert isinstance(normalized[0]["function"]["arguments"], str)


def test_normalize_tool_result_openai_passes_through():
    raw = [{"id": "call_1", "type": "function", "function": {"name": "get_weather"}}]
    assert normalize_tool_result(raw, provider="openai") == raw


def test_normalize_tool_result_none():
    assert normalize_tool_result(None, provider="any") == []
