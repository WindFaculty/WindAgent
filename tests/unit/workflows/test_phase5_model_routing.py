from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest
import httpx

from windagent_core.contracts.providers import ProviderResponse
from windagent_core.contracts.tools import ToolResult
from windagent_providers.gateway_bridge import V3ModelGatewayBridge
from windagent_providers.google import GoogleGeminiProviderAdapter
from windagent_providers.ollama import OllamaProviderAdapter
from windagent_cli.social_research_composition import compose_social_research_workflow
from windagent_workflows.social_research import (
    SocialResearchConfig,
    SocialResearchError,
    SocialResearchWorkflow,
    SocialSourceSpec,
)


class FakeBrowserTool:
    async def execute(self, invocation, ctx):
        url = invocation.params["url"]
        platform = invocation.params["platform"]
        content = f"Rendered page content for {platform} at {url}. Metrics: 500 views. Secret query token: api_key=AIzaSySecretTokenInContent123"
        return ToolResult(
            call_id=invocation.id,
            success=True,
            data={
                "url": url,
                "final_url": f"{url}?auth_token=AIzaSyUrlSecret12345",
                "title": f"{platform.title()} Page with API_KEY=AIzaSyTitleSecret999",
                "content": content,
                "content_sha256": "b" * 64,
                "content_chars": len(content),
                "platform": platform,
                "browser_backend": "vercel-labs/agent-browser",
                "screenshot_path": None,
            },
        )


class ConfigurableGateway:
    def __init__(self, *, response_map: Optional[dict[str, str]] = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.available_models: set[str] = {
            "ollama/qwen3.5",
            "google/gemma-4-31b",
            "google/gemini-3.5-flash-lite",
        }
        self.response_map = response_map or {}

    async def discover_models(self, provider: str) -> list[Any]:
        class ModelInfo:
            def __init__(self, raw_id: str) -> None:
                self.raw_model_id = raw_id

        return [
            ModelInfo(m.split("/", 1)[1])
            for m in self.available_models
            if m.startswith(f"{provider}/")
        ]

    async def generate(
        self,
        *,
        provider: str,
        model: str,
        system_instruction: str,
        prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        key = f"{provider}/{model}"
        self.calls.append((provider, model, prompt))

        if key in self.response_map:
            return self.response_map[key]

        if provider == "ollama":
            source_url = prompt.split("Source URL: ", 1)[1].splitlines()[0]
            platform = prompt.split("Platform: ", 1)[1].splitlines()[0]
            return json.dumps(
                {
                    "platform": platform,
                    "source_url": source_url,
                    "author": "test-author",
                    "published_at": None,
                    "title": "Test Title",
                    "text": "Evidence content extracted",
                    "metrics": {"views": 500},
                    "topics": ["test"],
                    "claims": ["Claim 1"],
                    "language": "en",
                }
            )

        if "gemma" in model:
            return "Gemma independent synthesis: Discussion is positive at https://youtube.com/watch?v=12345678901."

        return "Gemini verification synthesis: Validated evidence at https://youtube.com/watch?v=12345678901."


class TestV3ModelGatewayBridge:
    @pytest.mark.asyncio
    async def test_v3_bridge_generation_and_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "/api/chat" in url_str:
                return httpx.Response(
                    200,
                    json={
                        "message": {"role": "assistant", "content": '{"text": "Qwen extracted"}'},
                        "prompt_eval_count": 45,
                        "eval_count": 20,
                    },
                )
            if "generateContent" in url_str:
                return httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {"content": {"parts": [{"text": "Gemini synthesis section"}]}}
                        ],
                        "usageMetadata": {
                            "promptTokenCount": 80,
                            "candidatesTokenCount": 50,
                            "totalTokenCount": 130,
                        },
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        ollama = OllamaProviderAdapter(base_url="http://localhost:11434", http_client=client)
        google = GoogleGeminiProviderAdapter(api_key="AIzaSyTestKey12345", http_client=client)

        bridge = V3ModelGatewayBridge(ollama_adapter=ollama, google_adapter=google)

        # Call generate for Ollama
        resp_ollama = await bridge.generate(
            provider="ollama",
            model="qwen3.5",
            system_instruction="Extract JSON",
            prompt="Test prompt",
        )
        assert isinstance(resp_ollama, ProviderResponse)
        assert resp_ollama.text == '{"text": "Qwen extracted"}'
        assert resp_ollama.usage.prompt_tokens == 45
        assert resp_ollama.usage.completion_tokens == 20

        # Call generate for Google
        resp_google = await bridge.generate(
            provider="google",
            model="gemini-3.5-flash-lite",
            system_instruction="Synthesize report",
            prompt="Test synthesis",
        )
        assert isinstance(resp_google, ProviderResponse)
        assert resp_google.text == "Gemini synthesis section"
        assert resp_google.usage.total_tokens == 130

    @pytest.mark.asyncio
    async def test_composed_workflow_uses_v3_bridge_for_all_model_routes(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.method == "GET" and path.endswith("/api/tags"):
                return httpx.Response(200, json={"models": [{"name": "qwen3.5"}]})
            if request.method == "GET" and path.endswith("/models"):
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": "models/gemma-4-31b"},
                            {"name": "models/gemini-3.5-flash-lite"},
                        ]
                    },
                )
            if request.method == "POST" and path.endswith("/api/chat"):
                return httpx.Response(
                    200,
                    json={
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "platform": "youtube",
                                    "source_url": "https://youtube.com/watch?v=12345678901",
                                    "text": "Qwen extracted evidence.",
                                    "metrics": {"views": 500},
                                    "topics": ["test"],
                                    "claims": ["Claim 1"],
                                }
                            ),
                        },
                        "prompt_eval_count": 45,
                        "eval_count": 20,
                    },
                )
            if request.method == "POST" and path.endswith(":generateContent"):
                model = path.rsplit("/", 1)[-1].split(":", 1)[0]
                return httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": f"{model} synthesis with https://youtube.com/watch?v=12345678901"}
                                    ]
                                }
                            }
                        ],
                        "usageMetadata": {
                            "promptTokenCount": 80,
                            "candidatesTokenCount": 50,
                            "totalTokenCount": 130,
                        },
                    },
                )
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bridge = V3ModelGatewayBridge(
                ollama_adapter=OllamaProviderAdapter(
                    base_url="http://localhost:11434", http_client=client
                ),
                google_adapter=GoogleGeminiProviderAdapter(
                    api_key="AIzaSyTestKey12345", http_client=client
                ),
            )
            workflow = compose_social_research_workflow(
                model_gateway=bridge,
                browser_tool=FakeBrowserTool(),
                config=SocialResearchConfig(output_dir=str(tmp_path / "out")),
            )
            result = await workflow.run(
                query="test query",
                sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
                workspace_root=str(tmp_path),
            )

        assert result.status == "COMPLETE"
        assert isinstance(workflow.model_gateway, V3ModelGatewayBridge)
        assert [receipt.prompt_tokens for receipt in result.model_receipts] == [45, 80, 80]
        assert [receipt.completion_tokens for receipt in result.model_receipts] == [20, 50, 50]


class TestModelPreflightDiscovery:
    @pytest.mark.asyncio
    async def test_preflight_discovery_success(self, tmp_path: Path) -> None:
        gateway = ConfigurableGateway()
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(output_dir=str(tmp_path / "out")),
        )
        sources = [SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")]
        res = await workflow.run(
            query="test query", sources=sources, workspace_root=str(tmp_path)
        )
        assert res.status == "COMPLETE"
        assert len(res.model_receipts) == 3

    @pytest.mark.asyncio
    async def test_preflight_discovery_failure_blocks_run(self, tmp_path: Path) -> None:
        gateway = ConfigurableGateway()
        gateway.available_models.remove("ollama/qwen3.5")
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"), skip_model_preflight=False
            ),
        )
        sources = [SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")]
        with pytest.raises(SocialResearchError, match="Model preflight failed"):
            await workflow.run(
                query="test query", sources=sources, workspace_root=str(tmp_path)
            )

    @pytest.mark.asyncio
    async def test_mandatory_discovery_enforcement_without_api(self, tmp_path: Path) -> None:
        class FailingDiscoveryGateway:
            async def discover_models(self, provider: str):
                return []  # No models discovered

            async def generate(self, **kwargs):
                return "text"

        workflow = SocialResearchWorkflow(
            model_gateway=FailingDiscoveryGateway(),
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"), skip_model_preflight=False
            ),
        )
        sources = [SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")]
        with pytest.raises(SocialResearchError, match="Model preflight failed"):
            await workflow.run(
                query="test query", sources=sources, workspace_root=str(tmp_path)
            )

    @pytest.mark.asyncio
    async def test_gateway_without_discovery_api_is_rejected(self, tmp_path: Path) -> None:
        class GenerateOnlyGateway:
            async def generate(self, **kwargs) -> str:
                return "unused"

        workflow = SocialResearchWorkflow(
            model_gateway=GenerateOnlyGateway(),
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(output_dir=str(tmp_path / "out")),
        )
        with pytest.raises(SocialResearchError, match="Model preflight failed"):
            await workflow.run(
                query="test query",
                sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
                workspace_root=str(tmp_path),
            )

    @pytest.mark.asyncio
    async def test_skip_preflight_config(self, tmp_path: Path) -> None:
        gateway = ConfigurableGateway()
        gateway.available_models.clear()
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"), skip_model_preflight=True
            ),
        )
        sources = [SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")]
        res = await workflow.run(
            query="test query", sources=sources, workspace_root=str(tmp_path)
        )
        assert res.status == "COMPLETE"


class FlakyExtractionGateway(ConfigurableGateway):
    def __init__(self) -> None:
        super().__init__()
        self.qwen_attempts = 0

    async def generate(self, **kwargs) -> str:
        provider = kwargs.get("provider")
        if provider == "ollama":
            self.qwen_attempts += 1
            if self.qwen_attempts == 1:
                return "Not valid json object from Qwen model"
        return await super().generate(**kwargs)


class TestExtractionAndJSONRepair:
    @pytest.mark.asyncio
    async def test_qwen_json_extraction_retry_on_invalid_output(self, tmp_path: Path) -> None:
        gateway = FlakyExtractionGateway()
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"),
                model_retry_attempts=3,
                skip_model_preflight=True,
            ),
        )
        res = await workflow.run(
            query="test query",
            sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
            workspace_root=str(tmp_path),
        )
        assert res.status == "COMPLETE"
        assert gateway.qwen_attempts == 2

    @pytest.mark.asyncio
    async def test_qwen_json_extraction_with_markdown_fences(self, tmp_path: Path) -> None:
        raw_json = """```json
{
  "platform": "youtube",
  "source_url": "https://youtube.com/watch?v=12345678901",
  "author": "fenced-author",
  "text": "Extracted text in fences",
  "topics": ["fence"],
  "claims": []
}
```"""
        gateway = ConfigurableGateway(response_map={"ollama/qwen3.5": raw_json})
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(output_dir=str(tmp_path / "out")),
        )
        res = await workflow.run(
            query="test query",
            sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
            workspace_root=str(tmp_path),
        )
        assert res.successful_source_count == 1


class RetryingGateway(ConfigurableGateway):
    def __init__(
        self,
        fail_count: int = 1,
        failure_message: str = "HTTP 429 RateLimitExceeded: rate limit hit",
    ) -> None:
        super().__init__()
        self.fail_count = fail_count
        self.failure_message = failure_message
        self.attempts = 0

    async def generate(self, **kwargs) -> str:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise RuntimeError(self.failure_message)
        return await super().generate(**kwargs)


class TestGatewayRetryAndFailureClassification:
    @pytest.mark.asyncio
    async def test_gateway_retry_on_429_rate_limit(self, tmp_path: Path) -> None:
        gateway = RetryingGateway(fail_count=1)
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"),
                model_retry_attempts=3,
                model_retry_backoff_seconds=0.01,
            ),
        )
        res = await workflow.run(
            query="test query",
            sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
            workspace_root=str(tmp_path),
        )
        assert res.status == "COMPLETE"
        assert res.model_receipts[0].status == "RETRY_SUCCESS"
        assert res.model_receipts[0].attempts == 2

    @pytest.mark.asyncio
    async def test_gateway_retry_exhaustion_raises(self, tmp_path: Path) -> None:
        gateway = RetryingGateway(fail_count=5)
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"),
                model_retry_attempts=2,
                model_retry_backoff_seconds=0.01,
                allow_partial_sources=False,
            ),
        )
        with pytest.raises(SocialResearchError, match="failed after 2 attempts"):
            await workflow.run(
                query="test query",
                sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
                workspace_root=str(tmp_path),
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "failure_message",
        ["HTTP 503 Service Unavailable", "request timeout"],
    )
    async def test_gateway_retries_server_error_and_timeout(
        self, tmp_path: Path, failure_message: str
    ) -> None:
        gateway = RetryingGateway(
            fail_count=1,
            failure_message=failure_message,
        )
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(
                output_dir=str(tmp_path / "out"),
                model_retry_attempts=3,
                model_retry_backoff_seconds=0.01,
            ),
        )
        result = await workflow.run(
            query="test query",
            sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
            workspace_root=str(tmp_path),
        )

        assert result.model_receipts[0].status == "RETRY_SUCCESS"
        assert result.model_receipts[0].attempts == 2


class TestContradictionAndUnsupportedClaims:
    @pytest.mark.asyncio
    async def test_detect_contradictions_and_unsupported_urls(self, tmp_path: Path) -> None:
        response_map = {
            "google/gemma-4-31b": "Gemma synthesis: Discussion is positive at https://youtube.com/watch?v=12345678901.",
            "google/gemini-3.5-flash-lite": "Gemini synthesis: Discussion is negative at https://unknown.com/fake-url.",
        }
        gateway = ConfigurableGateway(response_map=response_map)
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(output_dir=str(tmp_path / "out")),
        )
        res = await workflow.run(
            query="test query",
            sources=[SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")],
            workspace_root=str(tmp_path),
        )
        assert res.contradiction_analysis is not None
        assert res.contradiction_analysis["contradictions_found"] is True
        assert len(res.contradiction_analysis["contradictions"]) > 0
        assert len(res.contradiction_analysis["unsupported_claims"]) > 0


class TestSecretRedaction:
    @pytest.mark.asyncio
    async def test_secret_redaction_across_reports_and_metadata(self, tmp_path: Path) -> None:
        gateway = ConfigurableGateway()
        workflow = SocialResearchWorkflow(
            model_gateway=gateway,
            browser_tool=FakeBrowserTool(),
            config=SocialResearchConfig(output_dir=str(tmp_path / "out")),
        )
        query_with_secret = "Research WindAgent with API_KEY=AIzaSyQuerySecretKey123"
        sources = [SocialSourceSpec(url="https://youtube.com/watch?v=12345678901")]
        res = await workflow.run(
            query=query_with_secret,
            sources=sources,
            workspace_root=str(tmp_path),
        )

        assert "AIzaSyQuerySecretKey123" not in res.json_path
        report_json_content = Path(res.json_path).read_text(encoding="utf-8")
        report_md_content = Path(res.markdown_path).read_text(encoding="utf-8")

        assert "AIzaSyQuerySecretKey123" not in report_json_content
        assert "AIzaSyTitleSecret999" not in report_json_content
        assert "AIzaSyUrlSecret12345" not in report_json_content

        assert "AIzaSyQuerySecretKey123" not in report_md_content
        assert "AIzaSyTitleSecret999" not in report_md_content
        assert "AIzaSyUrlSecret12345" not in report_md_content
