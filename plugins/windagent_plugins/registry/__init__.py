"""Plugin registry - async wrapper over PluginLoader.

Health checker and composition roots expect async list_plugins().
The actual loader (PluginLoader) is synchronous; this registry wraps it.
"""
from __future__ import annotations

from typing import Any, Dict, List

from windagent_plugins.loader.loader import PluginLoader


class PluginRegistry:
    """Async registry facade over PluginLoader."""

    def __init__(self, loader: PluginLoader | None = None) -> None:
        self._loader = loader or PluginLoader()

    async def list_plugins(self) -> List[Dict[str, Any]]:
        return self._loader.list_plugins()

    async def install(self, source: str) -> Dict[str, Any]:
        return self._loader.install(source)

    async def uninstall(self, plugin_id: str) -> bool:
        return self._loader.uninstall(plugin_id)


__all__ = ["PluginRegistry"]
