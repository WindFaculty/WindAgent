"""
Plugin Loader & Lifecycle Manager for WindAgent Extension Platform (Phase 20).
Enforces disabled-by-default policy, allowlist matching, and hash verification.
Supports durable content roots for install, update, uninstall, quarantine, and hot reload.
Enforces namespace isolation so plugins cannot collide with tools or workflows.
"""

from __future__ import annotations
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from windagent_core.errors.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from windagent_tools.plugins.manifest import PluginDependency, PluginManifest

logger = logging.getLogger("windagent.tools.plugins")

# Default content root paths (relative to workspace)
DEFAULT_PLUGINS_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "plugins")
INSTALLED_DIR = os.path.join(DEFAULT_PLUGINS_ROOT, "installed")
MANIFESTS_DIR = os.path.join(DEFAULT_PLUGINS_ROOT, "manifests")
QUARANTINE_DIR = os.path.join(DEFAULT_PLUGINS_ROOT, "quarantine")
REGISTRY_DIR = os.path.join(DEFAULT_PLUGINS_ROOT, "registry")


class PluginLoader:
    def __init__(
        self,
        allowlist: Optional[Set[str]] = None,
        enforce_allowlist: bool = True,
        plugins_root: Optional[str] = None,
        dev_hot_reload: bool = False,
    ):
        self.allowlist = allowlist or set()
        self.enforce_allowlist = enforce_allowlist
        self.plugins_root = plugins_root or DEFAULT_PLUGINS_ROOT
        self.installed_dir = os.path.join(self.plugins_root, "installed")
        self.manifests_dir = os.path.join(self.plugins_root, "manifests")
        self.quarantine_dir = os.path.join(self.plugins_root, "quarantine")
        self.registry_dir = os.path.join(self.plugins_root, "registry")
        self.dev_hot_reload = dev_hot_reload
        self._manifests: Dict[str, PluginManifest] = {}
        self._enabled_plugins: Set[str] = set()
        self._quarantined_plugins: Set[str] = set()
        # Track known tool and workflow names for namespace collision detection
        self._registered_tool_names: Set[str] = set()
        self._registered_workflow_names: Set[str] = set()

        # Ensure content directories exist
        for d in [self.installed_dir, self.manifests_dir, self.quarantine_dir, self.registry_dir]:
            os.makedirs(d, exist_ok=True)

    # ------------------------------------------------------------------
    # Allowlist management
    # ------------------------------------------------------------------

    def add_to_allowlist(self, plugin_id: str) -> None:
        """Adds a plugin ID to the allowlist."""
        self.allowlist.add(plugin_id)

    def remove_from_allowlist(self, plugin_id: str) -> None:
        """Removes a plugin ID from the allowlist."""
        self.allowlist.discard(plugin_id)

    # ------------------------------------------------------------------
    # Tool / Workflow name registration (for collision detection)
    # ------------------------------------------------------------------

    def register_tool_names(self, names: Set[str]) -> None:
        """Registers known tool names for namespace collision detection."""
        self._registered_tool_names.update(names)

    def register_workflow_names(self, names: Set[str]) -> None:
        """Registers known workflow names for namespace collision detection."""
        self._registered_workflow_names.update(names)

    # ------------------------------------------------------------------
    # Manifest registration (in-memory)
    # ------------------------------------------------------------------

    def register_manifest(self, manifest: PluginManifest) -> None:
        """Registers a plugin manifest. All plugins remain disabled by default."""
        manifest.validate()
        if manifest.id in self._manifests:
            raise ConflictError(f"Plugin with ID [{manifest.id}] is already registered.")

        # Namespace collision: plugin ID must not collide with tools or workflows
        if manifest.id in self._registered_tool_names:
            raise ConflictError(
                f"Plugin ID [{manifest.id}] collides with a registered tool name. "
                f"Plugin namespace isolation requires unique names across tools and plugins."
            )
        if manifest.id in self._registered_workflow_names:
            raise ConflictError(
                f"Plugin ID [{manifest.id}] collides with a registered workflow name. "
                f"Plugin namespace isolation requires unique names across workflows and plugins."
            )

        self._manifests[manifest.id] = manifest
        logger.info(f"Registered plugin manifest [{manifest.id}] v{manifest.version} (Status: Disabled by default)")

    def unregister_manifest(self, plugin_id: str) -> None:
        """Removes a plugin manifest from memory."""
        if plugin_id in self._manifests:
            del self._manifests[plugin_id]
            self._enabled_plugins.discard(plugin_id)
            logger.info(f"Unregistered plugin manifest [{plugin_id}]")

    # ------------------------------------------------------------------
    # Content root persistence (install / uninstall / update)
    # ------------------------------------------------------------------

    def install_plugin(self, manifest: PluginManifest, source_path: Optional[str] = None) -> str:
        """Installs a plugin to the content root.
        - Validates and registers the manifest
        - Copies plugin files to installed/ directory
        - Persists manifest to manifests/ directory
        - Is idempotent for the same version
        Returns the install path.
        """
        manifest.validate()

        # Resolve dependencies before installing
        self._resolve_dependencies(manifest, source_path)

        # Check if already installed at same version (idempotent)
        installed_manifest_path = os.path.join(self.manifests_dir, f"{manifest.id}.json")
        if os.path.exists(installed_manifest_path):
            with open(installed_manifest_path, "r") as f:
                existing = json.load(f)
            if existing.get("version") == manifest.version:
                logger.info(f"Plugin [{manifest.id}] v{manifest.version} already installed. Skipping (idempotent).")
                return os.path.join(self.installed_dir, manifest.id)

        # Register plugin in memory (will check namespace collision)
        if manifest.id in self._manifests:
            # Allow re-registration if version changed (update)
            if self._manifests[manifest.id].version != manifest.version:
                logger.info(f"Upgrading plugin [{manifest.id}] from v{self._manifests[manifest.id].version} to v{manifest.version}")
                self.unregister_manifest(manifest.id)
            else:
                raise ConflictError(f"Plugin [{manifest.id}] v{manifest.version} is already registered. Use update_plugin to change.")

        self.register_manifest(manifest)

        # Create install directory
        install_path = os.path.join(self.installed_dir, manifest.id)
        os.makedirs(install_path, exist_ok=True)

        # Copy plugin source files if provided
        if source_path and os.path.isdir(source_path):
            for item in os.listdir(source_path):
                s = os.path.join(source_path, item)
                d = os.path.join(install_path, item)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
                elif os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
            logger.info(f"Copied plugin files for [{manifest.id}] from {source_path} to {install_path}")
        else:
            # Create minimal plugin stub
            stub_path = os.path.join(install_path, "__init__.py")
            if not os.path.exists(stub_path):
                with open(stub_path, "w") as f:
                    f.write(f'# Plugin [{manifest.id}] v{manifest.version}\n')

        # Persist manifest to manifests directory
        with open(installed_manifest_path, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # Persist to registry index
        self._update_registry_index(manifest)

        logger.info(f"Installed plugin [{manifest.id}] v{manifest.version} at {install_path}")
        return install_path

    def uninstall_plugin(self, plugin_id: str, version: Optional[str] = None) -> bool:
        """Uninstalls a plugin from the content root.
        If version is specified, only uninstalls if version matches (safety check).
        Idempotent.
        """
        installed_manifest_path = os.path.join(self.manifests_dir, f"{plugin_id}.json")

        # Check manifest exists
        if os.path.exists(installed_manifest_path):
            with open(installed_manifest_path, "r") as f:
                existing = json.load(f)
            if version and existing.get("version") != version:
                logger.warning(
                    f"Cannot uninstall plugin [{plugin_id}]: specified version [{version}] "
                    f"does not match installed version [{existing.get('version')}]."
                )
                return False
        else:
            if plugin_id not in self._manifests:
                logger.info(f"Plugin [{plugin_id}] is not installed. Nothing to uninstall.")
                return False

        # Remove from quarantine if present
        self._quarantined_plugins.discard(plugin_id)

        # Remove installed files
        install_path = os.path.join(self.installed_dir, plugin_id)
        if os.path.exists(install_path):
            shutil.rmtree(install_path)
            logger.info(f"Removed plugin install directory [{install_path}]")

        # Remove manifest file
        if os.path.exists(installed_manifest_path):
            os.remove(installed_manifest_path)

        # Remove from registry index
        self._remove_from_registry_index(plugin_id)

        # Clean up in-memory state
        self.unregister_manifest(plugin_id)

        logger.info(f"Uninstalled plugin [{plugin_id}].")
        return True

    def update_plugin(
        self,
        manifest: PluginManifest,
        source_path: Optional[str] = None,
    ) -> str:
        """Updates a plugin to a new version.
        Validates the manifest, uninstalls the old version, installs the new one.
        Preserves enabled/disabled status.
        """
        was_enabled = self.is_enabled(manifest.id)

        # Uninstall old version (if present)
        self.uninstall_plugin(manifest.id)

        # Install new version
        install_path = self.install_plugin(manifest, source_path)

        # Restore enabled status
        if was_enabled:
            self._enabled_plugins.add(manifest.id)

        logger.info(f"Updated plugin [{manifest.id}] to v{manifest.version}")
        return install_path

    # ------------------------------------------------------------------
    # Enable / Disable
    # ------------------------------------------------------------------

    def enable_plugin(self, plugin_id: str, expected_hash: Optional[str] = None) -> None:
        """Enables a registered plugin after verifying allowlist and signature hash."""
        if plugin_id in self._quarantined_plugins:
            raise PermissionDeniedError(
                message=f"Plugin [{plugin_id}] is quarantined and cannot be enabled.",
                code="WINDAGENT_ERR_PLUGIN_QUARANTINED",
                details={"plugin_id": plugin_id},
            )

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

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    def quarantine_plugin(self, plugin_id: str, reason: str = "misbehavior") -> bool:
        """Moves a plugin to quarantine isolation.
        Disables the plugin, moves its files to quarantine/, and records the reason.
        """
        if plugin_id not in self._manifests and not os.path.exists(os.path.join(self.installed_dir, plugin_id)):
            logger.warning(f"Cannot quarantine plugin [{plugin_id}]: not installed.")
            return False

        self.disable_plugin(plugin_id)
        self._quarantined_plugins.add(plugin_id)

        # Move installed files to quarantine
        install_path = os.path.join(self.installed_dir, plugin_id)
        quarantine_path = os.path.join(self.quarantine_dir, plugin_id)
        if os.path.exists(install_path):
            if os.path.exists(quarantine_path):
                shutil.rmtree(quarantine_path)
            shutil.move(install_path, quarantine_path)

        # Write quarantine record
        record_path = os.path.join(quarantine_path, ".quarantine.json")
        record = {
            "plugin_id": plugin_id,
            "reason": reason,
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(record_path, "w") as f:
            json.dump(record, f, indent=2)

        logger.warning(f"Plugin [{plugin_id}] quarantined: {reason}")
        return True

    def release_from_quarantine(self, plugin_id: str) -> bool:
        """Releases a plugin from quarantine and restores its files to installed/.
        Does NOT enable the plugin (remains disabled by default).
        """
        if plugin_id not in self._quarantined_plugins:
            logger.warning(f"Plugin [{plugin_id}] is not quarantined.")
            return False

        quarantine_path = os.path.join(self.quarantine_dir, plugin_id)
        install_path = os.path.join(self.installed_dir, plugin_id)

        if os.path.exists(quarantine_path):
            if os.path.exists(install_path):
                shutil.rmtree(install_path)
            shutil.move(quarantine_path, install_path)

        self._quarantined_plugins.discard(plugin_id)
        logger.info(f"Plugin [{plugin_id}] released from quarantine.")
        return True

    def is_quarantined(self, plugin_id: str) -> bool:
        return plugin_id in self._quarantined_plugins

    def list_quarantined(self) -> List[Dict[str, Any]]:
        """Lists all quarantined plugins with their quarantine records."""
        results = []
        for pid in self._quarantined_plugins:
            record_path = os.path.join(self.quarantine_dir, pid, ".quarantine.json")
            record = {}
            if os.path.exists(record_path):
                with open(record_path, "r") as f:
                    record = json.load(f)
            results.append({"plugin_id": pid, **record})
        return results

    # ------------------------------------------------------------------
    # Hot reload (development only)
    # ------------------------------------------------------------------

    def hot_reload_plugin(self, plugin_id: str) -> bool:
        """Hot-reloads a plugin from the installed content root.
        Only available when dev_hot_reload=True.
        """
        if not self.dev_hot_reload:
            raise PermissionDeniedError(
                message="Hot reload is only allowed in development mode.",
                code="WINDAGENT_ERR_DEV_MODE_ONLY",
                details={"plugin_id": plugin_id},
            )

        # Reload manifest from persisted file
        manifest_path = os.path.join(self.manifests_dir, f"{plugin_id}.json")
        if not os.path.exists(manifest_path):
            raise NotFoundError(f"Cannot hot-reload plugin [{plugin_id}]: manifest not found at {manifest_path}")

        with open(manifest_path, "r") as f:
            data = json.load(f)

        new_manifest = PluginManifest.from_dict(data)

        was_enabled = self.is_enabled(plugin_id)
        self.unregister_manifest(plugin_id)
        self.register_manifest(new_manifest)
        if was_enabled:
            self._enabled_plugins.add(plugin_id)

        logger.info(f"Hot-reloaded plugin [{plugin_id}] v{new_manifest.version}")
        return True

    def reload_all(self) -> int:
        """Hot-reloads all installed plugins from the manifests content root.
        Only available when dev_hot_reload=True.
        """
        if not os.path.exists(self.manifests_dir):
            return 0

        count = 0
        for filename in os.listdir(self.manifests_dir):
            if filename.endswith(".json"):
                plugin_id = filename[:-5]
                try:
                    self.hot_reload_plugin(plugin_id)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to hot-reload plugin [{plugin_id}]: {e}")
        logger.info(f"Hot-reloaded {count} plugins from manifests content root.")
        return count

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> PluginManifest:
        if plugin_id not in self._manifests:
            raise NotFoundError(f"Plugin [{plugin_id}] is not found.")
        return self._manifests[plugin_id]

    def list_plugins(self) -> List[Dict[str, Any]]:
        return [
            {
                **m.to_dict(),
                "enabled": m.id in self._enabled_plugins,
                "quarantined": m.id in self._quarantined_plugins,
            }
            for m in self._manifests.values()
        ]

    def list_enabled_plugins(self) -> List[PluginManifest]:
        return [m for m in self._manifests.values() if m.id in self._enabled_plugins]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_dependencies(self, manifest: PluginManifest, source_path: Optional[str] = None) -> None:
        """Resolves and validates plugin dependencies before installation.
        Checks that all required dependencies are already installed.
        """
        for dep in manifest.dependencies:
            if dep.optional:
                continue
            # Check if dependency is already installed or registered
            dep_manifest_path = os.path.join(self.manifests_dir, f"{dep.plugin_id}.json")
            if dep.plugin_id in self._manifests:
                continue
            if os.path.exists(dep_manifest_path):
                # Dependency exists in content root; load it
                with open(dep_manifest_path, "r") as f:
                    dep_data = json.load(f)
                dep_manifest = PluginManifest.from_dict(dep_data)
                self.register_manifest(dep_manifest)
                continue
            raise ValidationError(
                f"Plugin [{manifest.id}] requires dependency [{dep.plugin_id}] "
                f"which is not installed. Install the dependency first."
            )

    def _update_registry_index(self, manifest: PluginManifest) -> None:
        """Persists plugin info to the registry index file."""
        index_path = os.path.join(self.registry_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                index = json.load(f)
        else:
            index = {"plugins": [], "updated_at": ""}

        # Remove existing entry for this plugin
        index["plugins"] = [p for p in index["plugins"] if p.get("id") != manifest.id]

        index["plugins"].append({
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "capabilities": manifest.capabilities,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        })
        index["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

    def _remove_from_registry_index(self, plugin_id: str) -> None:
        """Removes a plugin from the registry index file."""
        index_path = os.path.join(self.registry_dir, "index.json")
        if not os.path.exists(index_path):
            return

        with open(index_path, "r") as f:
            index = json.load(f)

        index["plugins"] = [p for p in index["plugins"] if p.get("id") != plugin_id]
        index["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

    def load_registry_index(self) -> Dict[str, Any]:
        """Loads the persisted registry index."""
        index_path = os.path.join(self.registry_dir, "index.json")
        if not os.path.exists(index_path):
            return {"plugins": [], "updated_at": ""}
        with open(index_path, "r") as f:
            return json.load(f)
