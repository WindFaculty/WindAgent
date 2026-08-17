"""Phase 0/7/11 single durable multi-agent workspace contract gates.

Phase 11 cutover: MultiAgentWorkspace delegates fully to the canonical
@windagent/app AgentWorkspacePage. The page used to own its own store
(useMultiAgent / MultiAgentProvider), manual refresh loops, 2-second Browser
polling and mock browser state — that authority is now owned by
/api/v3/conversations/{id} queries + the realtime stream, per Phase 11.5.
"""

from pathlib import Path

ROOT = Path(__file__).parents[2]
APP_TSX = ROOT / "apps" / "desktop" / "src" / "App.tsx"
MULTI_AGENT_WS = ROOT / "apps" / "desktop" / "src" / "pages" / "MultiAgentWorkspace.tsx"
CANONICAL_WS_DIR = ROOT / "frontend" / "app" / "src" / "features" / "agent-workspace"
CANONICAL_PAGE = CANONICAL_WS_DIR / "pages" / "AgentWorkspacePage.tsx"
CANONICAL_HOOK = CANONICAL_WS_DIR / "hooks" / "useAgentWorkspace.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workspace_mount_is_single_and_canonical():
    """Phase 7 removes the flag and every legacy session-workspace branch."""
    src = _read(APP_TSX)
    assert '<MultiAgentWorkspace conversationId={conversationId} />' in src
    assert src.count("<MultiAgentWorkspace ") == 1
    assert "WORKSPACE_UI" not in src
    assert "VITE_WORKSPACE_UI" not in src
    assert "AgentWorkspacePage" not in src
    assert 'from "./pages/AgentWorkspace"' not in src
    assert not (ROOT / "apps" / "desktop" / "src" / "pages" / "AgentWorkspace.tsx").exists()


def test_workspace_delegates_to_canonical_agent_workspace():
    """Phases 7/11: desktop shell delegates; page owns no manual store authority."""
    workspace = _read(MULTI_AGENT_WS)
    assert "useMultiAgent" not in workspace
    assert "MultiAgentProvider" not in workspace
    assert "conversationId" in workspace
    assert "CanonicalAgentWorkspacePage" in workspace
    assert "@windagent/app/src/features/agent-workspace" in workspace


def test_canonical_agent_workspace_is_query_and_realtime_driven():
    """Phase 11: Query-backed data + realtime stream; zero polling, zero mocks."""
    hook = _read(CANONICAL_HOOK)
    assert "useQuery" in hook or "fetchQuery" in hook
    assert "setInterval" not in hook
    assert "setTimeout" not in hook
    assert "Math.random" not in hook
    assert "conversation" in hook and "tasks" in hook
    page = _read(CANONICAL_PAGE)
    assert "conversationId" in page


def test_canonical_workspace_calls_v3_conversation_api():
    """Phase 11.3: conversation is the authority — agents/tasks/events hang off it."""
    hook = _read(CANONICAL_HOOK)
    assert "conversations.get" in hook
    assert "conversations.getAgents" in hook
    assert "conversations.getTasks" in hook
    assert "conversations.getEvents" in hook


def test_workspace_has_no_mock_browser_or_task_graph():
    """Legacy mock panels removed with the cutover; realtime panels remain."""
    workspace = _read(MULTI_AGENT_WS)
    assert "Awesome App" not in workspace
    assert "fetchBrowserState" not in workspace
    assert "Không có browser runtime" not in workspace
    assert "v2Unavailable" not in workspace
    terminal = _read(CANONICAL_WS_DIR / "components" / "AgentTerminal.tsx")
    assert "Workspace Event Stream & Output" in terminal
    assert "events" in terminal


def test_canonical_workspace_preserves_operator_panels():
    """Phase 11.5 target structure: coordinator, agents, tasks, inspector, terminal, browser."""
    panel_files = {p.name for p in (CANONICAL_WS_DIR / "components").glob("*.tsx")}
    for expected in ("CoordinatorPanel.tsx", "AgentInstanceList.tsx", "TaskGraph.tsx", "AgentInspector.tsx", "AgentTerminal.tsx", "BrowserRuntimePanel.tsx"):
        assert expected in panel_files, f"missing {expected}"