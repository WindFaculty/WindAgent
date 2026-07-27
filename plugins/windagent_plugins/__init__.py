"""
Plugin system for extensible functionality - loader, registry, lifecycle, security, manifest
"""

from windagent_plugins.loader.loader import PluginLoader
from windagent_plugins.manifest.manifest import PluginDependency, PluginManifest

__version__ = "0.3.0"
__all__ = ["PluginLoader", "PluginManifest", "PluginDependency"]
