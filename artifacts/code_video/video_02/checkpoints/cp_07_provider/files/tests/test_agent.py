"""
Agentic Studio Test Suite.
Verifies Agent behavior with FakeLLMClient and Message immutability.
Target: 2 passed.
"""

import pytest
from src.agent import Agent, AgentConfig, FakeLLMClient, Message


def test_agent_runs_with_fake_llm() -> None:
    config = AgentConfig(
        name="Assistant",
        system_prompt="You are a helpful assistant.",
        model="gpt-4o-mini",
        temperature=0.7,
    )
    fake_llm = FakeLLMClient(default_response="Paris is the capital of France.")
    agent = Agent(config=config, llm_client=fake_llm)

    response = agent.run("What is the capital of France?")

    assert response == "Paris is the capital of France."
    assert len(fake_llm.call_history) == 1
    messages = fake_llm.call_history[0]
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].content == "You are a helpful assistant."
    assert messages[1].role == "user"
    assert messages[1].content == "What is the capital of France?"


def test_message_immutability_and_role_validation() -> None:
    msg = Message(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"

    with pytest.raises(Exception):
        msg.content = "New content"  # type: ignore

    with pytest.raises(ValueError, match="Invalid role"):
        Message(role="invalid_role", content="Hello")  # type: ignore
