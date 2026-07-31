from __future__ import annotations

import json
from pathlib import Path

import pytest

from windagent_core.contracts.tools import ToolResult
from windagent_workflows.social_research import (
    ModelRoute,
    SocialResearchConfig,
    SocialResearchWorkflow,
    SocialSourceSpec,
)


class FakeBrowserTool:
    async def execute(self, invocation, ctx):
        url = invocation.params["url"]
        platform = invocation.params["platform"]
        content = (
            f"Visible {platform} post discussing WindAgent. Views: 1200. URL: {url}"
        )
        return ToolResult(
            call_id=invocation.id,
            success=True,
            data={
                "url": url,
                "final_url": url,
                "title": f"{platform.title()} fixture",
                "content": content,
                "content_sha256": "a" * 64,
                "content_chars": len(content),
                "platform": platform,
                "browser_backend": "vercel-labs/agent-browser",
                "screenshot_path": None,
            },
        )


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    async def discover_models(self, provider: str) -> list[str]:
        if provider == "ollama":
            return ["qwen3.5"]
        if provider == "google":
            return ["gemma-4-31b", "gemini-3.5-flash-lite"]
        return []

    async def generate(
        self,
        *,
        provider,
        model,
        system_instruction,
        prompt,
        max_output_tokens,
        temperature,
    ):
        self.calls.append((provider, model, prompt))
        if provider == "ollama":
            source_url = prompt.split("Source URL: ", 1)[1].splitlines()[0]
            platform = prompt.split("Platform: ", 1)[1].splitlines()[0]
            return json.dumps(
                {
                    "platform": platform,
                    "source_url": source_url,
                    "author": "fixture-author",
                    "published_at": None,
                    "title": "Fixture",
                    "text": "WindAgent browser research",
                    "metrics": {
                        "views": 1200,
                        "likes": None,
                        "comments": None,
                        "shares": None,
                    },
                    "topics": ["WindAgent", "browser automation"],
                    "claims": ["The source discusses WindAgent."],
                    "language": "en",
                }
            )
        if "gemma" in model:
            return "Gemma finds consistent discussion of browser automation."
        return "Gemini verifies the cross-platform evidence and its limitations."


class RetryingBrowserTool(FakeBrowserTool):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, invocation, ctx):
        self.calls += 1
        if self.calls == 1:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                data={"error_type": "AgentBrowserTimeoutError", "retryable": True},
                error="transient browser timeout",
            )
        return await super().execute(invocation, ctx)


class NonRetryingBrowserTool(FakeBrowserTool):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, invocation, ctx):
        self.calls += 1
        if "youtube" in invocation.params["url"]:
            return ToolResult(
                call_id=invocation.id,
                success=False,
                data={"error_type": "AgentBrowserPolicyError", "retryable": False},
                error="domain policy rejected URL",
            )
        return await super().execute(invocation, ctx)


class CapturingBrowserTool(FakeBrowserTool):
    def __init__(self) -> None:
        self.invocations = []

    async def execute(self, invocation, ctx):
        self.invocations.append(invocation)
        return await super().execute(invocation, ctx)


@pytest.mark.asyncio
async def test_social_research_runs_browser_extracts_and_writes_two_model_report(
    tmp_path: Path,
):
    gateway = FakeGateway()
    config = SocialResearchConfig(
        local_extractor=ModelRoute("ollama", "qwen3.5", "structured_extractor"),
        gemma_synthesizer=ModelRoute("google", "gemma-4-31b", "independent_synthesis"),
        gemini_synthesizer=ModelRoute(
            "google", "gemini-3.5-flash-lite", "verification_synthesis"
        ),
        output_dir="artifacts/social-test",
        save_screenshots=False,
    )
    workflow = SocialResearchWorkflow(
        model_gateway=gateway,
        browser_tool=FakeBrowserTool(),
        config=config,
    )

    result = await workflow.run(
        query="How are people discussing WindAgent?",
        sources=[
            SocialSourceSpec("https://www.youtube.com/watch?v=fixture"),
            SocialSourceSpec("https://www.tiktok.com/@fixture/video/1"),
            SocialSourceSpec("https://www.facebook.com/fixture/posts/1"),
        ],
        workspace_root=str(tmp_path),
    )

    assert result.status == "COMPLETE"
    assert result.successful_source_count == 3
    assert Path(result.markdown_path).is_file()
    assert Path(result.json_path).is_file()
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "Gemini verification synthesis" in markdown
    assert "Gemma independent synthesis" in markdown
    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
    assert len(payload["normalized_records"]) == 3
    assert {call[0] for call in gateway.calls} == {"ollama", "google"}
    assert sum(1 for call in gateway.calls if call[0] == "ollama") == 3
    assert sum(1 for call in gateway.calls if call[0] == "google") == 2


@pytest.mark.asyncio
async def test_workflow_retries_only_transient_browser_errors(tmp_path: Path):
    browser = RetryingBrowserTool()
    workflow = SocialResearchWorkflow(
        model_gateway=FakeGateway(),
        browser_tool=browser,
        config=SocialResearchConfig(
            output_dir="artifacts/social-retry",
            save_screenshots=False,
            browser_workflow_retry_attempts=2,
            browser_workflow_retry_backoff_seconds=0,
        ),
    )

    result = await workflow.run(
        query="Retry this source",
        sources=[SocialSourceSpec("https://www.youtube.com/watch?v=fixture")],
        workspace_root=str(tmp_path),
    )

    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
    assert browser.calls == 2
    assert payload["sources"][0]["browser_attempts"] == 2


@pytest.mark.asyncio
async def test_workflow_does_not_retry_nonretryable_browser_errors(tmp_path: Path):
    browser = NonRetryingBrowserTool()
    workflow = SocialResearchWorkflow(
        model_gateway=FakeGateway(),
        browser_tool=browser,
        config=SocialResearchConfig(
            output_dir="artifacts/social-nonretry",
            save_screenshots=False,
            browser_workflow_retry_attempts=3,
            browser_workflow_retry_backoff_seconds=0,
            allow_partial_sources=True,
        ),
    )

    result = await workflow.run(
        query="Do not retry policy failures",
        sources=[
            SocialSourceSpec("https://www.youtube.com/watch?v=fixture"),
            SocialSourceSpec("https://www.tiktok.com/@fixture/video/1"),
        ],
        workspace_root=str(tmp_path),
    )

    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
    assert browser.calls == 2
    assert payload["sources"][0]["browser_attempts"] == 1
    assert payload["sources"][0]["error"] == "domain policy rejected URL"


@pytest.mark.asyncio
async def test_workflow_forwards_explicit_authenticated_profile(tmp_path: Path):
    browser = CapturingBrowserTool()
    workflow = SocialResearchWorkflow(
        model_gateway=FakeGateway(),
        browser_tool=browser,
        config=SocialResearchConfig(
            output_dir="artifacts/social-authenticated",
            save_screenshots=False,
            browser_authenticated=True,
            browser_profile="Default",
        ),
    )

    await workflow.run(
        query="Use the approved browser profile",
        sources=[SocialSourceSpec("https://www.youtube.com/watch?v=fixture")],
        workspace_root=str(tmp_path),
    )

    assert browser.invocations[0].params["authenticated"] is True
    assert browser.invocations[0].params["profile"] == "Default"
