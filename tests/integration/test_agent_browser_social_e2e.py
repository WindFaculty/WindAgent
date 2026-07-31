from __future__ import annotations

import json
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from windagent_workflows.social_research import (
    ModelRoute,
    SocialResearchConfig,
    SocialResearchWorkflow,
    SocialSourceSpec,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_AGENT_BROWSER_E2E") != "1"
    or shutil.which(os.environ.get("AGENT_BROWSER_BIN", "agent-browser")) is None,
    reason="Set RUN_AGENT_BROWSER_E2E=1 with agent-browser installed",
)


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"""<!doctype html>
<html><head><title>WindAgent Social Fixture</title></head>
<body>
<main>
  <article>
    <h1>WindAgent browser research update</h1>
    <p>Public fixture post: the agent collected three sources and produced a report.</p>
    <dl><dt>Views</dt><dd>1200</dd><dt>Likes</dt><dd>87</dd></dl>
  </article>
</main>
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class DeterministicGateway:
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
        if provider == "ollama":
            source_url = prompt.split("Source URL: ", 1)[1].splitlines()[0]
            return json.dumps(
                {
                    "platform": "youtube",
                    "source_url": source_url,
                    "author": "fixture",
                    "published_at": None,
                    "title": "WindAgent Social Fixture",
                    "text": "The agent collected three sources and produced a report.",
                    "metrics": {
                        "views": 1200,
                        "likes": 87,
                        "comments": None,
                        "shares": None,
                    },
                    "topics": ["WindAgent", "browser research"],
                    "claims": ["A browser-driven report was produced."],
                    "language": "en",
                }
            )
        if "gemma" in model:
            return "Gemma synthesis: the fixture reports a completed browser workflow."
        return (
            "Gemini synthesis: evidence is limited to one deterministic fixture source."
        )


@pytest.mark.asyncio
async def test_real_agent_browser_collects_rendered_page_and_writes_report(
    tmp_path: Path,
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/fixture"
        config = SocialResearchConfig(
            local_extractor=ModelRoute("ollama", "qwen3.5", "structured_extractor"),
            gemma_synthesizer=ModelRoute(
                "google", "gemma-4-31b", "independent_synthesis"
            ),
            gemini_synthesizer=ModelRoute(
                "google", "gemini-3.5-flash-lite", "verification_synthesis"
            ),
            output_dir="artifacts/agent-browser-e2e",
            save_screenshots=False,
            allow_partial_sources=False,
            browser_timeout_seconds=float(
                os.environ.get("WINDAGENT_E2E_BROWSER_TIMEOUT_SECONDS", "90")
            ),
        )
        workflow = SocialResearchWorkflow(
            model_gateway=DeterministicGateway(),
            config=config,
        )
        result = await workflow.run(
            query="Did the browser workflow produce a report?",
            sources=[
                SocialSourceSpec(
                    url=url,
                    platform="youtube",
                    allowed_domains=("127.0.0.1",),
                    allow_private_network=True,
                )
            ],
            workspace_root=str(tmp_path),
            env_vars={
                "AGENT_BROWSER_BIN": os.environ.get(
                    "AGENT_BROWSER_BIN", "agent-browser"
                ),
                "WINDAGENT_BROWSER_CONTAINMENT": os.environ.get(
                    "WINDAGENT_BROWSER_CONTAINMENT", "native"
                ),
                "WINDAGENT_BROWSER_HEADLESS": "1",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.status == "COMPLETE"
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
    assert "Gemma synthesis" in markdown
    assert "Gemini synthesis" in markdown
    assert payload["sources"][0]["browser_backend"] == "vercel-labs/agent-browser"
    assert payload["sources"][0]["content_chars"] > 0
    assert payload["sources"][0]["content_sha256"]

    evidence_dir = os.environ.get("WINDAGENT_E2E_EVIDENCE_DIR")
    if evidence_dir:
        destination = Path(evidence_dir)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            result.markdown_path, destination / Path(result.markdown_path).name
        )
        shutil.copy2(result.json_path, destination / Path(result.json_path).name)
