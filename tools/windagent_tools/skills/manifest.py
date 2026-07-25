"""
Skill Manifest Definition for WindAgent Intelligence & Tool System (Phase 20).
Supports schema versioning, WindAgent compatibility range, required tools/workflows,
and token budget declaration.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from windagent_core.errors.exceptions import ValidationError

SKILL_ID_PATTERN = re.compile(r"^[a-z0-9_\-]+$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

MANIFEST_SCHEMA_VERSION = "2.0.0"


@dataclass
class SkillManifest:
    id: str
    description: str
    version: str = "1.0.0"
    schema_version: str = MANIFEST_SCHEMA_VERSION
    windagent_version: str = ">=0.3.0"
    activation_rules: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    required_workflows: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    token_budget: int = 2000
    prompt_template: str = ""
    verification_policy: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.id or not SKILL_ID_PATTERN.match(self.id):
            raise ValidationError(
                f"Invalid skill ID [{self.id}]. Must match lowercase alphanumeric, hyphens, underscores."
            )
        if not self.description or not self.description.strip():
            raise ValidationError("Skill description cannot be empty.")
        if self.token_budget <= 0:
            raise ValidationError("Skill token_budget must be > 0.")

        # Validate schema_version format
        if self.schema_version and not SEMVER_PATTERN.match(self.schema_version.replace("v", "")):
            raise ValidationError(f"Invalid schema_version [{self.schema_version}]. Must be semver.")

        # Validate required tools (no empty names)
        for tool_name in self.required_tools:
            if not tool_name.strip():
                raise ValidationError("Required tool name cannot be empty.")

        # Validate required workflows (no empty names)
        for wf_name in self.required_workflows:
            if not wf_name.strip():
                raise ValidationError("Required workflow name cannot be empty.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "schema_version": self.schema_version,
            "windagent_version": self.windagent_version,
            "description": self.description,
            "activation_rules": self.activation_rules,
            "required_tools": self.required_tools,
            "required_workflows": self.required_workflows,
            "required_permissions": self.required_permissions,
            "token_budget": self.token_budget,
            "prompt_template": self.prompt_template,
            "verification_policy": self.verification_policy,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillManifest:
        skill = cls(
            id=str(data.get("id", "")),
            version=str(data.get("version", "1.0.0")),
            schema_version=str(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
            windagent_version=str(data.get("windagent_version", ">=0.3.0")),
            description=str(data.get("description", "")),
            activation_rules=data.get("activation_rules", []) or [],
            required_tools=data.get("required_tools", []) or [],
            required_workflows=data.get("required_workflows", []) or [],
            required_permissions=data.get("required_permissions", []) or [],
            token_budget=int(data.get("token_budget", 2000)),
            prompt_template=str(data.get("prompt_template", "")),
            verification_policy=data.get("verification_policy", {}) or {},
        )
        skill.validate()
        return skill
