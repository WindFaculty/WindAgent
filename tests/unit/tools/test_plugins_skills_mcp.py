"""
Unit Tests for WindAgent Plugins, Skills, and MCP Client Adapter (Phase 7):
- PluginManifest static validation & PluginLoader allowlist enforcement
- SkillManifest & SkillManager lazy loading, token budget, and activation rule matching
- MCPClientPort connection lifecycle, tool registration, and disconnect recovery
- MCPToolAdapter PermissionEngine enforcement & fault isolation
"""

import pytest
from windagent_core.domain.types import SessionId, ToolCallId
from windagent_core.domain.models import ToolInvocation
from windagent_core.errors.exceptions import (
    ConflictError, NotFoundError, PermissionDeniedError, ValidationError
)
from windagent_core.security.types import Principal, Permission
from windagent_tools import (
    PluginManifest, PluginLoader,
    SkillManifest, SkillManager,
    MCPClientPort, MCPServerConfig, MCPTransportType, MCPToolInfo,
    MCPToolAdapter, register_mcp_server_tools,
    ToolRegistry, PermissionEngine, ToolExecutionContext, ToolRiskLevel
)


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

    # Invalid ID pattern
    with pytest.raises(ValidationError, match="Invalid plugin ID"):
        PluginManifest(id="Invalid ID", name="Bad").validate()

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


def test_skill_manifest_manager_and_rule_matching():
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

    # Fault isolation check: Disconnecting MCP server causes graceful ToolResult error or ProviderError without crashing app
    await client.disconnect()
    res_disconnected = await tool.execute(inv, ctx_approved)
    assert not res_disconnected.success
    assert "disconnected" in res_disconnected.error.lower()
