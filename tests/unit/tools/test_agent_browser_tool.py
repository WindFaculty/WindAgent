from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from windagent_core.contracts.tools import ToolExecutionContext, ToolInvocation
from windagent_core.domain.types import SessionId, ToolCallId
from windagent_tools.browser import (
    AgentBrowserClient,
    AgentBrowserCommandResult,
    AgentBrowserConfig,
    AgentBrowserPolicyError,
    AgentBrowserTimeoutError,
    ClickXYTool,
    OpenURLTool,
    SubprocessAgentBrowserProcess,
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
        if command[-1:] == ("read",):
            stdout = "Public fixture post about WindAgent browser research."
        elif command[-1:] == ("snapshot",):
            stdout = '- button "Next" [ref=@e2]'
        elif "eval" in command and "transcript" in command[-1]:
            stdout = '["First transcript segment", "Second transcript segment"]'
        elif "eval" in command:
            stdout = '[{"text":"Next","href":"https://www.youtube.com/next"}]'
        elif command[-2:] == ("cookies", "get"):
            stdout = '[{"name":"session"}]'
        elif command[-4:-1] == ("get", "attr", "href"):
            stdout = "https://www.youtube.com/next"
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
            parsed=(
                ["First transcript segment", "Second transcript segment"]
                if "eval" in command and "transcript" in command[-1]
                else (
                    [{"text": "Next", "href": "https://www.youtube.com/next"}]
                    if "eval" in command
                    else (
                        [{"name": "session"}]
                        if command[-2:] == ("cookies", "get")
                        else None
                    )
                )
            ),
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
            binary="agent-browser",
            session="test",
            authenticated=True,
            profile="/tmp/profile",
            allowed_domains=("example.com",),
            containment_mode="native",
        )


def test_chrome_profile_requires_explicit_authenticated_opt_in():
    with pytest.raises(AgentBrowserPolicyError, match="authenticated=true"):
        AgentBrowserConfig(binary="agent-browser", session="test", profile="Default")

    config = AgentBrowserConfig(
        binary="agent-browser",
        session="test",
        authenticated=True,
        profile="Default",
        containment_mode="preflight",
    )
    assert config.command_prefix()[3:5] == ["--profile", "Default"]


@pytest.mark.asyncio
async def test_authenticated_open_uses_default_chrome_profile_only_after_opt_in(
    tmp_path: Path,
):
    process = FakeProcess()
    captured_config: list[AgentBrowserConfig] = []

    def client_factory(config: AgentBrowserConfig) -> AgentBrowserClient:
        captured_config.append(config)
        return AgentBrowserClient(config, process=process)

    tool = OpenURLTool(client_factory=client_factory)
    result = await tool.execute(
        ToolInvocation(
            id=ToolCallId.generate(),
            tool_name="open_url",
            params={
                "url": "https://www.youtube.com/watch?v=fixture",
                "authenticated": True,
            },
        ),
        ToolExecutionContext(
            workspace_root=str(tmp_path),
            session_id=SessionId.generate(),
            user_approved=True,
        ),
    )

    assert result.success is True
    assert captured_config[0].authenticated is True
    assert captured_config[0].profile == "Default"
    assert result.data["authenticated"] is True


@pytest.mark.asyncio
async def test_open_url_can_return_snapshot_and_safe_session_health(tmp_path: Path):
    process = FakeProcess()
    tool = OpenURLTool(
        client_factory=lambda config: AgentBrowserClient(config, process=process)
    )
    invocation = ToolInvocation(
        id=ToolCallId.generate(),
        tool_name="open_url",
        params={
            "url": "https://www.youtube.com/watch?v=fixture",
            "include_snapshot": True,
            "include_session_health": True,
        },
    )
    context = ToolExecutionContext(
        workspace_root=str(tmp_path),
        session_id=SessionId.generate(),
        user_approved=True,
    )

    result = await tool.execute(invocation, context)

    assert result.success is True
    assert result.data["snapshot"] == '- button "Next" [ref=@e2]'
    assert result.data["session_health"]["cookie_count"] == 1
    assert sum(call[-1] == "close" for call in process.calls) == 1


@pytest.mark.asyncio
async def test_semantic_click_replaces_coordinate_click_in_primary_contract(
    tmp_path: Path,
):
    process = FakeProcess()
    tool = ClickXYTool(
        client_factory=lambda config: AgentBrowserClient(config, process=process)
    )
    invocation = ToolInvocation(
        id=ToolCallId.generate(),
        tool_name="click_xy",
        params={"target": "Next", "locator": "role", "session": "semantic"},
    )
    context = ToolExecutionContext(
        workspace_root=str(tmp_path),
        session_id=SessionId.generate(),
        user_approved=True,
    )

    result = await tool.execute(invocation, context)

    assert result.success is True
    assert result.data["clicked_target"] == "Next"
    assert process.calls[-1][-4:] == ("find", "role", "Next", "click")


@pytest.mark.asyncio
async def test_browser_primitives_support_semantic_wait_scroll_links_and_health():
    process = FakeProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(
            session="primitive-test",
            allowed_domains=("youtube.com", "*.youtube.com"),
            retry_backoff_seconds=0,
        ),
        process=process,
    )

    await client.wait_for("#ready")
    await client.wait_for("loaded", condition="text")
    await client.scroll("down", 500)
    await client.click_target("@e2")
    await client.click_target("Read more", locator="text")
    assert (
        await client.read_attribute("a.next", "href") == "https://www.youtube.com/next"
    )
    assert await client.list_links() == [
        {"text": "Next", "href": "https://www.youtube.com/next"}
    ]
    health = await client.session_health()

    assert health["has_cookies"] is True
    flattened = [item for call in process.calls for item in call]
    assert "scroll" in flattened
    assert "snapshot" not in flattened
    assert ("wait", "#ready") == process.calls[0][-2:]


@pytest.mark.asyncio
async def test_persistent_page_primitives_capture_after_ui_actions():
    process = FakeProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(
            session="desktop-ui-test",
            allowed_domains=("youtube.com", "*.youtube.com"),
            retry_backoff_seconds=0,
        ),
        process=process,
    )

    await client.set_viewport(1280, 800)
    await client.type_text("#search", "WindAgent")
    await client.go_back()
    await client.go_forward()
    await client.reload()
    capture = await client.capture_current_page()

    assert capture.title == "Fixture social post"
    assert capture.text.startswith("Public fixture post")
    assert ("set", "viewport", "1280", "800") == process.calls[0][-4:]
    assert ("type", "#search", "WindAgent") == process.calls[1][-3:]
    assert process.calls[-3][-2:] == ("get", "title")


@pytest.mark.asyncio
async def test_social_crawling_primitives_cover_pagination_scroll_transcript_network_and_har():
    process = FakeProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(session="crawl-test", retry_backoff_seconds=0),
        process=process,
    )

    paginated = await client.collect_paginated("@e2", max_pages=3)
    infinite = await client.collect_infinite_scroll(max_scrolls=3, settle_ms=1)
    transcript = await client.extract_video_transcript()
    network = await client.inspect_network(clear=True)
    await client.start_har()
    assert (
        await client.stop_har("artifacts/social/network.har")
        == "artifacts/social/network.har"
    )

    assert paginated == ["Public fixture post about WindAgent browser research."]
    assert infinite == ["Public fixture post about WindAgent browser research."]
    assert transcript == "First transcript segment\nSecond transcript segment"
    assert network == "OK"
    assert ("network", "har", "start") == process.calls[-2][-3:]
    assert process.calls[-1][-4:] == (
        "network",
        "har",
        "stop",
        "artifacts/social/network.har",
    )


@pytest.mark.asyncio
async def test_multiple_urls_reuse_one_session_then_close_once():
    process = FakeProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(
            session="shared-session",
            allowed_domains=("youtube.com", "*.youtube.com"),
            retry_backoff_seconds=0,
        ),
        process=process,
    )

    captures = await client.open_many_and_read(
        [
            "https://www.youtube.com/watch?v=first",
            "https://www.youtube.com/watch?v=second",
        ]
    )

    assert len(captures) == 2
    assert all(capture.text for capture in captures)
    assert sum(call[-1] == "close" for call in process.calls) == 1
    assert sum("open" in call for call in process.calls) == 2


class TimeoutThenSuccessProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__()
        self.open_attempts = 0

    async def run(self, argv, *, timeout_seconds, env):
        command = tuple(argv)
        if command[-2:] == ("open", "https://www.youtube.com/watch?v=fixture"):
            self.open_attempts += 1
            if self.open_attempts == 1:
                raise AgentBrowserTimeoutError("transient launch timeout")
        return await super().run(argv, timeout_seconds=timeout_seconds, env=env)


@pytest.mark.asyncio
async def test_retry_backoff_retries_only_transient_idempotent_operations():
    process = TimeoutThenSuccessProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(
            session="retry-test",
            allowed_domains=("youtube.com", "*.youtube.com"),
            retry_attempts=2,
            retry_backoff_seconds=0,
        ),
        process=process,
    )

    capture = await client.open_and_read(
        "https://www.youtube.com/watch?v=fixture", close_session=False
    )

    assert capture.text
    assert process.open_attempts == 2


class AlwaysTimeoutProcess:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def run(self, argv, *, timeout_seconds, env):
        self.calls.append(tuple(argv))
        raise AgentBrowserTimeoutError("timeout")


@pytest.mark.asyncio
async def test_non_idempotent_click_is_not_retried():
    process = AlwaysTimeoutProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(
            session="click-test", retry_attempts=3, retry_backoff_seconds=0
        ),
        process=process,
    )

    with pytest.raises(AgentBrowserTimeoutError):
        await client.click_target("@e2")

    assert len(process.calls) == 1


class BlockingProcess:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[tuple[str, ...]] = []

    async def run(self, argv, *, timeout_seconds, env):
        command = tuple(argv)
        self.calls.append(command)
        if command[-1] == "close":
            return AgentBrowserCommandResult(command, 0, "OK", "")
        self.started.set()
        await self.release.wait()
        return AgentBrowserCommandResult(command, 0, "OK", "")


@pytest.mark.asyncio
async def test_cancellation_closes_the_browser_session():
    process = BlockingProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(session="cancel-test", cleanup_timeout_seconds=1),
        process=process,
    )
    task = asyncio.create_task(
        client.open_and_read("https://www.example.com", close_session=True)
    )
    await process.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert any(call[-1] == "close" for call in process.calls)


class FakeChildProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.started = asyncio.Event()
        self.killed = False
        self._transport = FakeTransport()

    async def communicate(self):
        if self.killed:
            self.returncode = -9
            return b"", b""
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    def kill(self) -> None:
        self.killed = True

    async def wait(self):
        self.returncode = -9
        return self.returncode


class FakeTransport:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_subprocess_child_is_reaped_when_task_is_cancelled(monkeypatch):
    child = FakeChildProcess()

    async def create_process(*args, **kwargs):
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    process = SubprocessAgentBrowserProcess()
    task = asyncio.create_task(
        process.run(["agent-browser"], timeout_seconds=60, env=dict(os.environ))
    )
    await child.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert child.killed is True
    assert child._transport.closed is True


@pytest.mark.asyncio
async def test_benchmark_reports_latency_and_runner_memory():
    process = FakeProcess()
    client = AgentBrowserClient(
        AgentBrowserConfig(
            session="benchmark-test",
            allowed_domains=("youtube.com", "*.youtube.com"),
            retry_backoff_seconds=0,
        ),
        process=process,
    )

    benchmark = await client.benchmark_open_and_read(
        "https://www.youtube.com/watch?v=fixture"
    )

    assert benchmark.open_and_read_ms >= 0
    assert benchmark.runner_peak_memory_bytes > 0
    assert benchmark.content_chars > 0
