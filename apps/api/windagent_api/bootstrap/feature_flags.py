"""
Feature Flags Manager for Application Bootstrap.
Manages cutover feature flags loaded from environment variables.
"""

from __future__ import annotations
import os
from typing import Dict


class FeatureFlagsManager:
    """Manages feature flags controlling Architecture V2 cutover."""

    DEFAULT_FLAGS: Dict[str, bool] = {
        "WINDAGENT_ARCH_V2": True,
        "WINDAGENT_V2_TASKS": True,
        "WINDAGENT_V2_PROVIDERS": True,
        "WINDAGENT_V2_TOOLS": True,
        "WINDAGENT_V2_WORKFLOWS": True,
    }

    def __init__(self) -> None:
        self._flags: Dict[str, bool] = dict(self.DEFAULT_FLAGS)
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Loads feature flag overrides from environment variables if present."""
        for flag in self.DEFAULT_FLAGS:
            env_val = os.getenv(flag)
            if env_val is not None:
                self._flags[flag] = env_val.lower() in ("true", "1", "yes")

    def get_flag(self, name: str) -> bool:
        """Returns current status of specified feature flag."""
        return self._flags.get(name, False)

    def set_flag(self, name: str, enabled: bool) -> None:
        """Sets feature flag state."""
        self._flags[name] = enabled

    def is_v2_enabled(self) -> bool:
        """Returns True if master Architecture V2 cutover is active."""
        return self.get_flag("WINDAGENT_ARCH_V2")
