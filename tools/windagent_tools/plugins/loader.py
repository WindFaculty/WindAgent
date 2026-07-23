"""
Plugin Loader & Lifecycle Manager for WindAgent Extension Platform.
Enforces disabled-by-default policy, allowlist matching, and hash verification.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Set

from windagent_core.errors.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from windagent_tools.plugins.manifest import PluginManifest

logger = logging.getLogger("windagent.tools.plugins")


class PluginLoader:
    def __init__(self, allowlist: Optional[Set[str]] = None, enforce_allowlist: bool = True):
        self.allowlist = allowlist or set()
        self.enforce_allowlist = enforce_allowlist
        self._manifests: Dict[str, PluginManifest] = {}
        self._enabled_plugins: Set[str] = set()

    def register_manifest(self, manifest: PluginManifest) -> None:
        """Registers a plugin manifest. All plugins remain disabled by default."""
        manifest.validate()
        if manifest.id in self._manifests:
            raise ConflictError(f"Plugin with ID [{manifest.id}] is already registered.")

        self._manifests[manifest.id] = manifest
        logger.info(f"Registered plugin manifest [{manifest.id}] v{manifest.version} (Status: Disabled by default)")

    def enable_plugin(self, plugin_id: str, expected_hash: Optional[str] = None) -> None:
        """Enables a registered plugin after verifying allowlist and signature hash."""
        if plugin_id not in self._manifests:
            raise NotFoundError(f"Plugin [{plugin_id}] is not registered.")

        manifest = self._manifests[plugin_id]

        if self.enforce_allowlist and plugin_id not in self.allowlist:
            raise PermissionDeniedError(
                message=f"Plugin [{plugin_id}] is not in the system allowlist.",
                code="WINDAGENT_ERR_PLUGIN_NOT_ALLOWED",
                details={"plugin_id": plugin_id},
            )

        if expected_hash and manifest.signature_hash and manifest.signature_hash != expected_hash:
            raise ValidationError(
                f"Plugin [{plugin_id}] hash verification failed. Expected {expected_hash}, got {manifest.signature_hash}."
            )

        self._enabled_plugins.add(plugin_id)
        logger.info(f"Plugin [{plugin_id}] has been enabled.")

    def disable_plugin(self, plugin_id: str) -> None:
        if plugin_id in self._enabled_plugins:
            self._enabled_plugins.remove(plugin_id)
            logger.info(f"Plugin [{plugin_id}] has been disabled.")

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id in self._enabled_plugins

    def get_plugin(self, plugin_id: str) -> PluginManifest:
        if plugin_id not in self._manifests:
            raise NotFoundError(f"Plugin [{plugin_id}] is not found.")
        return self._manifests[plugin_id]

    def list_plugins(self) -> List[Dict[str, Any]]:
        return [
            {
                **m.to_dict(),
                "enabled": m.id in self._enabled_plugins,
            }
            for m in self._manifests.values()
        ]
