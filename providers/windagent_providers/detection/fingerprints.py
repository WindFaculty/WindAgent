"""
Protocol and Vendor Fingerprint Definitions for WindAgent Provider Subsystem V3.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ProtocolFingerprint:
    protocol_type: str  # "ollama", "anthropic", "gemini", "openai"
    vendor: str
    confidence: float
    evidence: List[str] = field(default_factory=list)


def detect_vendor_from_url_or_key(url: str, api_key: Optional[str] = None) -> Tuple[str, float]:
    """Matches URL patterns or API key prefixes to known vendors."""
    url_lower = url.lower()
    key_str = (api_key or "").lower()

    if "openrouter.ai" in url_lower or key_str.startswith("sk-or-"):
        return "openrouter", 0.95
    if "nvidia.com" in url_lower or key_str.startswith("nvapi-"):
        return "nvidia", 0.95
    if "mistral.ai" in url_lower:
        return "mistral", 0.95
    if "anthropic.com" in url_lower or key_str.startswith("sk-ant-"):
        return "anthropic", 0.95
    if "googleapis.com" in url_lower or key_str.startswith("aizasy"):
        return "google", 0.95
    if "openai.com" in url_lower:
        return "openai", 0.95
    if "11434" in url_lower or "ollama" in url_lower:
        return "ollama", 0.90

    return "generic", 0.30
