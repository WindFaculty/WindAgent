"""Phase 0/7 single durable multi-agent workspace contract gates."""

from pathlib import Path


ROOT = Path(__file__).parents[2]
APP_TSX = ROOT / "apps" / "desktop" / "src" / "App.tsx"
MULTI_AGENT_WS = ROOT / "apps" / "desktop" / "src" / "pages" / "MultiAgentWorkspace.tsx"
STORE = ROOT / "apps" / "desktop" / "src" / "state" / "multiAgentStore.tsx"
ADR = ROOT / "docs" / "adr" / "0006-multi-agent-workspace-aggregates.md"
TEST_MATRIX = ROOT / "docs" / "architecture" / "g1_g9_test_matrix.md"
SCHEMA_MAPPING = ROOT / "docs" / "architecture" / "multi_agent_schema_mapping.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase0_docs_exist():
    for doc in (ADR, SCHEMA_MAPPING, TEST_MATRIX):
        assert doc.is_file(), f"missing Phase 0 deliverable: {doc}"
    assert "Multi-Agent Workspace Target Architecture" in _read(ADR)
    assert "G1.1" in _read(TEST_MATRIX) and "G9.7" in _read(TEST_MATRIX)
    assert "task_plan_versions" in _read(SCHEMA_MAPPING)


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


def test_workspace_uses_normalized_conversation_store():
    workspace = _read(MULTI_AGENT_WS)
    store = _read(STORE)
    assert "useMultiAgent" in workspace
    assert "conversationId" in workspace
    assert "MultiAgentProvider" in store and "setConversationId" in store
    for key in ("conversations", "agents", "sessions", "events", "taskNodes"):
        assert key in store


def test_workspace_has_no_mock_browser_or_task_graph():
    workspace = _read(MULTI_AGENT_WS)
    assert "Awesome App" not in workspace
    assert "fetchBrowserState" in workspace
    assert "Không có browser runtime" in workspace
    assert "v2Unavailable" not in workspace


def test_workspace_preserves_three_column_operator_contract():
    """G8: required labels and live inspector sources remain production-wired."""
    workspace = _read(MULTI_AGENT_WS)
    for label in ("Agent điều phối", "Sub-agents", "Công việc hiện tại"):
        assert label in workspace
    for field in ("Model", "Provider binding", "Route lock", "Permission profile", "Worktree"):
        assert field in workspace
    assert "BrowserPanel" in workspace and "fetchBrowserState" in workspace
