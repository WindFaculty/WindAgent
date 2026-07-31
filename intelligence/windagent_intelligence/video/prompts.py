"""
Versioned, hashed prompt specifications (Phase 6).

Every model-backed capability declares a `PromptSpec` with a semantic
version and a deterministic content hash over the resolved template. Any
artifact produced from a prompt must record `prompt_version` + `content_hash`
so it is traceable back to the exact prompt that produced it (see
docs/video_production/preproduction/prompt_versioning.md).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PromptSpec:
    """Immutable, versioned, hashed prompt template."""

    capability: str
    version: str  # semantic version, e.g. "1.0.0"
    template: str  # string with {placeholder} slots
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Deterministic SHA-256 over the resolved contract (capability+version+template)."""
        payload = f"{self.capability}::{self.version}::{self.template}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def render(self, **kwargs: Any) -> str:
        """Render the template with named substitutions (missing keys left intact)."""
        return self.template.format_map(_SafeDict(kwargs))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "version": self.version,
            "content_hash": self.content_hash,
            "description": self.description,
            "metadata": self.metadata,
        }


class _SafeDict(dict):
    """dict subclass that leaves unknown {placeholders} untouched instead of KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


__all__ = ["PromptSpec"]
