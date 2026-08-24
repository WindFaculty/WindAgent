"""Simple Python factory functions for canonical fixtures.

No external dependency (factory_boy/polyfactory) required — simple functions
suffice for deterministic test data. Add new factories here as needed.
"""

from __future__ import annotations

from typing import Any, Dict

from tests.fixtures.canonical.canonical_bunny_episode import build_canonical_bunny_episode

def build_episode_fixture(**overrides: Any) -> Dict[str, Any]:
    """Build a canonical bunny episode fixture with optional overrides."""
    base = build_canonical_bunny_episode()
    base.update(overrides)
    return base

__all__ = ["build_episode_fixture", "build_canonical_bunny_episode"]
