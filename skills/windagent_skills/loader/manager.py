"""
Skill Manager for WindAgent Tool Platform (Phase 20).
Handles skill registration, lazy loading, rule matching, token budget accounting,
prompt formatting, and durable lifecycle management (install, update, uninstall).
Enforces tool and workflow dependency validation so skills cannot call tools/workflows
outside their manifest declarations.
"""

from __future__ import annotations
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from windagent_core.errors.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from windagent_skills.manifest.manifest import SkillManifest

logger = logging.getLogger("windagent.skills")

# Default content root paths
DEFAULT_SKILLS_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "skills")
INSTALLED_DIR = os.path.join(DEFAULT_SKILLS_ROOT, "installed")
MANIFESTS_DIR = os.path.join(DEFAULT_SKILLS_ROOT, "manifests")
CATALOG_DIR = os.path.join(DEFAULT_SKILLS_ROOT, "catalog")


class SkillManager:
    def __init__(
        self,
        default_max_token_budget: int = 8000,
        skills_root: Optional[str] = None,
        dev_hot_reload: bool = False,
    ):
        self.default_max_token_budget = default_max_token_budget
        self.skills_root = skills_root or DEFAULT_SKILLS_ROOT
        self.installed_dir = os.path.join(self.skills_root, "installed")
        self.manifests_dir = os.path.join(self.skills_root, "manifests")
        self.catalog_dir = os.path.join(self.skills_root, "catalog")
        self.dev_hot_reload = dev_hot_reload
        self._skills: Dict[str, SkillManifest] = {}
        self._loaded_templates: Dict[str, str] = {}
        # Track known tool and workflow names for dependency validation
        self._registered_tool_names: Set[str] = set()
        self._registered_workflow_names: Set[str] = set()

        # Ensure content directories exist
        for d in [self.installed_dir, self.manifests_dir, self.catalog_dir]:
            os.makedirs(d, exist_ok=True)

    # ------------------------------------------------------------------
    # Tool / Workflow name registration (for dependency validation)
    # ------------------------------------------------------------------

    def register_tool_names(self, names: Set[str]) -> None:
        """Registers known tool names for dependency validation.
        Skills can only require tools that exist in the registry.
        """
        self._registered_tool_names.update(names)

    def register_workflow_names(self, names: Set[str]) -> None:
        """Registers known workflow names for dependency validation."""
        self._registered_workflow_names.update(names)

    # ------------------------------------------------------------------
    # In-memory registration
    # ------------------------------------------------------------------

    def register_skill(self, manifest: SkillManifest) -> None:
        """Registers a skill manifest lazily."""
        manifest.validate()

        # Validate that required tools are registered
        for tool_name in manifest.required_tools:
            if tool_name not in self._registered_tool_names:
                raise ValidationError(
                    f"Skill [{manifest.id}] requires tool [{tool_name}] which is not "
                    f"registered in the tool registry. Skills cannot call tools outside their manifest."
                )

        # Validate that required workflows are registered
        for wf_name in manifest.required_workflows:
            if wf_name not in self._registered_workflow_names:
                raise ValidationError(
                    f"Skill [{manifest.id}] requires workflow [{wf_name}] which is not "
                    f"registered in the workflow registry."
                )

        if manifest.id in self._skills:
            raise ConflictError(f"Skill with ID [{manifest.id}] is already registered.")

        # Namespace collision: skill ID must not collide with tools or workflows
        if manifest.id in self._registered_tool_names:
            raise ConflictError(
                f"Skill ID [{manifest.id}] collides with a registered tool name. "
                f"Skill namespace isolation requires unique names across tools and skills."
            )
        if manifest.id in self._registered_workflow_names:
            raise ConflictError(
                f"Skill ID [{manifest.id}] collides with a registered workflow name. "
                f"Skill namespace isolation requires unique names across workflows and skills."
            )

        self._skills[manifest.id] = manifest
        logger.info(f"Registered skill [{manifest.id}] (token budget: {manifest.token_budget})")

    def unregister_skill(self, skill_id: str) -> None:
        """Removes a skill from memory."""
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._loaded_templates.pop(skill_id, None)
            logger.info(f"Unregistered skill [{skill_id}]")

    # ------------------------------------------------------------------
    # Content root persistence (install / uninstall / update)
    # ------------------------------------------------------------------

    def install_skill(self, manifest: SkillManifest, source_path: Optional[str] = None) -> str:
        """Installs a skill to the content root.
        - Validates the manifest with dependency checking
        - Copies skill files to installed/ directory
        - Persists manifest to manifests/ directory
        - Is idempotent for the same version
        Returns the install path.
        """
        manifest.validate()

        # Check if already installed at same version (idempotent)
        installed_manifest_path = os.path.join(self.manifests_dir, f"{manifest.id}.json")
        if os.path.exists(installed_manifest_path):
            with open(installed_manifest_path, "r") as f:
                existing = json.load(f)
            if existing.get("version") == manifest.version:
                logger.info(f"Skill [{manifest.id}] v{manifest.version} already installed. Skipping (idempotent).")
                return os.path.join(self.installed_dir, manifest.id)

        # Register skill in memory (will validate tool/workflow deps)
        if manifest.id in self._skills:
            if self._skills[manifest.id].version != manifest.version:
                logger.info(f"Upgrading skill [{manifest.id}] from v{self._skills[manifest.id].version} to v{manifest.version}")
                self.unregister_skill(manifest.id)
            else:
                raise ConflictError(f"Skill [{manifest.id}] v{manifest.version} is already registered. Use update_skill to change.")

        self.register_skill(manifest)

        # Create install directory
        install_path = os.path.join(self.installed_dir, manifest.id)
        os.makedirs(install_path, exist_ok=True)

        # Copy skill source files if provided
        if source_path and os.path.isdir(source_path):
            for item in os.listdir(source_path):
                s = os.path.join(source_path, item)
                d = os.path.join(install_path, item)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
                elif os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
            logger.info(f"Copied skill files for [{manifest.id}] from {source_path} to {install_path}")
        else:
            # Create minimal skill stub
            stub_path = os.path.join(install_path, "__init__.py")
            if not os.path.exists(stub_path):
                with open(stub_path, "w") as f:
                    f.write(f'# Skill [{manifest.id}] v{manifest.version}\n')

            # Write prompt template if present
            if manifest.prompt_template:
                template_path = os.path.join(install_path, "prompt.txt")
                if not os.path.exists(template_path):
                    with open(template_path, "w") as f:
                        f.write(manifest.prompt_template)

        # Persist manifest to manifests directory
        with open(installed_manifest_path, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        # Update catalog index
        self._update_catalog_index(manifest)

        logger.info(f"Installed skill [{manifest.id}] v{manifest.version} at {install_path}")
        return install_path

    def uninstall_skill(self, skill_id: str, version: Optional[str] = None) -> bool:
        """Uninstalls a skill from the content root.
        If version is specified, only uninstalls if version matches (safety check).
        Idempotent.
        """
        installed_manifest_path = os.path.join(self.manifests_dir, f"{skill_id}.json")

        if os.path.exists(installed_manifest_path):
            with open(installed_manifest_path, "r") as f:
                existing = json.load(f)
            if version and existing.get("version") != version:
                logger.warning(
                    f"Cannot uninstall skill [{skill_id}]: specified version [{version}] "
                    f"does not match installed version [{existing.get('version')}]."
                )
                return False
        else:
            if skill_id not in self._skills:
                logger.info(f"Skill [{skill_id}] is not installed. Nothing to uninstall.")
                return False

        # Remove installed files
        install_path = os.path.join(self.installed_dir, skill_id)
        if os.path.exists(install_path):
            shutil.rmtree(install_path)

        # Remove manifest file
        if os.path.exists(installed_manifest_path):
            os.remove(installed_manifest_path)

        # Remove from catalog index
        self._remove_from_catalog_index(skill_id)

        # Clean up in-memory state
        self.unregister_skill(skill_id)

        logger.info(f"Uninstalled skill [{skill_id}].")
        return True

    def update_skill(self, manifest: SkillManifest, source_path: Optional[str] = None) -> str:
        """Updates a skill to a new version.
        Validates the manifest, uninstalls the old version, installs the new one.
        """
        self.uninstall_skill(manifest.id)
        install_path = self.install_skill(manifest, source_path)
        logger.info(f"Updated skill [{manifest.id}] to v{manifest.version}")
        return install_path

    # ------------------------------------------------------------------
    # Hot reload (development only)
    # ------------------------------------------------------------------

    def hot_reload_skill(self, skill_id: str) -> bool:
        """Hot-reloads a skill from the installed content root.
        Only available when dev_hot_reload=True.
        """
        if not self.dev_hot_reload:
            raise PermissionDeniedError(
                message="Hot reload is only allowed in development mode.",
                code="WINDAGENT_ERR_DEV_MODE_ONLY",
                details={"skill_id": skill_id},
            )

        manifest_path = os.path.join(self.manifests_dir, f"{skill_id}.json")
        if not os.path.exists(manifest_path):
            raise NotFoundError(f"Cannot hot-reload skill [{skill_id}]: manifest not found at {manifest_path}")

        with open(manifest_path, "r") as f:
            data = json.load(f)

        new_manifest = SkillManifest.from_dict(data)
        self.unregister_skill(skill_id)
        self.register_skill(new_manifest)

        # Clear cached template
        self._loaded_templates.pop(skill_id, None)

        logger.info(f"Hot-reloaded skill [{skill_id}] v{new_manifest.version}")
        return True

    def reload_all(self) -> int:
        """Hot-reloads all installed skills from the manifests content root.
        Only available when dev_hot_reload=True.
        """
        if not os.path.exists(self.manifests_dir):
            return 0

        count = 0
        for filename in os.listdir(self.manifests_dir):
            if filename.endswith(".json"):
                skill_id = filename[:-5]
                try:
                    self.hot_reload_skill(skill_id)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to hot-reload skill [{skill_id}]: {e}")
        logger.info(f"Hot-reloaded {count} skills from manifests content root.")
        return count

    # ------------------------------------------------------------------
    # Lookup & query
    # ------------------------------------------------------------------

    def get_skill(self, skill_id: str) -> SkillManifest:
        if skill_id not in self._skills:
            raise NotFoundError(f"Skill [{skill_id}] is not registered.")
        return self._skills[skill_id]

    def list_skills(self) -> List[SkillManifest]:
        return list(self._skills.values())

    def find_matching_skills(self, task_description: str) -> List[SkillManifest]:
        """Matches registered skills against task description rules."""
        matched: List[SkillManifest] = []
        desc_lower = task_description.lower()

        for skill in self._skills.values():
            if not skill.activation_rules:
                continue
            for rule in skill.activation_rules:
                if rule.lower() in desc_lower:
                    matched.append(skill)
                    break

        return matched

    def render_skill_prompt(self, skill_id: str, context_vars: Optional[Dict[str, Any]] = None) -> str:
        """Lazy loads and renders the skill prompt template with context variables."""
        skill = self.get_skill(skill_id)
        if skill_id not in self._loaded_templates:
            self._loaded_templates[skill_id] = skill.prompt_template

        raw_template = self._loaded_templates[skill_id]
        if not context_vars:
            return raw_template

        try:
            return raw_template.format(**context_vars)
        except KeyError as e:
            logger.warning(f"Missing variable {e} when rendering skill [{skill_id}] template")
            return raw_template

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_catalog_index(self, manifest: SkillManifest) -> None:
        """Persists skill info to the catalog index file."""
        index_path = os.path.join(self.catalog_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                index = json.load(f)
        else:
            index = {"skills": [], "updated_at": ""}

        # Remove existing entry for this skill
        index["skills"] = [s for s in index["skills"] if s.get("id") != manifest.id]

        index["skills"].append({
            "id": manifest.id,
            "version": manifest.version,
            "description": manifest.description,
            "activation_rules": manifest.activation_rules,
            "required_tools": manifest.required_tools,
            "required_workflows": manifest.required_workflows,
            "token_budget": manifest.token_budget,
            "installed_at": datetime.now(timezone.utc).isoformat(),
        })
        index["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

    def _remove_from_catalog_index(self, skill_id: str) -> None:
        """Removes a skill from the catalog index file."""
        index_path = os.path.join(self.catalog_dir, "index.json")
        if not os.path.exists(index_path):
            return

        with open(index_path, "r") as f:
            index = json.load(f)

        index["skills"] = [s for s in index["skills"] if s.get("id") != skill_id]
        index["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

    def load_catalog_index(self) -> Dict[str, Any]:
        """Loads the persisted catalog index."""
        index_path = os.path.join(self.catalog_dir, "index.json")
        if not os.path.exists(index_path):
            return {"skills": [], "updated_at": ""}
        with open(index_path, "r") as f:
            return json.load(f)
