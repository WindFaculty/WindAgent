"""
Code Studio Master Renderer for Code Video Production.

Orchestrates the entire Code Studio layout: Header, FileTree, CodeEditor, Terminal,
DiagramStage, TitleCard, Checklist, and Outro. Enforces recording-safe visual guarantees
(sanitized workspace, no popups, no hostname, high-contrast dark theme).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import html
from typing import Any, Dict, List, Optional

from windagent_core.contracts.code_video import (
    Action,
    ActionType,
    Scene,
    VisualMode,
)

from windagent_tools.code_video.renderer.code_renderer import (
    CodeEditorRenderer,
    CodeEditorState,
)
from windagent_tools.code_video.renderer.diagram_renderer import (
    DiagramRenderer,
    DiagramState,
)
from windagent_tools.code_video.renderer.terminal_renderer import (
    TerminalRenderer,
    TerminalState,
)
from windagent_tools.code_video.renderer.title_renderer import (
    ChecklistState,
    OutroCardState,
    TitleCardState,
    TitleRenderer,
)


@dataclass(frozen=True)
class FileTreeItem:
    path: str
    name: str
    is_dir: bool = False
    children: List[FileTreeItem] = field(default_factory=list)
    is_open: bool = True
    is_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "is_dir": self.is_dir,
            "children": [c.to_dict() for c in self.children],
            "is_open": self.is_open,
            "is_active": self.is_active,
        }


@dataclass
class FileTreeState:
    root_name: str = "agentic-studio"
    active_path: str = "src/agent.py"
    items: List[FileTreeItem] = field(default_factory=list)

    @classmethod
    def default_video_02_tree(cls, active_path: str = "src/agent.py") -> FileTreeState:
        src_children = [
            FileTreeItem("src/__pycache__", "__pycache__", is_dir=True, is_open=False),
            FileTreeItem("src/__init__.py", "__init__.py", is_active=(active_path == "src/__init__.py")),
            FileTreeItem("src/agent.py", "agent.py", is_active=(active_path == "src/agent.py")),
        ]
        test_children = [
            FileTreeItem("tests/__pycache__", "__pycache__", is_dir=True, is_open=False),
            FileTreeItem("tests/__init__.py", "__init__.py", is_active=(active_path == "tests/__init__.py")),
            FileTreeItem("tests/test_agent.py", "test_agent.py", is_active=(active_path == "tests/test_agent.py")),
        ]
        items = [
            FileTreeItem(".pytest_cache", ".pytest_cache", is_dir=True, is_open=False),
            FileTreeItem("src", "src", is_dir=True, children=src_children, is_open=True),
            FileTreeItem("tests", "tests", is_dir=True, children=test_children, is_open=True),
            FileTreeItem(".env.example", ".env.example", is_active=(active_path == ".env.example")),
            FileTreeItem(".gitignore", ".gitignore", is_active=(active_path == ".gitignore")),
            FileTreeItem("pyproject.toml", "pyproject.toml", is_active=(active_path == "pyproject.toml")),
            FileTreeItem("README.md", "README.md", is_active=(active_path == "README.md")),
        ]
        return cls(root_name="agentic-studio", active_path=active_path, items=items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_name": self.root_name,
            "active_path": self.active_path,
            "items": [i.to_dict() for i in self.items],
        }

    def render_html(self) -> str:
        def _render_item(item: FileTreeItem, depth: int = 1) -> str:
            pad = depth * 14 + 14
            badge_html = ""
            status_cls = ""

            if item.is_dir:
                chevron = '<span class="tree-chevron">⌄</span>' if item.is_open else '<span class="tree-chevron">&gt;</span>'
                if item.name in ("src", "tests"):
                    icon = '<span class="tree-icon code-folder">📁</span>'
                else:
                    icon = '<span class="tree-icon folder">📁</span>'

                if item.name == "src":
                    status_cls = "status-src"
                    badge_html = '<span class="tree-badge dot dot-green">●</span>'
                elif item.name == "tests":
                    status_cls = "status-tests"
                    badge_html = '<span class="tree-badge dot dot-coral">●</span>'
                elif item.name in (".pytest_cache", "__pycache__"):
                    status_cls = "status-muted"
            else:
                chevron = '<span class="tree-chevron spacer"></span>'
                if item.name.endswith(".py"):
                    icon = '<span class="tree-icon py-snake">🐍</span>'
                    if item.name == "test_agent.py":
                        status_cls = "status-error"
                        badge_html = '<span class="tree-badge text-coral">1, U</span>'
                    else:
                        status_cls = "status-untracked"
                        badge_html = '<span class="tree-badge text-green">U</span>'
                elif item.name == "README.md":
                    icon = '<span class="badge badge-md">M↓</span>'
                    status_cls = "status-modified"
                    badge_html = '<span class="tree-badge text-yellow">M</span>'
                elif item.name.startswith(".env"):
                    icon = '<span class="tree-icon doc">📄</span>'
                    status_cls = "status-untracked"
                    badge_html = '<span class="tree-badge text-green">U</span>'
                elif item.name == ".gitignore":
                    icon = '<span class="tree-icon git-diamond">🔶</span>'
                    status_cls = "status-untracked"
                    badge_html = '<span class="tree-badge text-green">U</span>'
                elif item.name.endswith(".toml"):
                    icon = '<span class="tree-icon py-snake">🐍</span>'
                    status_cls = "status-untracked"
                    badge_html = '<span class="tree-badge text-green">U</span>'
                else:
                    icon = '<span class="tree-icon file">📄</span>'

            active_cls = "active" if item.is_active else ""
            guide_line = f'<span class="indent-guide" style="left: {pad - 10}px;"></span>' if depth > 0 else ""
            html_parts = [
                f'<div class="tree-item {active_cls} {status_cls}" style="padding-left: {pad}px;" data-path="{html.escape(item.path)}">'
                f'{guide_line}'
                f'{chevron}'
                f'{icon}'
                f'<span class="tree-label">{html.escape(item.name)}</span>'
                f'{badge_html}'
                f'</div>'
            ]
            if item.is_dir and item.is_open:
                for child in item.children:
                    html_parts.append(_render_item(child, depth + 1))
            return "\n".join(html_parts)

        inner = "\n".join(_render_item(it, depth=1) for it in self.items)
        return (
            f'<div class="file-tree-container">\n'
            f'  <div class="tree-header">\n'
            f'    <span class="tree-header-title">Explorer</span>\n'
            f'    <span class="tree-header-actions">···</span>\n'
            f'  </div>\n'
            f'  <div class="tree-body">\n'
            f'    <div class="tree-item workspace-subroot open status-root">'
            f'      <span class="tree-chevron">⌄</span>'
            f'      <span class="tree-icon folder">📁</span>'
            f'      <span class="tree-label">{html.escape(self.root_name)}</span>'
            f'      <span class="tree-badge dot dot-coral">●</span>'
            f'    </div>\n'
            f'{inner}\n'
            f'  </div>\n'
            f'</div>'
        )


@dataclass
class StudioLayoutState:
    visual_mode: VisualMode = VisualMode.CODE_STUDIO
    project_name: str = "agentic-studio"
    episode_badge: str = "VIDEO 02"
    file_tree: FileTreeState = field(default_factory=FileTreeState.default_video_02_tree)
    editor: CodeEditorState = field(default_factory=CodeEditorState)
    terminal: TerminalState = field(default_factory=TerminalState)
    diagram: DiagramState = field(default_factory=DiagramState)
    title_card: TitleCardState = field(default_factory=TitleCardState)
    checklist: ChecklistState = field(default_factory=ChecklistState)
    outro: OutroCardState = field(default_factory=OutroCardState)
    recording_safe: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visual_mode": self.visual_mode.value,
            "project_name": self.project_name,
            "episode_badge": self.episode_badge,
            "file_tree": self.file_tree.to_dict(),
            "editor": self.editor.to_dict(),
            "terminal": self.terminal.to_dict(),
            "diagram": self.diagram.to_dict(),
            "title_card": self.title_card.to_dict(),
            "checklist": self.checklist.to_dict(),
            "outro": self.outro.to_dict(),
            "recording_safe": self.recording_safe,
        }

    def render_html(self) -> str:
        """Render complete studio layout based on active VisualMode."""
        header_html = (
            f'<header class="studio-header">\n'
            f'  <div class="studio-header-left">\n'
            f'    <span class="app-logo">⚡ WindAgent Code Studio</span>\n'
            f'    <span class="project-pill">{html.escape(self.project_name)}</span>\n'
            f'  </div>\n'
            f'  <div class="studio-header-right">\n'
            f'    <span class="rec-badge">REC SAFE</span>\n'
            f'    <span class="episode-pill">{html.escape(self.episode_badge)}</span>\n'
            f'  </div>\n'
            f'</header>'
        )

        content_html = ""
        mode = self.visual_mode

        activity_bar_html = (
            '<div class="pane-activity-bar">\n'
            '  <div class="act-item active" title="Explorer">📁</div>\n'
            '  <div class="act-item" title="Search">🔍</div>\n'
            '  <div class="act-item badge-container" title="Source Control">🔀<span class="act-badge">24</span></div>\n'
            '  <div class="act-item" title="Run & Debug">▶</div>\n'
            '  <div class="act-item" title="Remote">&gt;&lt;</div>\n'
            '  <div class="act-item" title="Extensions">🧩</div>\n'
            '  <div class="act-item" title="Testing">⚗</div>\n'
            '  <div class="act-spacer"></div>\n'
            '  <div class="act-item" title="Accounts">👤</div>\n'
            '  <div class="act-item" title="Settings">⚙</div>\n'
            '</div>'
        )

        status_bar_html = (
            '<footer class="studio-statusbar">\n'
            '  <div class="status-left"><span class="wsl-pill">&gt;&lt;</span> <span>🔀 main*</span> <span>🔄 0 ↓ 1 ↑</span> <span>⨂ 0  ⚠ 0</span></div>\n'
            '  <div class="status-right"><span>Ln 14, Col 21</span> <span>Spaces: 4</span> <span>UTF-8</span> <span>LF</span> <span>{ } Python 3.11.8</span> <span>✨ Antigravity: Ready</span> <span>🔔</span></div>\n'
            '</footer>'
        )

        if mode == VisualMode.CODE_STUDIO:
            content_html = (
                f'<main class="studio-main layout-code-studio">\n'
                f'  {activity_bar_html}\n'
                f'  <aside class="pane-file-tree">{self.file_tree.render_html()}</aside>\n'
                f'  <section class="pane-editor-and-terminal">\n'
                f'    <div class="pane-editor">{self.editor.render_html()}</div>\n'
                f'    <div class="pane-terminal">{self.terminal.render_html()}</div>\n'
                f'  </section>\n'
                f'</main>'
            )
        elif mode == VisualMode.FULL_CODE:
            content_html = (
                f'<main class="studio-main layout-full-code">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-editor full-view">{self.editor.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.FULL_TERMINAL:
            content_html = (
                f'<main class="studio-main layout-full-terminal">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-terminal full-view">{self.terminal.render_html()}</div>\n'
                f'</main>'
            )
        elif mode in (VisualMode.DIAGRAM, VisualMode.ARCHITECTURE):
            content_html = (
                f'<main class="studio-main layout-diagram">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-diagram">{self.diagram.render_svg()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.TITLE_CARD:
            content_html = (
                f'<main class="studio-main layout-title">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-title">{self.title_card.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.CHECKLIST:
            content_html = (
                f'<main class="studio-main layout-checklist">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-checklist">{self.checklist.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.SPLIT:
            content_html = (
                f'<main class="studio-main layout-split">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-split-left">{self.editor.render_html()}</div>\n'
                f'  <div class="pane-split-right">{self.terminal.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.OUTRO:
            content_html = (
                f'<main class="studio-main layout-outro">\n'
                f'  {activity_bar_html}\n'
                f'  <div class="pane-outro">{self.outro.render_html()}</div>\n'
                f'</main>'
            )

        return (
            f'<!DOCTYPE html>\n'
            f'<html lang="en">\n'
            f'<head>\n'
            f'  <meta charset="UTF-8">\n'
            f'  <title>{html.escape(self.project_name)} — {html.escape(self.episode_badge)}</title>\n'
            f'  <style>\n'
            f'    body {{ margin: 0; padding: 0; background: #1e1e1e; color: #cccccc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; overflow: hidden; display: flex; flex-direction: column; height: 100vh; }}\n'
            f'    .studio-header {{ display: flex; justify-content: space-between; align-items: center; height: 38px; background: #1e1e1e; border-bottom: 1px solid #333333; padding: 0 16px; }}\n'
            f'    .project-pill, .episode-pill {{ background: #2d2d2d; border: 1px solid #3c3c3c; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px; color: #e0e0e0; }}\n'
            f'    .rec-badge {{ background: #b03030; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }}\n'
            f'    .studio-main {{ display: flex; flex: 1; height: calc(100vh - 66px); box-sizing: border-box; overflow: hidden; }}\n'
            f'    .pane-activity-bar {{ width: 50px; background: #181818; border-right: 1px solid #2d2d2d; display: flex; flex-direction: column; align-items: center; padding: 8px 0; position: relative; }}\n'
            f'    .act-item {{ width: 42px; height: 42px; display: flex; align-items: center; justify-content: center; font-size: 18px; color: #858585; cursor: pointer; border-left: 2px solid transparent; position: relative; }}\n'
            f'    .act-item.active {{ color: #ffffff; border-left-color: #007acc; }}\n'
            f'    .act-badge {{ position: absolute; top: 4px; right: 4px; background: #0078d4; color: #fff; font-size: 10px; font-weight: bold; border-radius: 8px; padding: 1px 5px; min-width: 14px; text-align: center; }}\n'
            f'    .act-spacer {{ flex: 1; }}\n'
            f'    .pane-file-tree {{ width: 260px; background: #181818; border-right: 1px solid #2d2d2d; overflow: hidden; display: flex; flex-direction: column; font-size: 13px; }}\n'
            f'    .file-tree-container {{ display: flex; flex-direction: column; height: 100%; }}\n'
            f'    .tree-header {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px 4px 16px; font-weight: bold; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #bbbbbb; }}\n'
            f'    .tree-header-actions {{ color: #888888; font-size: 14px; }}\n'
            f'    .workspace-section {{ display: flex; align-items: center; gap: 6px; padding: 4px 12px; font-weight: 600; font-size: 12px; color: #ffffff; cursor: pointer; }}\n'
            f'    .tree-body {{ flex: 1; overflow-y: auto; display: flex; flex-direction: column; }}\n'
            f'    .tree-item {{ display: flex; align-items: center; height: 24px; color: #cccccc; cursor: pointer; position: relative; font-size: 13px; user-select: none; }}\n'
            f'    .tree-item:hover {{ background: rgba(255, 255, 255, 0.04); }}\n'
            f'    .tree-item.active {{ background: #2a2d2e; color: #ffffff; }}\n'
            f'    .tree-item.active::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 2px; background: #007acc; }}\n'
            f'    .tree-chevron {{ font-size: 10px; width: 14px; text-align: center; color: #888888; margin-right: 2px; }}\n'
            f'    .tree-chevron.spacer {{ width: 14px; }}\n'
            f'    .indent-guide {{ position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(255, 255, 255, 0.08); }}\n'
            f'    .tree-icon {{ margin-right: 6px; font-size: 13px; }}\n'
            f'    .badge {{ font-size: 10px; font-weight: bold; padding: 1px 4px; border-radius: 3px; margin-right: 6px; text-transform: uppercase; }}\n'
            f'    .badge-py {{ background: #2b5b84; color: #ffd43b; }}\n'
            f'    .badge-md {{ background: #519aba; color: #ffffff; }}\n'
            f'    .badge-env {{ background: #b8641e; color: #ffffff; }}\n'
            f'    .tree-badge {{ margin-left: auto; margin-right: 12px; font-size: 11px; font-weight: bold; }}\n'
            f'    .status-root {{ color: #d97d64; font-weight: bold; }}\n'
            f'    .status-src {{ color: #7ec794; }}\n'
            f'    .status-tests {{ color: #d97d64; }}\n'
            f'    .status-untracked {{ color: #89d185; }}\n'
            f'    .status-modified {{ color: #dcdcaa; }}\n'
            f'    .status-error {{ color: #e57c65; }}\n'
            f'    .status-muted {{ color: #858585; }}\n'
            f'    .text-green {{ color: #73c991; }}\n'
            f'    .text-yellow {{ color: #e5c07b; }}\n'
            f'    .text-coral {{ color: #e57c65; }}\n'
            f'    .dot-green {{ color: #4e8e58; font-size: 8px; }}\n'
            f'    .dot-coral {{ color: #966050; font-size: 8px; }}\n'
            f'    .pane-editor-and-terminal {{ flex: 1; display: flex; flex-direction: column; }}\n'
            f'    .pane-editor {{ flex: 6; background: #1e1e1e; overflow: hidden; font-family: "JetBrains Mono", "Fira Code", Consolas, monospace; }}\n'
            f'    .pane-terminal {{ flex: 4; background: #181818; border-top: 1px solid #2d2d2d; overflow: hidden; font-family: "JetBrains Mono", "Fira Code", Consolas, monospace; }}\n'
            f'    .studio-statusbar {{ height: 28px; background: #007acc; color: #ffffff; display: flex; justify-content: space-between; align-items: center; padding: 0 12px; font-size: 12px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}\n'
            f'    .status-left, .status-right {{ display: flex; gap: 16px; align-items: center; }}\n'
            f'    .wsl-pill {{ background: #005a9e; padding: 2px 6px; font-weight: bold; }}\n'
            f'    .full-view {{ flex: 1; height: 100%; }}\n'
            f'    .layout-split {{ display: grid; grid-template-columns: 50px 1fr 1fr; height: 100%; }}\n'
            f'    .tok-keyword {{ color: #c586c0; font-weight: bold; }}\n'
            f'    .tok-builtin {{ color: #4ec9b0; }}\n'
            f'    .tok-def_class {{ color: #4ec9b0; font-weight: bold; }}\n'
            f'    .tok-decorator {{ color: #dcdcaa; }}\n'
            f'    .tok-string {{ color: #ce9178; }}\n'
            f'    .tok-number {{ color: #b5cea8; }}\n'
            f'    .tok-comment {{ color: #6a9955; font-style: italic; }}\n'
            f'    .tok-operator {{ color: #d4d4d4; }}\n'
            f'    .tok-identifier {{ color: #9cdcfe; }}\n'
            f'  </style>\n'
            f'</head>\n'
            f'<body>\n'
            f'{header_html}\n'
            f'{content_html}\n'
            f'{status_bar_html}\n'
            f'</body>\n'
            f'</html>'
        )


class CodeStudioRenderer:
    """Master controller and frame generator for the Code Studio environment."""

    def __init__(self, initial_state: Optional[StudioLayoutState] = None) -> None:
        self._editor_renderer = CodeEditorRenderer()
        self._terminal_renderer = TerminalRenderer()
        self._diagram_renderer = DiagramRenderer()
        self._title_renderer = TitleRenderer()
        self._layout_state = initial_state or StudioLayoutState(
            editor=self._editor_renderer.state,
            terminal=self._terminal_renderer.state,
            diagram=self._diagram_renderer.state,
            title_card=self._title_renderer.title_state,
            checklist=self._title_renderer.checklist_state,
            outro=self._title_renderer.outro_state,
        )

    @property
    def layout_state(self) -> StudioLayoutState:
        # Synchronize sub-renderer states
        self._layout_state.editor = self._editor_renderer.state
        self._layout_state.terminal = self._terminal_renderer.state
        self._layout_state.diagram = self._diagram_renderer.state
        self._layout_state.title_card = self._title_renderer.title_state
        self._layout_state.checklist = self._title_renderer.checklist_state
        self._layout_state.outro = self._title_renderer.outro_state
        return self._layout_state

    @property
    def editor(self) -> CodeEditorRenderer:
        return self._editor_renderer

    @property
    def terminal(self) -> TerminalRenderer:
        return self._terminal_renderer

    @property
    def diagram(self) -> DiagramRenderer:
        return self._diagram_renderer

    @property
    def title_card(self) -> TitleRenderer:
        return self._title_renderer

    def switch_layout(self, visual_mode: VisualMode) -> StudioLayoutState:
        self._layout_state.visual_mode = visual_mode
        return self.layout_state

    def set_active_file(self, path: str) -> None:
        self._layout_state.file_tree = FileTreeState.default_video_02_tree(active_path=path)
        self._editor_renderer.state.active_file = path

    def apply_action(self, action: Action) -> StudioLayoutState:
        """Route and execute action on the appropriate sub-renderer."""
        if action.action_type == ActionType.SWITCH_LAYOUT:
            mode_raw = action.params.get("visual_mode", action.params.get("mode"))
            if mode_raw:
                self.switch_layout(VisualMode(str(mode_raw)))

        elif action.action_type == ActionType.OPEN_WORKSPACE:
            root = action.params.get("root", "agentic-studio")
            self._layout_state.project_name = root

        elif action.action_type in (
            ActionType.OPEN_FILE,
            ActionType.TYPE_TEXT,
            ActionType.REPLACE_TEXT,
            ActionType.SELECT_RANGE,
            ActionType.HIGHLIGHT,
            ActionType.SCROLL,
            ActionType.ZOOM,
        ):
            if action.action_type == ActionType.OPEN_FILE:
                path = action.params.get("path", "src/agent.py")
                self.set_active_file(path)
            self._editor_renderer.apply_action(action)

        elif action.action_type in (ActionType.RUN_TERMINAL, ActionType.SHOW_OUTPUT):
            self._terminal_renderer.apply_action(action)

        elif action.action_type in (ActionType.SHOW_DIAGRAM, ActionType.SHOW_ARCHITECTURE):
            self._diagram_renderer.apply_action(action)

        elif action.action_type in (ActionType.SHOW_TITLE, ActionType.SHOW_CHECKLIST):
            self._title_renderer.apply_action(action)

        elif action.action_type == ActionType.RESET_VIEW:
            self._editor_renderer.apply_action(action)
            self._terminal_renderer.apply_action(action)
            self._diagram_renderer.apply_action(action)

        return self.layout_state

    def apply_scene(self, scene: Scene) -> StudioLayoutState:
        """Set visual mode and execute all scene actions sequentially."""
        self.switch_layout(scene.visual_mode)
        for action in scene.actions:
            self.apply_action(action)
        return self.layout_state
