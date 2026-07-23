"""
Response-cache eligibility rules for WindAgent Provider Subsystem V3.

Cache is opt-in and conservative.  These rules live in one place so they can be
audited and tested independently of backend adapters.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from windagent_providers.base.contracts import ProviderRequest


def response_cache_eligible(
    request: ProviderRequest,
    *,
    equivalence_level: str = "exact_revision",
    explicit_opt_in: bool = False,
) -> bool:
    """
    Return True only when response caching is safe.

    Conservative defaults:
    - explicit opt-in via cache_directive, OR exact_revision binding used
    - no tools with possible side effects
    - no high temperature without seed
    - no cancellation requested
    """
    directive = request.cache_directive
    if directive is not None and directive.enable_response_cache is False:
        return False

    enabled = (
        explicit_opt_in or
        (directive is not None and directive.enable_response_cache is True) or
        (equivalence_level == "exact_revision")
    )
    if not enabled:
        return False

    if request.is_cancelled is not None and request.is_cancelled():
        return False

    # High temperature without seed = non-deterministic.
    if request.temperature is not None and request.temperature > 0.0:
        if request.seed is None:
            return False

    # Tools that may have side effects are not cached.
    if request.tools:
        for tool in request.tools:
            if _tool_has_side_effects(tool):
                return False

    # Provider extensions often contain per-request state / secrets.
    if request.provider_extensions:
        # Known safe hints (temperature overrides, etc.) are numeric or bool.
        for key, value in request.provider_extensions.items():
            if isinstance(value, (int, float, bool)):
                continue
            # Any string extension could be a secret or mutable id.
            if isinstance(value, str):
                return False
            if isinstance(value, (dict, list)):
                return False

    return True


def _tool_has_side_effects(tool: Dict[str, Any]) -> bool:
    metadata = tool.get("function", tool)
    name = str(metadata.get("name", "")).lower()
    description = str(metadata.get("description", "")).lower()

    side_effect_hints = (
        "send", "write", "create", "delete", "update", "post", "publish",
        "buy", "sell", "transfer", "execute", "run", "deploy", "commit",
        "upload", "download", "shell", "browser", "computer", "file",
    )
    if any(hint in name or hint in description for hint in side_effect_hints):
        return True

    # Tool call results are generally unknown; conservative default.
    return False
