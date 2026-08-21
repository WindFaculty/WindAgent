"""Explicit tools infrastructure factory (Architecture V3 Phase B hardening).

This module is the SINGLE allowlisted construction point for concrete tool
adapters inside the tools package:

    composition root / factory  ->  concrete adapter  ->  core port

Tool modules that lazily build a default adapter (browser client factories,
workspace checkpointing, MCP tool registration, guarded production-engine
registration) construct it through these creators instead of hard-instantiating
adapter classes inline.

Creator functions import their adapter classes lazily on purpose: the tools
package ``__init__`` files re-export several creators, so eager imports here
would make every factory load pull the whole tool tree (and risk import
cycles). A factory that imports at call time keeps one auditable construction
point without coupling module load order.
"""

from __future__ import annotations

from typing import Any, Optional


def create_agent_browser_client(
    config: Any,
    *,
    process: Optional[Any] = None,
) -> Any:
    """Build the durable agent-browser client for a browser tool session."""
    from windagent_tools.browser.agent_browser import AgentBrowserClient

    if process is not None:
        return AgentBrowserClient(config, process=process)
    return AgentBrowserClient(config)


def create_browser_state_manager(workspace_root: str) -> Any:
    """BrowserStateManager with env-based retention policy."""
    from windagent_tools.browser.state_manager import (
        BrowserStateManager,
        BrowserStateRetentionPolicy,
    )

    return BrowserStateManager(workspace_root, BrowserStateRetentionPolicy.from_env())


def create_workspace_checkpoint_manager(workspace: Any, store_root: Optional[Any] = None) -> Any:
    """CheckpointManager over a tutorial workspace (code_video pipeline)."""
    from windagent_tools.code_video.workspace.checkpoints import CheckpointManager

    if store_root is None:
        return CheckpointManager(workspace)
    return CheckpointManager(workspace, store_root)


def create_mcp_tool_adapter(
    *,
    client: Any,
    tool_info: Any,
    permission_engine: Any,
    is_trusted_server: bool = True,
) -> Any:
    """Wrap one discovered MCP server tool as a registry tool adapter."""
    from windagent_tools.mcp.adapter import MCPToolAdapter

    return MCPToolAdapter(
        client=client,
        tool_info=tool_info,
        permission_engine=permission_engine,
        is_trusted_server=is_trusted_server,
    )


def create_blender_engine_adapter(
    *,
    artifact_root: str,
    state_dir: str,
    executable_path: Optional[str] = None,
    addon_manifest: Optional[Any] = None,
    **kwargs: Any,
) -> Any:
    """Guarded production-engine registration factory.

    Moved from ``production_engines/blender/adapter.py`` so adapter
    construction has one auditable location per package.
    """
    from windagent_tools.production_engines.blender.adapter import (
        BlenderEngineAdapter,
        BlenderEngineConfig,
    )

    config = BlenderEngineConfig(
        artifact_root=artifact_root,
        state_dir=state_dir,
        executable_path=executable_path,
        addon_manifest=addon_manifest,
        **kwargs,
    )
    return BlenderEngineAdapter(config=config)


__all__ = [
    "create_agent_browser_client",
    "create_blender_engine_adapter",
    "create_browser_state_manager",
    "create_mcp_tool_adapter",
    "create_workspace_checkpoint_manager",
    "create_state_manager",
]


# Backward-compatible alias: the browser state-manager creator was originally
# public as ``create_state_manager``; existing consumers keep working.
create_state_manager = create_browser_state_manager
