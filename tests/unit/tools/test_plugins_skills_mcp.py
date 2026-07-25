"""
Unit Tests for WindAgent Plugins, Skills, and MCP Client Adapter (Phase 7 + Phase 20):
- PluginManifest static validation & PluginLoader allowlist enforcement
- Plugin install, uninstall, update, quarantine lifecycle
- Plugin dependency resolution and namespace collision detection
- Plugin hot reload (development mode)
- SkillManifest & SkillManager lazy loading, token budget, and activation rule matching
- Skill install, uninstall, update lifecycle with tool/workflow dependency validation
- Skill namespace collision detection
- MCPClientPort connection lifecycle, tool registration, and disconnect recovery
- MCPToolAdapter PermissionEngine enforcement & fault isolation
"""

import os
import json
import tempfile
import shutil
import pytest
from windagent_core.domain.types import SessionId, ToolCallId
from windagent_core.domain.models import ToolInvocation
from windagent_core.errors.exceptions import (
    ConflictError, PermissionDeniedError, ValidationError, NotFoundError
)
from windagent_tools import (
    PluginManifest, PluginLoader,
    SkillManifest, SkillManager,
    MCPClientPort, MCPServerConfig, MCPTransportType, MCPToolInfo,
    register_mcp_server_tools,
    ToolRegistry, PermissionEngine, ToolExecutionContext, ToolRiskLevel
)
from windagent_tools.plugins.manifest import PluginDependency, MANIFEST_SCHEMA_VERSION as PLUGIN_SCHEMA_VERSION
from windagent_tools.skills.manifest import MANIFEST_SCHEMA_VERSION as SKILL_SCHEMA_VERSION


# ====================================================================
# Plugins — Manifest & Basic Loader
# ====================================================================

def test_plugin_manifest_validation_and_loader():
    # Valid manifest
    manifest = PluginManifest(
        id="code_formatter",
        name="Code Formatter Plugin",
        version="1.2.0",
        entrypoint="formatter:PluginClass",
        signature_hash="sha256_hash_123",
    )
    manifest.validate()

    # Verify schema version field
    assert manifest.schema_version == PLUGIN_SCHEMA_VERSION
    assert manifest.windagent_version == ">=0.3.0"

    # Invalid ID pattern
    with pytest.raises(ValidationError, match="Invalid plugin ID"):
        PluginManifest(id="Invalid ID", name="Bad").validate()

    # Empty name
    with pytest.raises(ValidationError, match="name cannot be empty"):
        PluginManifest(id="valid_id", name="").validate()

    # Invalid entrypoint (no colon)
    with pytest.raises(ValidationError, match="entrypoint"):
        PluginManifest(id="valid_id", name="Test", entrypoint="invalid").validate()

    # Plugin loader disabled by default
    loader = PluginLoader(allowlist={"code_formatter"}, enforce_allowlist=True)
    loader.register_manifest(manifest)
    assert not loader.is_enabled("code_formatter")

    # Duplicate registration error
    with pytest.raises(ConflictError, match="already registered"):
        loader.register_manifest(manifest)

    # Enable allowed plugin with hash verification
    loader.enable_plugin("code_formatter", expected_hash="sha256_hash_123")
    assert loader.is_enabled("code_formatter")

    # Disallowed plugin attempt
    bad_manifest = PluginManifest(id="untrusted_plugin", name="Untrusted")
    loader.register_manifest(bad_manifest)
    with pytest.raises(PermissionDeniedError, match="not in the system allowlist"):
        loader.enable_plugin("untrusted_plugin")


# ====================================================================
# Plugins — Manifest with Dependencies
# ====================================================================

def test_plugin_manifest_with_dependencies():
    dep1 = PluginDependency(plugin_id="base_utils", version=">=1.0.0")
    dep2 = PluginDependency(plugin_id="optional_helper", version="*", optional=True)

    manifest = PluginManifest(
        id="advanced_plugin",
        name="Advanced Plugin",
        version="2.0.0",
        entrypoint="advanced:Plugin",
        capabilities=["advanced_analysis"],
        required_permissions=["workspace_write", "external_network"],
        required_tools=["git_tool", "exec_shell"],
        required_workflows=["code_review"],
        dependencies=[dep1, dep2],
        compatibility=">=0.4.0",
    )

    manifest.validate()
    assert len(manifest.dependencies) == 2
    assert manifest.dependencies[0].plugin_id == "base_utils"
    assert manifest.dependencies[0].optional is False
    assert manifest.dependencies[1].optional is True

    # Round-trip to_dict / from_dict
    data = manifest.to_dict()
    restored = PluginManifest.from_dict(data)
    assert restored.id == "advanced_plugin"
    assert restored.version == "2.0.0"
    assert len(restored.dependencies) == 2
    assert restored.required_workflows == ["code_review"]
    assert restored.capabilities == ["advanced_analysis"]


def test_plugin_manifest_from_dict():
    data = {
        "id": "from_dict_plugin",
        "name": "From Dict",
        "version": "0.5.0",
        "entrypoint": "module:Class",
        "capabilities": ["test"],
        "dependencies": [
            {"plugin_id": "dep1", "version": ">=1.0", "optional": False},
            "string_dep",
        ],
    }
    manifest = PluginManifest.from_dict(data)
    assert manifest.id == "from_dict_plugin"
    assert len(manifest.dependencies) == 2
    assert manifest.dependencies[0].plugin_id == "dep1"
    assert manifest.dependencies[1].plugin_id == "string_dep"


# ====================================================================
# Plugins — Install / Uninstall / Update Lifecycle
# ====================================================================

def test_plugin_install_and_uninstall(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    manifest = PluginManifest(
        id="test_install",
        name="Test Install Plugin",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    # Install
    install_path = loader.install_plugin(manifest)
    assert os.path.exists(install_path)
    assert os.path.exists(os.path.join(plugins_root, "manifests", "test_install.json"))
    assert loader.is_enabled("test_install") is False

    # Idempotent reinstall same version
    install_path2 = loader.install_plugin(manifest)
    assert install_path == install_path2

    # Enable after install
    loader.add_to_allowlist("test_install")
    loader.enable_plugin("test_install")
    assert loader.is_enabled("test_install")

    # Uninstall
    result = loader.uninstall_plugin("test_install")
    assert result is True
    assert not os.path.exists(install_path)
    assert not os.path.exists(os.path.join(plugins_root, "manifests", "test_install.json"))
    assert not loader.is_enabled("test_install")

    # Idempotent uninstall
    result2 = loader.uninstall_plugin("test_install")
    assert result2 is False  # Already gone, returns False but no error


def test_plugin_update(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    v1 = PluginManifest(id="updatable", name="Updatable", version="1.0.0", entrypoint="mod:Class")
    loader.install_plugin(v1)
    loader.add_to_allowlist("updatable")
    loader.enable_plugin("updatable")
    assert loader.is_enabled("updatable")

    v2 = PluginManifest(id="updatable", name="Updatable v2", version="2.0.0", entrypoint="mod:NewClass")
    install_path = loader.update_plugin(v2)
    assert "2.0.0" in v2.version

    # Enabled status preserved
    assert loader.is_enabled("updatable")


def test_plugin_install_with_custom_source(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins")
    source_dir = os.path.join(str(tmp_path), "source_plugin")
    os.makedirs(source_dir)
    with open(os.path.join(source_dir, "custom.py"), "w") as f:
        f.write("# custom plugin code")

    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)
    manifest = PluginManifest(id="source_install", name="Source Install", version="1.0.0", entrypoint="custom:Class")
    install_path = loader.install_plugin(manifest, source_path=source_dir)

    assert os.path.exists(os.path.join(install_path, "custom.py"))


# ====================================================================
# Plugins — Quarantine
# ====================================================================

def test_plugin_quarantine_and_release(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    manifest = PluginManifest(id="buggy", name="Buggy Plugin", version="1.0.0", entrypoint="buggy:Plugin")
    loader.install_plugin(manifest)
    loader.add_to_allowlist("buggy")
    loader.enable_plugin("buggy")
    assert loader.is_enabled("buggy")

    # Quarantine
    loader.quarantine_plugin("buggy", reason="crashed on startup")
    assert not loader.is_enabled("buggy")
    assert loader.is_quarantined("buggy")
    assert os.path.exists(os.path.join(plugins_root, "quarantine", "buggy"))
    assert os.path.exists(os.path.join(plugins_root, "quarantine", "buggy", ".quarantine.json"))

    # List quarantined
    quarantined = loader.list_quarantined()
    assert any(q["plugin_id"] == "buggy" for q in quarantined)

    # Cannot enable quarantined plugin
    with pytest.raises(PermissionDeniedError, match="quarantined"):
        loader.enable_plugin("buggy")

    # Release from quarantine
    loader.release_from_quarantine("buggy")
    assert not loader.is_quarantined("buggy")
    assert os.path.exists(os.path.join(plugins_root, "installed", "buggy"))

    # Still disabled by default
    assert not loader.is_enabled("buggy")


# ====================================================================
# Plugins — Namespace Collision Detection
# ====================================================================

def test_plugin_namespace_collision_with_tools(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins_namespace")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    # Register existing tool names
    loader.register_tool_names({"read_file", "write_file", "git_tool"})

    # Plugin ID collides with a tool name
    with pytest.raises(ConflictError, match="collides with a registered tool"):
        manifest = PluginManifest(id="read_file", name="Collision", entrypoint="mod:Class")
        loader.register_manifest(manifest)


def test_plugin_namespace_collision_with_workflows(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins_ns_wf")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    loader.register_workflow_names({"code_review", "bugfix"})

    with pytest.raises(ConflictError, match="collides with a registered workflow"):
        manifest = PluginManifest(id="code_review", name="Collision", entrypoint="mod:Class")
        loader.register_manifest(manifest)


# ====================================================================
# Plugins — Dependency Resolution
# ====================================================================

def test_plugin_dependency_resolution(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins_deps")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    # Install base plugin first
    base = PluginManifest(id="base_utils", name="Base Utils", version="1.0.0", entrypoint="base:Plugin")
    loader.install_plugin(base)

    # Install dependent plugin
    dep = PluginDependency(plugin_id="base_utils", version=">=1.0.0")
    dependent = PluginManifest(
        id="dependent_plugin",
        name="Dependent Plugin",
        version="1.0.0",
        entrypoint="dependent:Plugin",
        dependencies=[dep],
    )
    install_path = loader.install_plugin(dependent)
    assert os.path.exists(install_path)

    # Install plugin with missing dependency should fail
    missing_dep = PluginDependency(plugin_id="non_existent", version=">=1.0.0")
    broken = PluginManifest(
        id="broken_plugin",
        name="Broken Plugin",
        version="1.0.0",
        entrypoint="broken:Plugin",
        dependencies=[missing_dep],
    )
    with pytest.raises(ValidationError, match="requires dependency"):
        loader.install_plugin(broken)


# ====================================================================
# Plugins — Hot Reload (development mode)
# ====================================================================

def test_plugin_hot_reload(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins_hot")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False, dev_hot_reload=True)

    manifest = PluginManifest(id="hot_reloadable", name="Hot Reload", version="1.0.0", entrypoint="mod:Class")
    loader.install_plugin(manifest)

    # Modify the persisted manifest
    manifest_path = os.path.join(plugins_root, "manifests", "hot_reloadable.json")
    with open(manifest_path, "r") as f:
        data = json.load(f)
    data["version"] = "1.1.0"
    with open(manifest_path, "w") as f:
        json.dump(data, f)

    # Hot reload
    loader.hot_reload_plugin("hot_reloadable")
    updated = loader.get_plugin("hot_reloadable")
    assert updated.version == "1.1.0"

    # Hot reload disabled in production mode
    loader_prod = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False, dev_hot_reload=False)
    with pytest.raises(PermissionDeniedError, match="development mode"):
        loader_prod.hot_reload_plugin("hot_reloadable")


# ====================================================================
# Plugins — List and Registry
# ====================================================================

def test_plugin_list_and_registry(tmp_path):
    plugins_root = os.path.join(str(tmp_path), "plugins_list")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    m1 = PluginManifest(id="plugin_a", name="Plugin A", version="1.0.0", entrypoint="a:Plugin")
    m2 = PluginManifest(id="plugin_b", name="Plugin B", version="2.0.0", entrypoint="b:Plugin")
    loader.install_plugin(m1)
    loader.install_plugin(m2)

    plugins = loader.list_plugins()
    assert len(plugins) == 2
    assert all(p["enabled"] is False for p in plugins)

    loader.add_to_allowlist("plugin_a")
    loader.enable_plugin("plugin_a")
    enabled = loader.list_enabled_plugins()
    assert len(enabled) == 1
    assert enabled[0].id == "plugin_a"

    # Registry index
    index = loader.load_registry_index()
    assert len(index["plugins"]) == 2


# ====================================================================
# Skills — Manifest & Basic Manager
# ====================================================================

def test_skill_manifest_validation():
    manifest = SkillManifest(
        id="python_refactor",
        description="Refactors Python functions and type annotations",
        activation_rules=["refactor python", "python type hints"],
        token_budget=1500,
        prompt_template="Refactor the following Python code for {target_func}: {code}",
    )
    manifest.validate()

    # Verify schema version field
    assert manifest.schema_version == SKILL_SCHEMA_VERSION
    assert manifest.windagent_version == ">=0.3.0"

    # Invalid ID
    with pytest.raises(ValidationError, match="Invalid skill ID"):
        SkillManifest(id="Bad ID", description="test").validate()

    # Empty description
    with pytest.raises(ValidationError, match="description cannot be empty"):
        SkillManifest(id="valid_id", description="").validate()

    # Zero token budget
    with pytest.raises(ValidationError, match="token_budget"):
        SkillManifest(id="valid_id", description="test", token_budget=0).validate()

    # Round-trip to_dict / from_dict
    data = manifest.to_dict()
    restored = SkillManifest.from_dict(data)
    assert restored.id == "python_refactor"
    assert restored.token_budget == 1500


def test_skill_manifest_with_workflows():
    manifest = SkillManifest(
        id="full_skill",
        description="Skill with workflows",
        version="2.0.0",
        required_tools=["read_file", "write_file", "git_tool"],
        required_workflows=["code_review", "bugfix"],
        token_budget=6000,
    )
    manifest.validate()
    assert len(manifest.required_workflows) == 2
    assert "code_review" in manifest.required_workflows
    assert manifest.schema_version == SKILL_SCHEMA_VERSION


# ====================================================================
# Skills — Manager: Registration, Rule Matching, Prompt Rendering
# ====================================================================

def test_skill_manager_registration_and_matching():
    manager = SkillManager()

    skill1 = SkillManifest(
        id="python_refactor",
        description="Refactors Python functions and type annotations",
        activation_rules=["refactor python", "python type hints"],
        token_budget=1500,
        prompt_template="Refactor the following Python code for {target_func}: {code}",
    )
    manager.register_skill(skill1)

    # Duplicate registration
    with pytest.raises(ConflictError, match="already registered"):
        manager.register_skill(skill1)

    # Lazy loading check
    fetched = manager.get_skill("python_refactor")
    assert fetched.token_budget == 1500

    # Rule matching
    matched = manager.find_matching_skills("Please refactor Python code in service.py")
    assert len(matched) == 1
    assert matched[0].id == "python_refactor"

    # Prompt rendering
    prompt = manager.render_skill_prompt("python_refactor", {"target_func": "process_data", "code": "def foo(): pass"})
    assert "process_data" in prompt
    assert "def foo(): pass" in prompt


# ====================================================================
# Skills — Tool/Workflow Dependency Validation
# ====================================================================

def test_skill_requires_known_tools():
    manager = SkillManager()
    # Register known tools
    manager.register_tool_names({"read_file", "write_file", "exec_shell"})

    # Skill requiring a registered tool passes
    valid = SkillManifest(
        id="valid_skill",
        description="Valid skill",
        required_tools=["read_file", "exec_shell"],
    )
    manager.register_skill(valid)

    # Skill requiring an unregistered tool fails
    invalid = SkillManifest(
        id="invalid_skill",
        description="Invalid skill",
        required_tools=["nonexistent_tool"],
    )
    with pytest.raises(ValidationError, match="requires tool"):
        manager.register_skill(invalid)


def test_skill_requires_known_workflows():
    manager = SkillManager()
    manager.register_workflow_names({"code_review", "bugfix"})

    valid = SkillManifest(
        id="wf_skill",
        description="Workflow skill",
        required_workflows=["code_review"],
    )
    manager.register_skill(valid)

    invalid = SkillManifest(
        id="bad_wf_skill",
        description="Bad workflow skill",
        required_workflows=["nonexistent_workflow"],
    )
    with pytest.raises(ValidationError, match="requires workflow"):
        manager.register_skill(invalid)


# ====================================================================
# Skills — Namespace Collision Detection
# ====================================================================

def test_skill_namespace_collision_with_tools():
    manager = SkillManager()
    manager.register_tool_names({"read_file", "git_tool"})

    with pytest.raises(ConflictError, match="collides with a registered tool"):
        manifest = SkillManifest(id="read_file", description="Collision")
        manager.register_skill(manifest)


def test_skill_namespace_collision_with_workflows():
    manager = SkillManager()
    manager.register_workflow_names({"code_review"})

    with pytest.raises(ConflictError, match="collides with a registered workflow"):
        manifest = SkillManifest(id="code_review", description="Collision")
        manager.register_skill(manifest)


# ====================================================================
# Skills — Install / Uninstall / Update Lifecycle
# ====================================================================

def test_skill_install_and_uninstall(tmp_path):
    skills_root = os.path.join(str(tmp_path), "skills")
    manager = SkillManager(skills_root=skills_root)

    # Register some tools first so deps pass
    manager.register_tool_names({"read_file", "write_file"})

    manifest = SkillManifest(
        id="test_skill",
        description="Test Skill",
        version="1.0.0",
        required_tools=["read_file"],
        prompt_template="Test template for {subject}",
    )

    # Install
    install_path = manager.install_skill(manifest)
    assert os.path.exists(install_path)
    assert os.path.exists(os.path.join(skills_root, "manifests", "test_skill.json"))

    # Idempotent reinstall
    path2 = manager.install_skill(manifest)
    assert install_path == path2

    # Uninstall
    assert manager.uninstall_skill("test_skill") is True
    assert not os.path.exists(install_path)
    assert not os.path.exists(os.path.join(skills_root, "manifests", "test_skill.json"))

    # Idempotent uninstall
    assert manager.uninstall_skill("test_skill") is False


def test_skill_update(tmp_path):
    skills_root = os.path.join(str(tmp_path), "skills_update")
    manager = SkillManager(skills_root=skills_root)
    manager.register_tool_names({"read_file"})

    v1 = SkillManifest(id="updatable_skill", description="v1", version="1.0.0", required_tools=["read_file"])
    manager.install_skill(v1)

    v2 = SkillManifest(id="updatable_skill", description="v2", version="2.0.0", required_tools=["read_file"])
    manager.update_skill(v2)
    assert manager.get_skill("updatable_skill").version == "2.0.0"


def test_skill_install_with_source(tmp_path):
    skills_root = os.path.join(str(tmp_path), "skills_src")
    source_dir = os.path.join(str(tmp_path), "source_skill")
    os.makedirs(source_dir)
    with open(os.path.join(source_dir, "template.txt"), "w") as f:
        f.write("Custom skill template")

    manager = SkillManager(skills_root=skills_root)
    manager.register_tool_names({"read_file"})
    manifest = SkillManifest(id="src_skill", description="Source skill", version="1.0.0", required_tools=["read_file"])

    install_path = manager.install_skill(manifest, source_path=source_dir)
    assert os.path.exists(os.path.join(install_path, "template.txt"))


# ====================================================================
# Skills — Hot Reload (development mode)
# ====================================================================

def test_skill_hot_reload(tmp_path):
    skills_root = os.path.join(str(tmp_path), "skills_hot")
    manager = SkillManager(skills_root=skills_root, dev_hot_reload=True)
    manager.register_tool_names({"read_file"})

    manifest = SkillManifest(id="hot_skill", description="Hot skill", version="1.0.0", required_tools=["read_file"])
    manager.install_skill(manifest)

    # Modify persisted manifest
    manifest_path = os.path.join(skills_root, "manifests", "hot_skill.json")
    with open(manifest_path, "r") as f:
        data = json.load(f)
    data["version"] = "1.5.0"
    data["description"] = "Updated description"
    with open(manifest_path, "w") as f:
        json.dump(data, f)

    # Hot reload
    manager.hot_reload_skill("hot_skill")
    updated = manager.get_skill("hot_skill")
    assert updated.version == "1.5.0"
    assert updated.description == "Updated description"

    # Production mode restriction
    manager_prod = SkillManager(skills_root=skills_root, dev_hot_reload=False)
    with pytest.raises(PermissionDeniedError, match="development mode"):
        manager_prod.hot_reload_skill("hot_skill")


# ====================================================================
# Skills — Catalog Index
# ====================================================================

def test_skill_catalog_index(tmp_path):
    skills_root = os.path.join(str(tmp_path), "skills_catalog")
    manager = SkillManager(skills_root=skills_root)
    manager.register_tool_names({"read_file"})

    m1 = SkillManifest(id="skill_a", description="A", version="1.0.0", required_tools=["read_file"])
    m2 = SkillManifest(id="skill_b", description="B", version="2.0.0", required_tools=["read_file"])
    manager.install_skill(m1)
    manager.install_skill(m2)

    index = manager.load_catalog_index()
    assert len(index["skills"]) == 2

    manager.uninstall_skill("skill_a")
    index2 = manager.load_catalog_index()
    assert len(index2["skills"]) == 1
    assert index2["skills"][0]["id"] == "skill_b"


# ====================================================================
# Skills — PermissionEngine Integration (Plugin cannot bypass)
# ====================================================================

def test_plugin_cannot_bypass_permission_engine(tmp_path):
    """Gate: Plugin cannot bypass PermissionEngine.
    Verify that PluginLoader still enforces security through PermissionEngine
    for tool execution even after plugin install.
    """
    plugins_root = os.path.join(str(tmp_path), "plugins_perm")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=True)

    # Even with exclude from allowlist, plugin cannot access destructive actions
    manifest = PluginManifest(
        id="safe_plugin",
        name="Safe",
        version="1.0.0",
        entrypoint="safe:Plugin",
        required_permissions=["read_only"],
    )
    loader.install_plugin(manifest)

    # PermissionEngine denies actions outside declared permissions
    engine = PermissionEngine(enforce_strict=True)

    from windagent_core.security.types import PermissionEvaluationRequest, RiskLevel, Principal

    # Plugin tries to do a destructive action - should be denied
    req = PermissionEvaluationRequest(
        principal=Principal(id="plugin_safe_plugin", roles=["plugin"], permissions=["read_only"]),
        action="format_disk",
        target="/",
        risk_level=RiskLevel.CRITICAL,
        context={"is_destructive": True, "user_approved": False},
    )
    decision = engine.evaluate_request(req)
    assert decision.outcome == "REQUIRE_APPROVAL"  # Not auto-approved
    assert decision.is_allowed is False


# ====================================================================
# Skills — Cannot Call Tool Outside Manifest
# ====================================================================

def test_skill_cannot_call_unregistered_tool():
    """Gate: Skill cannot call tool outside manifest.
    SkillManager.validate_dependencies catches unregistered tool requirements.
    """
    manager = SkillManager()
    manager.register_tool_names({"read_file"})  # Only register read_file

    # Skill that requires write_file should work (it's registered)
    valid = SkillManifest(id="valid_skill2", description="Valid", required_tools=["read_file"])
    manager.register_skill(valid)

    # Skill requiring unregistered tool is rejected
    invalid = SkillManifest(id="bad_skill2", description="Bad", required_tools=["unregistered_tool"])
    with pytest.raises(ValidationError, match="requires tool"):
        manager.register_skill(invalid)


# ====================================================================
# Skills — Reinstall same version idempotent
# ====================================================================

def test_reinstall_idempotent_plugin(tmp_path):
    """Gate: Reinstall same version is idempotent for plugins."""
    plugins_root = os.path.join(str(tmp_path), "plugins_idem")
    loader = PluginLoader(plugins_root=plugins_root, enforce_allowlist=False)

    manifest = PluginManifest(id="idempotent", name="Idempotent", version="1.0.0", entrypoint="mod:Class")
    path1 = loader.install_plugin(manifest)
    path2 = loader.install_plugin(manifest)
    assert path1 == path2


def test_reinstall_idempotent_skill(tmp_path):
    """Gate: Reinstall same version is idempotent for skills."""
    skills_root = os.path.join(str(tmp_path), "skills_idem")
    manager = SkillManager(skills_root=skills_root)
    manager.register_tool_names({"read_file"})

    manifest = SkillManifest(id="idem_skill", description="Idempotent skill", version="1.0.0", required_tools=["read_file"])
    path1 = manager.install_skill(manifest)
    path2 = manager.install_skill(manifest)
    assert path1 == path2


# ====================================================================
# MCP — Lifecycle & Permission
# ====================================================================

@pytest.mark.asyncio
async def test_mcp_client_port_lifecycle_and_reconnect():
    config = MCPServerConfig(
        server_id="filesystem_mcp",
        transport_type=MCPTransportType.IN_MEMORY,
        timeout_seconds=5.0,
    )
    client = MCPClientPort(config)
    assert not client.is_connected

    await client.connect()
    assert client.is_connected

    client.register_mock_tool(MCPToolInfo(name="list_dir", description="Lists directory contents"))
    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "list_dir"

    # Reconnect test
    await client.reconnect()
    assert client.is_connected

    await client.disconnect()
    assert not client.is_connected


@pytest.mark.asyncio
async def test_mcp_tool_adapter_permission_enforcement_and_fault_isolation(tmp_path):
    config = MCPServerConfig(server_id="github_mcp", transport_type=MCPTransportType.IN_MEMORY)
    client = MCPClientPort(config)
    await client.connect()
    client.register_mock_tool(MCPToolInfo(name="create_issue", description="Creates GitHub issue"))

    registry = ToolRegistry()
    permission_engine = PermissionEngine(enforce_strict=True)

    registered_names = await register_mcp_server_tools(client, registry, permission_engine)
    assert len(registered_names) == 1
    mcp_tool_name = registered_names[0]
    assert mcp_tool_name == "mcp_github_mcp_create_issue"

    tool = registry.get_tool(mcp_tool_name)
    assert tool.definition.risk_level == ToolRiskLevel.EXTERNAL_NETWORK

    sid = SessionId.generate()
    inv = ToolInvocation(id=ToolCallId.generate(), tool_name=mcp_tool_name, params={"title": "Bug report"})

    # Unapproved call fails PermissionEngine evaluation
    ctx_unapproved = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=False)
    with pytest.raises(PermissionDeniedError, match="requires explicit user approval"):
        await tool.execute(inv, ctx_unapproved)

    # Approved call passes PermissionEngine & executes via MCP client
    ctx_approved = ToolExecutionContext(workspace_root=str(tmp_path), session_id=sid, user_approved=True)
    res = await tool.execute(inv, ctx_approved)
    assert res.success
    assert res.data["tool_name"] == "create_issue"

    # Fault isolation check: Disconnecting MCP server causes graceful ToolResult error without crashing app
    await client.disconnect()
    res_disconnected = await tool.execute(inv, ctx_approved)
    assert not res_disconnected.success
    assert "disconnected" in res_disconnected.error.lower()
