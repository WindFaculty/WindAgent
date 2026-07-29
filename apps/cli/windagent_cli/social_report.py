"""CLI composition for the agent-browser social research workflow."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Sequence

from windagent_core.contracts.providers import ProviderRequest
from windagent_providers.google.adapter import GoogleGeminiProviderAdapter
from windagent_providers.ollama.adapter import OllamaProviderAdapter
from windagent_workflows.social_research import (
    ModelRoute,
    SocialResearchConfig,
    SocialResearchError,
    SocialResearchWorkflow,
    SocialSourceSpec,
)


class ProviderModelGateway:
    """Maps workflow model roles to existing WindAgent provider adapters."""

    def __init__(
        self,
        *,
        google_api_key: str,
        ollama_base_url: str = "http://localhost:11434",
        google_adapter: Optional[GoogleGeminiProviderAdapter] = None,
        ollama_adapter: Optional[OllamaProviderAdapter] = None,
    ) -> None:
        if not google_api_key.strip():
            raise SocialResearchError(
                "GOOGLE_API_KEY or GEMINI_API_KEY is required for both synthesis models."
            )
        self.google = google_adapter or GoogleGeminiProviderAdapter(
            api_key=google_api_key
        )
        self.ollama = ollama_adapter or OllamaProviderAdapter(
            base_url=ollama_base_url
        )

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
        request = ProviderRequest(
            provider_id=provider,
            model_id=model,
            messages=[{"role": "user", "content": prompt}],
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=120.0,
        )
        if provider == "ollama":
            response = await self.ollama.generate(request, model_id=model)
        elif provider == "google":
            response = await self.google.generate(request, model_id=model)
        else:
            raise SocialResearchError(f"Unsupported model provider: {provider}")
        text = response.text or ""
        if not text.strip():
            raise SocialResearchError(
                f"Provider {provider}/{model} returned no text output."
            )
        return text

    async def validate_models(self, routes: Sequence[ModelRoute]) -> dict[str, list[str]]:
        discovered: dict[str, list[str]] = {}
        for provider in sorted({route.provider for route in routes}):
            if provider == "ollama":
                models = await self.ollama.list_models()
            elif provider == "google":
                models = await self.google.list_models()
            else:
                raise SocialResearchError(f"Unsupported model provider: {provider}")
            discovered[provider] = sorted(
                {
                    str(getattr(item, "raw_model_id", "")).replace("models/", "")
                    for item in models
                    if getattr(item, "raw_model_id", None)
                }
            )

        missing: list[str] = []
        for route in routes:
            available = discovered.get(route.provider, [])
            if not _model_is_available(route.model, available, route.provider):
                missing.append(f"{route.provider}/{route.model}")
        if missing:
            summaries = "; ".join(
                f"{provider}={models[:20]}" for provider, models in discovered.items()
            )
            raise SocialResearchError(
                "Configured model IDs were not discovered: "
                f"{', '.join(missing)}. Available models: {summaries}"
            )
        return discovered


def _model_is_available(model: str, available: Sequence[str], provider: str) -> bool:
    clean = model.replace("models/", "")
    if clean in available:
        return True
    if provider == "ollama":
        return any(item.split(":", 1)[0] == clean for item in available)
    return False


async def execute_social_report(
    *,
    query: str,
    urls: Sequence[str],
    output_dir: str,
    local_model: str,
    gemma_model: str,
    gemini_model: str,
    browser_session_prefix: str,
    browser_profile: Optional[str],
    browser_state: Optional[str],
    authenticated: bool,
    skip_model_preflight: bool,
    save_screenshots: bool,
) -> dict[str, Any]:
    env = dict(os.environ)
    if authenticated and not (browser_profile or browser_state):
        raise SocialResearchError(
            "--authenticated requires --browser-profile or --browser-state."
        )
    if not authenticated and (browser_profile or browser_state):
        raise SocialResearchError(
            "Browser profile/state access requires the explicit --authenticated flag."
        )
    if browser_profile and browser_state:
        raise SocialResearchError(
            "Use either --browser-profile or --browser-state, not both."
        )
    if browser_profile:
        env["AGENT_BROWSER_PROFILE"] = browser_profile
    if browser_state:
        env["AGENT_BROWSER_STATE"] = browser_state
    if authenticated:
        env["WINDAGENT_BROWSER_CONTAINMENT"] = "preflight"
        if browser_state:
            env["AGENT_BROWSER_RESTORE"] = "1"
    else:
        env.setdefault("WINDAGENT_BROWSER_CONTAINMENT", "native")

    google_api_key = env.get("GOOGLE_API_KEY") or env.get("GEMINI_API_KEY") or ""
    gateway = ProviderModelGateway(
        google_api_key=google_api_key,
        ollama_base_url=env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    config = SocialResearchConfig(
        local_extractor=ModelRoute(
            provider="ollama", model=local_model, role="structured_extractor"
        ),
        gemma_synthesizer=ModelRoute(
            provider="google", model=gemma_model, role="independent_synthesis"
        ),
        gemini_synthesizer=ModelRoute(
            provider="google", model=gemini_model, role="verification_synthesis"
        ),
        output_dir=output_dir,
        browser_session_prefix=browser_session_prefix,
        save_screenshots=save_screenshots,
    )
    routes = (
        config.local_extractor,
        config.gemma_synthesizer,
        config.gemini_synthesizer,
    )
    discovered = None
    if not skip_model_preflight:
        discovered = await gateway.validate_models(routes)

    browser_env = {
        key: value
        for key, value in env.items()
        if key.startswith("AGENT_BROWSER_")
        or key.startswith("WINDAGENT_BROWSER_")
    }
    workflow = SocialResearchWorkflow(model_gateway=gateway, config=config)
    result = await workflow.run(
        query=query,
        sources=[SocialSourceSpec(url=url) for url in urls],
        workspace_root=str(Path.cwd()),
        env_vars=browser_env,
    )
    payload = asdict(result)
    payload["models"] = [asdict(route) for route in result.models]
    payload["model_preflight"] = discovered
    payload["data_source"] = "LIVE"
    payload["non_production"] = False
    return payload
