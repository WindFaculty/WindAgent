"""Composition root for the social-research model-routing workflow.

This module deliberately lives at the application boundary: the workflow stays
independent of provider implementations while the CLI/runtime can compose the
native Ollama and Google adapters through ``V3ModelGatewayBridge``.
"""

from __future__ import annotations

from typing import Optional

from windagent_providers.gateway_bridge import V3ModelGatewayBridge
from windagent_tools.browser import OpenURLTool
from windagent_workflows.social_research import (
    ModelGatewayPort,
    SocialResearchConfig,
    SocialResearchWorkflow,
)


def compose_social_research_workflow(
    *,
    config: Optional[SocialResearchConfig] = None,
    browser_tool: Optional[OpenURLTool] = None,
    model_gateway: Optional[ModelGatewayPort] = None,
) -> SocialResearchWorkflow:
    """Build a social-research workflow with the production model gateway.

    Tests and alternative runtimes may provide a compatible gateway explicitly;
    production callers receive the V3 Ollama/Google bridge by default.
    """

    return SocialResearchWorkflow(
        model_gateway=model_gateway or V3ModelGatewayBridge(),
        browser_tool=browser_tool,
        config=config,
    )


__all__ = ["compose_social_research_workflow"]
