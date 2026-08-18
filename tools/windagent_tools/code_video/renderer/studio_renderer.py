"""
Code Studio Master Renderer for Code Video Production.

Orchestrates the entire Code Studio layout: Header, FileTree, CodeEditor, Terminal,
DiagramStage, TitleCard, Checklist, and Outro. Enforces recording-safe visual guarantees
(sanitized workspace, no popups, no hostname, high-contrast dark theme).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import html
from typing import Any, Dict, List, Optional

from workflows.windagent_workflows.code_video.contracts import (
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
            FileTreeItem("src/__init__.py", "__init__.py", is_active=(active_path == "src/__init__.py")),
            FileTreeItem("src/agent.py", "agent.py", is_active=(active_path == "src/agent.py")),
        ]
        test_children = [
            FileTreeItem("tests/__init__.py", "__init__.py", is_active=(active_path == "tests/__init__.py")),
            FileTreeItem("tests/test_agent.py", "test_agent.py", is_active=(active_path == "tests/test_agent.py")),
        ]
        items = [
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
        def _render_item(item: FileTreeItem, depth: int = 0) -> str:
            pad = depth * 16
            icon = "📁" if item.is_dir else "📄"
            active_cls = "active" if item.is_active else ""
            html_parts = [
                f'<div class="tree-item {active_cls}" style="padding-left: {pad + 12}px;" data-path="{html.escape(item.path)}">'
                f'<span class="tree-icon">{icon}</span>'
                f'<span class="tree-label">{html.escape(item.name)}</span>'
                f'</div>'
            ]
            if item.is_dir and item.is_open:
                for child in item.children:
                    html_parts.append(_render_item(child, depth + 1))
            return "\n".join(html_parts)

        inner = "\n".join(_render_item(it) for it in self.items)
        return (
            f'<div class="file-tree-container">\n'
            f'  <div class="tree-header"><span class="tree-root-label">EXPLORER: {html.escape(self.root_name)}</span></div>\n'
            f'  <div class="tree-body">\n{inner}\n  </div>\n'
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

        if mode == VisualMode.CODE_STUDIO:
            content_html = (
                f'<main class="studio-main layout-code-studio">\n'
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
                f'  <div class="pane-editor full-view">{self.editor.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.FULL_TERMINAL:
            content_html = (
                f'<main class="studio-main layout-full-terminal">\n'
                f'  <div class="pane-terminal full-view">{self.terminal.render_html()}</div>\n'
                f'</main>'
            )
        elif mode in (VisualMode.DIAGRAM, VisualMode.ARCHITECTURE):
            content_html = (
                f'<main class="studio-main layout-diagram">\n'
                f'  <div class="pane-diagram">{self.diagram.render_svg()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.TITLE_CARD:
            content_html = (
                f'<main class="studio-main layout-title">\n'
                f'  <div class="pane-title">{self.title_card.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.CHECKLIST:
            content_html = (
                f'<main class="studio-main layout-checklist">\n'
                f'  <div class="pane-checklist">{self.checklist.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.SPLIT:
            content_html = (
                f'<main class="studio-main layout-split">\n'
                f'  <div class="pane-split-left">{self.editor.render_html()}</div>\n'
                f'  <div class="pane-split-right">{self.terminal.render_html()}</div>\n'
                f'</main>'
            )
        elif mode == VisualMode.OUTRO:
            content_html = (
                f'<main class="studio-main layout-outro">\n'
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
            f'    body {{ margin: 0; padding: 0; background: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; overflow: hidden; }}\n'
            f'    .studio-header {{ display: flex; justify-content: space-between; align-items: center; height: 40px; background: #161b22; border-bottom: 1px solid #30363d; padding: 0 16px; }}\n'
            f'    .project-pill, .episode-pill {{ background: #21262d; border: 1px solid #30363d; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px; }}\n'
            f'    .rec-badge {{ background: #da3633; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; }}\n'
            f'    .studio-main {{ display: flex; height: calc(100vh - 40px); box-sizing: border-box; }}\n'
            f'    .pane-file-tree {{ width: 220px; background: #010409; border-right: 1px solid #30363d; overflow: hidden; }}\n'
            f'    .pane-editor-and-terminal {{ flex: 1; display: flex; flex-direction: column; }}\n'
            f'    .pane-editor {{ flex: 6; background: #0d1117; overflow: hidden; font-family: "Fira Code", monospace; }}\n'
            f'    .pane-terminal {{ flex: 4; background: #010409; border-top: 1px solid #30363d; overflow: hidden; font-family: "Fira Code", monospace; }}\n'
            f'    .full-view {{ flex: 1; height: 100%; }}\n'
            f'    .layout-split {{ display: grid; grid-template-columns: 1fr 1fr; height: 100%; }}\n'
            f'    .tok-keyword {{ color: #ff7b72; font-weight: bold; }}\n'
            f'    .tok-builtin {{ color: #79c0ff; }}\n'
            f'    .tok-def_class {{ color: #d2a8ff; font-weight: bold; }}\n'
            f'    .tok-decorator {{ color: #ffa657; }}\n'
            f'    .tok-string {{ color: #a5d6ff; }}\n'
            f'    .tok-number {{ color: #79c0ff; }}\n'
            f'    .tok-comment {{ color: #8b949e; font-style: italic; }}\n'
            f'    .tok-operator {{ color: #ff7b72; }}\n'
            f'  </style>\n'
            f'</head>\n'
            f'<body>\n'
            f'{header_html}\n'
            f'{content_html}\n'
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
