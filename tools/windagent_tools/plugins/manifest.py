"""
Plugin Manifest Definition & Static Validator for WindAgent Extension Platform (Phase 20).
Supports schema versioning, WindAgent compatibility range, capability & permission declaration,
dependency resolution, and signature/hash verification.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

ID_PATTERN = re.compile(r"^[a-z0-9_\-]+$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
COMPATIBILITY_RANGE_PATTERN = re.compile(r"^([><=!]+)?\d+\.\d+\.\d+$")

MANIFEST_SCHEMA_VERSION = "2.0.0"


@dataclass
class PluginDependency:
    """Declares a dependency on another plugin."""
    plugin_id: str
    version: str = "*"  # semantic version range, * means any
    optional: bool = False

    def validate(self) -> None:
        if not self.plugin_id or not ID_PATTERN.match(self.plugin_id):
            raise ValidationError(
                f"Invalid dependency plugin_id [{self.plugin_id}]."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "version": self.version,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginDependency:
        return cls(
            plugin_id=str(data.get("plugin_id", "")),
            version=str(data.get("version", "*")),
            optional=bool(data.get("optional", False)),
        )


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str = "1.0.0"
    schema_version: str = MANIFEST_SCHEMA_VERSION
    windagent_version: str = ">=0.3.0"
    entrypoint: str = "main:Plugin"
    capabilities: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    required_workflows: List[str] = field(default_factory=list)
    dependencies: List[PluginDependency] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    compatibility: str = ">=0.3.0"
    signature_hash: Optional[str] = None

    def validate(self) -> None:
        """Validates plugin manifest structure and fields."""
        if not self.id or not ID_PATTERN.match(self.id):
            raise ValidationError(
                f"Invalid plugin ID [{self.id}]. Must match pattern lowercase alphanumeric, hyphens, underscores."
            )
        if not self.name or not self.name.strip():
            raise ValidationError("Plugin name cannot be empty.")
        if not self.version or not self.version.strip():
            raise ValidationError("Plugin version cannot be empty.")
        if not self.entrypoint or ":" not in self.entrypoint:
            raise ValidationError(f"Invalid plugin entrypoint [{self.entrypoint}]. Expected format 'module:Class'.")

        # Validate schema_version format
        if self.schema_version and not SEMVER_PATTERN.match(self.schema_version.replace("v", "")):
            raise ValidationError(f"Invalid schema_version [{self.schema_version}]. Must be semver.")

        # Validate dependencies
        for dep in self.dependencies:
            dep.validate()

        # Validate capabilities (no empty strings)
        for cap in self.capabilities:
            if not cap.strip():
                raise ValidationError("Capability name cannot be empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "schema_version": self.schema_version,
            "windagent_version": self.windagent_version,
            "entrypoint": self.entrypoint,
            "capabilities": self.capabilities,
            "required_permissions": self.required_permissions,
            "required_tools": self.required_tools,
            "required_workflows": self.required_workflows,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "config_schema": self.config_schema,
            "compatibility": self.compatibility,
            "signature_hash": self.signature_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginManifest:
        deps_raw = data.get("dependencies", []) or []
        dependencies = [PluginDependency.from_dict(d) if isinstance(d, dict) else PluginDependency(plugin_id=str(d)) for d in deps_raw]

        manifest = cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "1.0.0")),
            schema_version=str(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
            windagent_version=str(data.get("windagent_version", ">=0.3.0")),
            entrypoint=str(data.get("entrypoint", "main:Plugin")),
            capabilities=data.get("capabilities", []) or [],
            required_permissions=data.get("required_permissions", []) or [],
            required_tools=data.get("required_tools", []) or [],
            required_workflows=data.get("required_workflows", []) or [],
            dependencies=dependencies,
            config_schema=data.get("config_schema", {}) or {},
            compatibility=str(data.get("compatibility", ">=0.3.0")),
            signature_hash=data.get("signature_hash"),
        )
        manifest.validate()
        return manifest
