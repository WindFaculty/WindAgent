"""
Plugin system for extensible functionality - loader, registry, lifecycle, security, manifest
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_plugins.loader.loader import PluginLoader
from windagent_plugins.manifest.manifest import PluginDependency, PluginManifest

__version__ = PRODUCT_VERSION
__all__ = ["PluginLoader", "PluginManifest", "PluginDependency"]
