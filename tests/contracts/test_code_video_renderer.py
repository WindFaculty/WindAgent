"""
Contract and Unit Test Suite for Code Studio Renderer Subsystem.

Verifies:
- Python syntax highlighter and tokenization
- Code Editor renderer actions, state hashes, selection, highlights, and zoom
- Terminal renderer command playback, stdout/stderr formatting, and exit codes
- Architecture diagram renderer for scenes S03, S04, S11, S17 and SVG generation
- Title cards (S02), Not Yet checklist (S16), and Outro teaser (S19)
- Master Code Studio layout orchestration and recording-safe UI guarantees
- Full 19-scene plan replay rendering against video_02_plan.json
"""

import json
from pathlib import Path
import pytest

from workflows.windagent_workflows.code_video.contracts import (
    Action,
    ActionType,
    CodeVideoPlan,
    Resolution,
    Scene,
    VisualMode,
)
from windagent_tools.code_video.renderer import (
    ChecklistItemStatus,
    CodeEditorRenderer,
    CodeEditorState,
    CodeStudioRenderer,
    CodeToken,
    DiagramRenderer,
    DiagramState,
    FileTreeState,
    NodeCategory,
    PythonSyntaxHighlighter,
    PythonTokenType,
    StudioLayoutState,
    TerminalLineType,
    TerminalRenderer,
    TerminalState,
    TitleRenderer,
)


class TestPythonSyntaxHighlighter:
    """Test suite for Python syntax tokenization and highlighting."""

    def test_tokenize_keywords_and_classes(self) -> None:
        line = "class SimpleAgent:"
        tokens = PythonSyntaxHighlighter.tokenize_line(line)
        types = [t.token_type for t in tokens if t.token_type != PythonTokenType.PLAIN]
        assert PythonTokenType.KEYWORD in types
        assert PythonTokenType.DEF_CLASS in types

        # Check values
        class_kw = next(t for t in tokens if t.value == "class")
        assert class_kw.token_type == PythonTokenType.KEYWORD
        name_tok = next(t for t in tokens if t.value == "SimpleAgent")
        assert name_tok.token_type == PythonTokenType.DEF_CLASS

    def test_tokenize_decorators_and_types(self) -> None:
        code = "@dataclass(frozen=True)\ndef run(self, prompt: str) -> str:\n    return prompt"
        token_lines = PythonSyntaxHighlighter.tokenize(code)
        assert len(token_lines) == 3

        # Line 1 decorator
        dec_tok = next(t for t in token_lines[0] if t.token_type == PythonTokenType.DECORATOR)
        assert dec_tok.value == "@dataclass"

        # Line 2 def keyword and builtin str
        def_kw = next(t for t in token_lines[1] if t.value == "def")
        assert def_kw.token_type == PythonTokenType.KEYWORD
        fn_name = next(t for t in token_lines[1] if t.value == "run")
        assert fn_name.token_type == PythonTokenType.DEF_CLASS
        str_type = next(t for t in token_lines[1] if t.value == "str")
        assert str_type.token_type == PythonTokenType.BUILTIN

    def test_tokenize_comments_and_strings(self) -> None:
        line = '    name = "agentic-studio"  # Project Name'
        tokens = PythonSyntaxHighlighter.tokenize_line(line)
        str_tok = next(t for t in tokens if t.token_type == PythonTokenType.STRING)
        assert str_tok.value == '"agentic-studio"'
        comment_tok = next(t for t in tokens if t.token_type == PythonTokenType.COMMENT)
        assert comment_tok.value == "# Project Name"


class TestCodeEditorRenderer:
    """Test suite for CodeEditorState and CodeEditorRenderer."""

    def test_initial_state_and_open_file(self) -> None:
        renderer = CodeEditorRenderer()
        assert renderer.state.active_file == "src/agent.py"
        assert renderer.state.zoom_level == 1.0

        renderer.open_file("tests/test_agent.py", "def test_run():\n    assert True\n")
        assert renderer.state.active_file == "tests/test_agent.py"
        assert renderer.state.line_count == 3
        assert len(renderer.state.content_hash) == 64

    def test_typing_and_replacement(self) -> None:
        renderer = CodeEditorRenderer()
        renderer.open_file("src/agent.py", "")
        renderer.type_text("class Message:\n    role: str\n    content: str")

        assert "class Message:" in renderer.state.content
        assert renderer.state.cursor_line == 3
        assert renderer.state.line_count == 3

        renderer.replace_text("# New Clean Code\npass")
        assert renderer.state.line_count == 2
        assert renderer.state.content.startswith("# New Clean Code")

    def test_selection_and_highlights(self) -> None:
        renderer = CodeEditorRenderer()
        renderer.open_file("src/agent.py", "class Message:\n    role: str\n    content: str\n")

        renderer.select_range(1, 1, 1, 14)
        assert renderer.state.selection == (1, 1, 1, 14)

        renderer.highlight_symbol("Message")
        assert renderer.state.highlighted_symbol == "Message"
        assert 1 in renderer.state.highlighted_lines

        renderer.clear_highlights()
        assert renderer.state.highlighted_symbol is None
        assert len(renderer.state.highlighted_lines) == 0

    def test_apply_semantic_actions(self) -> None:
        renderer = CodeEditorRenderer()
        action_open = Action(
            action_id="A01",
            action_type=ActionType.OPEN_FILE,
            start_ms=0,
            duration_ms=1000,
            params={"path": "src/agent.py", "content": "@dataclass\nclass Message:\n    pass"}
        )
        renderer.apply_action(action_open)
        assert renderer.state.active_file == "src/agent.py"
        assert renderer.state.line_count == 3

        action_zoom = Action(
            action_id="A02",
            action_type=ActionType.ZOOM,
            start_ms=1000,
            duration_ms=1000,
            params={"zoom_level": 1.5}
        )
        renderer.apply_action(action_zoom)
        assert renderer.state.zoom_level == 1.5

    def test_html_rendering(self) -> None:
        renderer = CodeEditorRenderer()
        renderer.open_file("src/agent.py", "class Message:\n    role: str\n")
        html_out = renderer.state.render_html()

        assert 'class="code-editor"' in html_out
        assert 'data-file="src/agent.py"' in html_out
        assert 'class="line-num"' in html_out
        assert 'tok-keyword' in html_out


class TestTerminalRenderer:
    """Test suite for deterministic TerminalRenderer."""

    def test_command_playback_and_exit_code(self) -> None:
        terminal = TerminalRenderer()
        terminal.set_working_dir("agentic-studio")
        assert "agentic-studio" in terminal.state.prompt_prefix

        terminal.type_command("pytest")
        assert terminal.state.current_input == "pytest"

        terminal.execute_command(
            command="pytest",
            output="================ 2 passed in 0.05s ================",
            exit_code=0,
            timestamp_ms=5000,
        )

        assert terminal.state.last_command == "pytest"
        assert terminal.state.last_exit_code == 0
        assert len(terminal.state.history) == 3  # command, stdout, exit_code

        # Check line types
        assert terminal.state.history[0].line_type == TerminalLineType.COMMAND
        assert terminal.state.history[1].line_type == TerminalLineType.STDOUT
        assert terminal.state.history[2].line_type == TerminalLineType.EXIT_CODE

    def test_apply_run_terminal_action(self) -> None:
        terminal = TerminalRenderer()
        action = Action(
            action_id="A_TERM",
            action_type=ActionType.RUN_TERMINAL,
            start_ms=10000,
            duration_ms=5000,
            params={
                "command": "git tag v0.1",
                "expected": {"exit_code": 0},
            }
        )
        terminal.apply_action(action)
        assert terminal.state.last_command == "git tag v0.1"
        assert terminal.state.last_exit_code == 0

    def test_terminal_html_rendering(self) -> None:
        terminal = TerminalRenderer()
        terminal.execute_command("python -m src.agent", "Assistant: Hello!", exit_code=0)
        html_out = terminal.state.render_html()

        assert 'class="terminal-container"' in html_out
        assert 'term-command' in html_out
        assert 'term-exit_code' in html_out
        assert 'Process exited with code 0' in html_out


class TestDiagramRenderer:
    """Test suite for Architecture & Concept Diagram Renderer."""

    def test_s03_recap_diagram_structure(self) -> None:
        state = DiagramRenderer.build_s03_recap_diagram()
        assert state.diagram_id == "S03_RECAP"
        assert len(state.nodes) == 3
        assert len(state.edges) == 2
        svg = state.render_svg()
        assert "<svg" in svg
        assert "Video 01 Recap" in svg

    def test_s04_arch_v01_diagram_structure(self) -> None:
        state = DiagramRenderer.build_s04_arch_v01_diagram()
        assert state.diagram_id == "S04_ARCH_V0_1"
        assert len(state.nodes) == 4
        node_ids = {n.id for n in state.nodes}
        assert {"N_USER", "N_AGENT", "N_LLM", "N_ANSWER"}.issubset(node_ids)

        svg = state.render_svg()
        assert "Agentic Studio v0.1 Architecture" in svg
        assert "N_AGENT" in svg or "Agent" in svg

    def test_s11_concept_diagram_structure(self) -> None:
        state = DiagramRenderer.build_s11_concept_diagram()
        assert state.diagram_id == "S11_IS_THIS_AGENT"
        assert len(state.nodes) == 3
        svg = state.render_svg()
        assert "Is This An Agent?" in svg

    def test_s17_review_diagram_structure(self) -> None:
        state = DiagramRenderer.build_s17_review_diagram()
        assert state.diagram_id == "S17_ARCH_REVIEW"
        assert len(state.nodes) == 3
        # Has domain and infrastructure categories
        categories = {n.category for n in state.nodes}
        assert NodeCategory.DOMAIN in categories
        assert NodeCategory.INFRASTRUCTURE in categories
        svg = state.render_svg()
        assert "Architecture Review" in svg

    def test_diagram_renderer_actions(self) -> None:
        renderer = DiagramRenderer()
        action = Action(
            action_id="A_DIAG",
            action_type=ActionType.SHOW_DIAGRAM,
            start_ms=0,
            duration_ms=3000,
            params={"diagram_id": "S17_ARCH_REVIEW", "highlight": "D_MODELS"}
        )
        renderer.apply_action(action)
        assert renderer.state.diagram_id == "S17_ARCH_REVIEW"
        assert "D_MODELS" in renderer.state.highlighted_nodes


class TestTitleAndChecklistRenderer:
    """Test suite for Title Cards, Scope Checklists, and Outros."""

    def test_s02_hook_title_card(self) -> None:
        state = TitleRenderer.build_s02_hook_title()
        assert state.badge == "VIDEO 02"
        assert "VIẾT AI AGENT" in state.title
        html_out = state.render_html()
        assert "title-card-container" in html_out
        assert "VIDEO 02" in html_out

    def test_s16_not_yet_checklist(self) -> None:
        state = TitleRenderer.build_s16_checklist()
        assert len(state.items) >= 6
        included = [it for it in state.items if it.status == ChecklistItemStatus.INCLUDED]
        excluded = [it for it in state.items if it.status == ChecklistItemStatus.EXCLUDED]
        assert len(included) >= 4
        assert len(excluded) >= 2

        # Check Tool Calling is excluded
        tc_item = next(it for it in state.items if "Tool Calling" in it.text)
        assert tc_item.status == ChecklistItemStatus.EXCLUDED
        assert tc_item.tag == "VIDEO 03"

        html_out = state.render_html()
        assert "checklist-container" in html_out
        assert "Tool Calling" in html_out

    def test_s19_outro_card(self) -> None:
        state = TitleRenderer.build_s19_outro_card()
        assert "VIDEO 03: TOOL CALLING" in state.next_episode_title
        html_out = state.render_html()
        assert "outro-card-container" in html_out
        assert "VIDEO 03" in html_out


class TestCodeStudioMasterRenderer:
    """Test suite for master CodeStudioRenderer layout orchestration."""

    def test_file_tree_state(self) -> None:
        tree = FileTreeState.default_video_02_tree(active_path="src/agent.py")
        assert tree.root_name == "agentic-studio"
        assert len(tree.items) == 6
        html_out = tree.render_html()
        assert "src" in html_out
        assert "tests" in html_out
        assert "pyproject.toml" in html_out

    def test_layout_switching_across_modes(self) -> None:
        studio = CodeStudioRenderer()
        for mode in VisualMode:
            studio.switch_layout(mode)
            assert studio.layout_state.visual_mode == mode
            html_out = studio.layout_state.render_html()
            assert "<!DOCTYPE html>" in html_out
            assert studio.layout_state.project_name in html_out

    def test_recording_safe_ui_guarantees(self) -> None:
        studio = CodeStudioRenderer()
        html_out = studio.layout_state.render_html()

        # Guarantees:
        assert "REC SAFE" in html_out
        assert "agentic-studio" in html_out
        # No personal home paths
        assert "C:\\Users\\" not in html_out
        assert "/home/" not in html_out

    def test_full_video_02_plan_end_to_end_replay(self) -> None:
        """Replay all 19 scenes from video_02_plan.json through CodeStudioRenderer."""
        plan_path = Path("artifacts/code_video/video_02/plans/video_02_plan.json")
        assert plan_path.exists(), f"Plan artifact {plan_path} must exist from Phase 4"

        with open(plan_path, "r", encoding="utf-8") as f:
            plan_data = json.load(f)

        plan = CodeVideoPlan.from_dict(plan_data)
        assert plan.total_scenes == 19

        studio = CodeStudioRenderer()

        for idx, scene in enumerate(plan.scenes):
            studio.apply_scene(scene)
            assert studio.layout_state.visual_mode == scene.visual_mode

            # Render HTML snapshot for each scene
            rendered_frame = studio.layout_state.render_html()
            assert len(rendered_frame) > 100
            assert "<html" in rendered_frame
