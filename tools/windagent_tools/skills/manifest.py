"""
Skill Manifest Definition for WindAgent Intelligence & Tool System.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

SKILL_ID_PATTERN = re.compile(r"^[a-z0-9_\-]+$")


@dataclass
class SkillManifest:
    id: str
    description: str
    version: str = "1.0.0"
    activation_rules: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "activation_rules": self.activation_rules,
            "required_tools": self.required_tools,
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
            description=str(data.get("description", "")),
            activation_rules=data.get("activation_rules", []) or [],
            required_tools=data.get("required_tools", []) or [],
            required_permissions=data.get("required_permissions", []) or [],
            token_budget=int(data.get("token_budget", 2000)),
            prompt_template=str(data.get("prompt_template", "")),
            verification_policy=data.get("verification_policy", {}) or {},
        )
        skill.validate()
        return skill
