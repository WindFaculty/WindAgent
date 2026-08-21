"""
Core contracts for Browser Tool port.

Defines the protocol that browser tools must implement.
Workflows depend on this port, not on concrete tool implementations.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class BrowserToolPort(Protocol):
    """Protocol for browser URL opening tools."""

    async def execute(
        self,
        invocation: Any,
        context: Any,
    ) -> Any:
        """Execute a browser action and return results."""
        ...


def platform_for_url(url: str) -> str:
    """Determine the social platform for a given URL.

    This is a pure utility function with no dependencies on tool implementations.
    It can safely live in core as a domain utility.
    """
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "facebook.com" in url_lower or "fb.com" in url_lower:
        return "facebook"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "instagram.com" in url_lower:
        return "instagram"
    if "reddit.com" in url_lower:
        return "reddit"
    if "threads.net" in url_lower:
        return "threads"
    return "unknown"
