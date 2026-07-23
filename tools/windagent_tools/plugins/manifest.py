"""
Plugin Manifest Definition & Static Validator for WindAgent Extension Platform.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

ID_PATTERN = re.compile(r"^[a-z0-9_\-]+$")


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str = "1.0.0"
    entrypoint: str = "main:Plugin"
    capabilities: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "entrypoint": self.entrypoint,
            "capabilities": self.capabilities,
            "required_permissions": self.required_permissions,
            "required_tools": self.required_tools,
            "config_schema": self.config_schema,
            "compatibility": self.compatibility,
            "signature_hash": self.signature_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginManifest:
        manifest = cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "1.0.0")),
            entrypoint=str(data.get("entrypoint", "main:Plugin")),
            capabilities=data.get("capabilities", []) or [],
            required_permissions=data.get("required_permissions", []) or [],
            required_tools=data.get("required_tools", []) or [],
            config_schema=data.get("config_schema", {}) or {},
            compatibility=str(data.get("compatibility", ">=0.3.0")),
            signature_hash=data.get("signature_hash"),
        )
        manifest.validate()
        return manifest
