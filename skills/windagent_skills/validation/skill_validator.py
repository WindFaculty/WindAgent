"""Skill Manifest and Permission Validator (Phase 12 — ban_ke_hoach_v1 §18, §29).

Enforces dependency validation and permission auditing for proposed skill candidates:
1. Manifest Structure & Semver Validation.
2. Tool & Workflow Dependency Checking against registered capabilities.
3. Permission Auditing: Ensures declared permissions are within host allowlists and
   blocks unauthorized privilege escalation attempts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from windagent_core.errors.exceptions import ValidationError
from windagent_skills.manifest.manifest import SkillManifest


# Host allowlisted permissions for standard skills
ALLOWED_SKILL_PERMISSIONS: Set[str] = {
    "file:read",
    "file:write",
    "tool:execute",
    "workflow:invoke",
    "network:sandbox",
    "memory:read",
    "memory:write",
    "context:read",
}

# Forbidden / dangerous privilege escalation permissions
FORBIDDEN_SKILL_PERMISSIONS: Set[str] = {
    "system:root",
    "credential:access",
    "arbitrary_exec",
    "security:bypass",
    "host:modify",
    "provider:raw_access",
}


class SkillValidator:
    """Validates skill manifests, dependencies, and permission boundaries."""

    def __init__(
        self,
        registered_tools: Optional[Set[str]] = None,
        registered_workflows: Optional[Set[str]] = None,
        allowed_permissions: Optional[Set[str]] = None,
    ) -> None:
        self.registered_tools: Set[str] = set(registered_tools or set())
        self.registered_workflows: Set[str] = set(registered_workflows or set())
        self.allowed_permissions: Set[str] = set(allowed_permissions or ALLOWED_SKILL_PERMISSIONS)

    def validate_manifest(self, manifest_dict: Dict[str, Any]) -> tuple[bool, Optional[SkillManifest], List[str]]:
        """Validates manifest dictionary structure, required fields, and semver.
        Returns (is_valid, parsed_manifest, violations).
        """
        violations: List[str] = []
        try:
            manifest = SkillManifest.from_dict(manifest_dict)
            return True, manifest, []
        except ValidationError as e:
            violations.append(str(e))
            return False, None, violations
        except Exception as e:
            violations.append(f"Unexpected error validating manifest: {e}")
            return False, None, violations

    def validate_dependencies(
        self,
        required_tools: List[str],
        required_workflows: List[str],
    ) -> tuple[bool, List[str]]:
        """Validates that all required tools and workflows exist in the registry."""
        violations: List[str] = []

        if self.registered_tools:
            for tool_name in required_tools:
                if tool_name not in self.registered_tools:
                    violations.append(
                        f"Required tool [{tool_name}] is not registered in the system tool registry."
                    )

        if self.registered_workflows:
            for wf_name in required_workflows:
                if wf_name not in self.registered_workflows:
                    violations.append(
                        f"Required workflow [{wf_name}] is not registered in the workflow registry."
                    )

        return len(violations) == 0, violations

    def audit_permissions(self, required_permissions: List[str]) -> tuple[bool, List[str]]:
        """Audits requested permissions against security policies and forbidden escalations."""
        violations: List[str] = []

        for perm in required_permissions:
            perm_lower = perm.lower().strip()
            if perm_lower in FORBIDDEN_SKILL_PERMISSIONS:
                violations.append(
                    f"Forbidden privilege escalation permission requested: [{perm}]."
                )
            elif perm_lower not in self.allowed_permissions:
                violations.append(
                    f"Permission [{perm}] is not allowed under current skill host security policy."
                )

        return len(violations) == 0, violations


__all__ = ["SkillValidator", "ALLOWED_SKILL_PERMISSIONS", "FORBIDDEN_SKILL_PERMISSIONS"]
