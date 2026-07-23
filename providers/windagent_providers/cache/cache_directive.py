"""
Helpers for provider-native cache directives.
"""

from __future__ import annotations

from typing import Dict, Optional

from windagent_providers.base.contracts import CacheDirective


def to_provider_headers(
    directive: Optional[CacheDirective], provider_name: str
) -> Dict[str, str]:
    """
    Map generic CacheDirective to provider-specific cache headers.

    Currently supports Anthropic prompt caching header.  Additional mappings
    are added here as providers expose stable cache-control APIs.
    """
    headers: Dict[str, str] = {}
    if directive is None:
        return headers

    if provider_name == "anthropic":
        if directive.enable_prompt_cache:
            headers["anthropic-beta"] = "prompt-caching-2024-07-31"

    return headers
