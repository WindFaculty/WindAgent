from __future__ import annotations

from pathlib import Path

import pytest

from windagent_core.contracts.tools import ToolExecutionContext, ToolInvocation
from windagent_core.domain.types import SessionId, ToolCallId
from windagent_tools.browser import (
    AgentBrowserClient,
    AgentBrowserCommandResult,
    AgentBrowserConfig,
    AgentBrowserPolicyError,
    OpenURLTool,
    validate_navigation_url,
)


class FakeProcess:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str]] = []

    async def run(self, argv, *, timeout_seconds, env):
        command = tuple(argv)
        self.calls.append(command)
        self.environments.append(dict(env))
        if "read" in command:
            stdout = "Public fixture post about WindAgent browser research."
        elif command[-2:] == ("get", "title"):
            stdout = "Fixture social post"
        elif command[-2:] == ("get", "url"):
            stdout = "https://www.youtube.com/watch?v=fixture"
        else:
            stdout = "OK"
        return AgentBrowserCommandResult(
            argv=command,
            returncode=0,
            stdout=stdout,
            stderr="",
        )


@pytest.mark.asyncio
async def test_open_url_uses_agent_browser_and_returns_hashed_content(tmp_path: Path):
    process = FakeProcess()

    def client_factory(config: AgentBrowserConfig) -> AgentBrowserClient:
        return AgentBrowserClient(config, process=process)

    tool = OpenURLTool(client_factory=client_factory)
    invocation = ToolInvocation(
        id=ToolCallId.generate(),
        tool_name="open_url",
        params={
            "url": "https://www.youtube.com/watch?v=fixture",
            "platform": "youtube",
            "session": "test-youtube",
            "screenshot_path": "artifacts/social/test.png",
        },
    )
    context = ToolExecutionContext(
        workspace_root=str(tmp_path),
        session_id=SessionId.generate(),
        env_vars={
            "AGENT_BROWSER_BIN": "agent-browser",
            "WINDAGENT_BROWSER_CONTAINMENT": "native",
            "GOOGLE_API_KEY": "must-not-reach-browser",
        },
        user_approved=True,
    )

    result = await tool.execute(invocation, context)

    assert result.success is True
    assert result.data["browser_backend"] == "vercel-labs/agent-browser"
    assert result.data["platform"] == "youtube"
    assert result.data["content_chars"] > 0
    assert len(result.data["content_sha256"]) == 64
    assert result.data["screenshot_path"] == str(
        tmp_path / "artifacts" / "social" / "test.png"
    )
    flattened = [item for call in process.calls for item in call]
    assert "--allowed-domains" in flattened
    assert "youtube.com,*.youtube.com,youtu.be" in flattened
    assert any(call[-1] == "close" for call in process.calls)
    assert all("GOOGLE_API_KEY" not in item for item in process.environments)


def test_validate_navigation_url_rejects_private_network_by_default():
    with pytest.raises(AgentBrowserPolicyError):
        validate_navigation_url(
            "http://127.0.0.1:8000/fixture",
            allowed_domains=("127.0.0.1",),
            allow_private_network=False,
        )


def test_native_containment_rejects_authenticated_profile_combination():
    with pytest.raises(AgentBrowserPolicyError):
        AgentBrowserConfig(
            session="test",
            profile="Default",
            containment_mode="native",
            allowed_domains=("youtube.com",),
        )
