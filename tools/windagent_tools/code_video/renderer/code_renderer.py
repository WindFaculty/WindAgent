"""
Code Editor Renderer for Code Video Production.

Provides deterministic state management, Python syntax tokenization/highlighting,
typing simulations, selection ranges, symbol highlights, zoom/focus management,
and rendered HTML/SVG representations for high-fidelity code video takes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import html
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from workflows.windagent_workflows.code_video.contracts import Action, ActionType


class PythonTokenType(str, Enum):
    KEYWORD = "keyword"
    BUILTIN = "builtin"
    DEF_CLASS = "def_class"
    DECORATOR = "decorator"
    STRING = "string"
    NUMBER = "number"
    COMMENT = "comment"
    OPERATOR = "operator"
    PUNCTUATION = "punctuation"
    IDENTIFIER = "identifier"
    PLAIN = "plain"


PYTHON_KEYWORDS: Set[str] = {
    "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "finally", "for", "from",
    "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
    "or", "pass", "raise", "return", "try", "while", "with", "yield",
    "None", "True", "False"
}

PYTHON_BUILTINS: Set[str] = {
    "str", "int", "float", "bool", "list", "dict", "set", "tuple", "bytes",
    "object", "type", "print", "len", "range", "enumerate", "zip", "super",
    "isinstance", "issubclass", "getattr", "setattr", "hasattr", "delattr",
    "Optional", "List", "Dict", "Set", "Tuple", "Any", "Union", "Protocol",
    "Callable", "dataclass", "field", "abstractmethod", "runtime_checkable"
}


@dataclass(frozen=True)
class CodeToken:
    token_type: PythonTokenType
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"type": self.token_type.value, "value": self.value}


class PythonSyntaxHighlighter:
    """Deterministic, lightweight Python syntax tokenizer and highlighter."""

    @classmethod
    def tokenize_line(cls, line: str) -> List[CodeToken]:
        tokens: List[CodeToken] = []
        i = 0
        n = len(line)

        while i < n:
            # Comment
            if line[i] == "#":
                tokens.append(CodeToken(PythonTokenType.COMMENT, line[i:]))
                break

            # Whitespace
            if line[i].isspace():
                start = i
                while i < n and line[i].isspace():
                    i += 1
                tokens.append(CodeToken(PythonTokenType.PLAIN, line[start:i]))
                continue

            # Decorator
            if line[i] == "@":
                start = i
                i += 1
                while i < n and (line[i].isalnum() or line[i] in "_."):
                    i += 1
                tokens.append(CodeToken(PythonTokenType.DECORATOR, line[start:i]))
                continue

            # String literal (single or double quoted, or triple quoted)
            if line[i] in ("'", '"'):
                quote = line[i]
                start = i
                if line[i:i+3] == quote * 3:
                    quote = quote * 3
                    i += 3
                    while i < n and line[i:i+3] != quote:
                        if line[i] == "\\":
                            i += 2
                        else:
                            i += 1
                    if i < n:
                        i += 3
                else:
                    i += 1
                    while i < n and line[i] != quote:
                        if line[i] == "\\":
                            i += 2
                        else:
                            i += 1
                    if i < n:
                        i += 1
                tokens.append(CodeToken(PythonTokenType.STRING, line[start:i]))
                continue

            # Number
            if line[i].isdigit():
                start = i
                while i < n and (line[i].isdigit() or line[i] in ".xXabcdefABCDEF_"):
                    i += 1
                tokens.append(CodeToken(PythonTokenType.NUMBER, line[start:i]))
                continue

            # Identifier / Keyword / Builtin
            if line[i].isalpha() or line[i] == "_":
                start = i
                while i < n and (line[i].isalnum() or line[i] == "_"):
                    i += 1
                word = line[start:i]

                # Check previous non-whitespace token to see if this is class or def name
                prev_token = None
                for t in reversed(tokens):
                    if t.token_type != PythonTokenType.PLAIN:
                        prev_token = t
                        break

                if prev_token and prev_token.value in ("class", "def"):
                    tokens.append(CodeToken(PythonTokenType.DEF_CLASS, word))
                elif word in PYTHON_KEYWORDS:
                    tokens.append(CodeToken(PythonTokenType.KEYWORD, word))
                elif word in PYTHON_BUILTINS:
                    tokens.append(CodeToken(PythonTokenType.BUILTIN, word))
                else:
                    tokens.append(CodeToken(PythonTokenType.IDENTIFIER, word))
                continue

            # Operators and punctuation
            if line[i] in "+-*/%^&=!<>|&~":
                start = i
                while i < n and line[i] in "+-*/%^&=!<>|&~":
                    i += 1
                tokens.append(CodeToken(PythonTokenType.OPERATOR, line[start:i]))
                continue

            if line[i] in "()[]{},:;?.":
                tokens.append(CodeToken(PythonTokenType.PUNCTUATION, line[i]))
                i += 1
                continue

            # Fallback
            tokens.append(CodeToken(PythonTokenType.PLAIN, line[i]))
            i += 1

        return tokens

    @classmethod
    def tokenize(cls, text: str) -> List[List[CodeToken]]:
        lines = text.split("\n")
        return [cls.tokenize_line(l) for l in lines]


@dataclass
class CodeEditorState:
    """Immutable/mutable state representation of the code editor at a point in time."""
    active_file: str = "src/agent.py"
    content: str = ""
    lines: List[str] = field(default_factory=list)
    cursor_line: int = 1
    cursor_col: int = 1
    selection: Optional[Tuple[int, int, int, int]] = None  # start_l, start_c, end_l, end_c
    highlighted_symbol: Optional[str] = None
    highlighted_lines: List[int] = field(default_factory=list)
    zoom_level: float = 1.0
    scroll_top_line: int = 1
    focus_mode: bool = False
    read_only: bool = False

    def __post_init__(self) -> None:
        if self.content and not self.lines:
            self.lines = self.content.split("\n")
        elif self.lines and not self.content:
            self.content = "\n".join(self.lines)

    @property
    def line_count(self) -> int:
        return max(1, len(self.lines))

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def get_tokenized_lines(self) -> List[List[CodeToken]]:
        return PythonSyntaxHighlighter.tokenize(self.content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_file": self.active_file,
            "content": self.content,
            "content_hash": self.content_hash,
            "line_count": self.line_count,
            "cursor_line": self.cursor_line,
            "cursor_col": self.cursor_col,
            "selection": list(self.selection) if self.selection else None,
            "highlighted_symbol": self.highlighted_symbol,
            "highlighted_lines": list(self.highlighted_lines),
            "zoom_level": self.zoom_level,
            "scroll_top_line": self.scroll_top_line,
            "focus_mode": self.focus_mode,
            "read_only": self.read_only,
        }

    def render_html(self) -> str:
        """Render self-contained HTML representation for browser capture or testing."""
        tokenized_lines = self.get_tokenized_lines()
        rows_html: List[str] = []

        for idx, tokens in enumerate(tokenized_lines, start=1):
            is_cursor_line = (idx == self.cursor_line)
            is_highlighted = (idx in self.highlighted_lines)
            line_classes = ["editor-line"]
            if is_cursor_line:
                line_classes.append("cursor-line")
            if is_highlighted:
                line_classes.append("highlighted-line")

            line_content_parts: List[str] = []
            col_pos = 1
            for tok in tokens:
                escaped_val = html.escape(tok.value)
                is_symbol_match = self.highlighted_symbol and tok.value == self.highlighted_symbol
                tok_classes = [f"tok-{tok.token_type.value}"]
                if is_symbol_match:
                    tok_classes.append("symbol-highlight")

                # Insert cursor if at this position
                if is_cursor_line and col_pos <= self.cursor_col <= col_pos + len(tok.value):
                    offset = self.cursor_col - col_pos
                    before = escaped_val[:offset]
                    after = escaped_val[offset:]
                    line_content_parts.append(
                        f'<span class="{" ".join(tok_classes)}">{before}<span class="cursor-caret"></span>{after}</span>'
                    )
                else:
                    line_content_parts.append(f'<span class="{" ".join(tok_classes)}">{escaped_val}</span>')

                col_pos += len(tok.value)

            line_html = "".join(line_content_parts) or "&nbsp;"
            rows_html.append(
                f'<div class="{" ".join(line_classes)}">'
                f'<span class="line-num">{idx:3d}</span>'
                f'<span class="line-code">{line_html}</span>'
                f'</div>'
            )

        return (
            f'<div class="code-editor" data-file="{html.escape(self.active_file)}" '
            f'data-zoom="{self.zoom_level}" data-focus="{str(self.focus_mode).lower()}">\n'
            f'<div class="editor-header"><span class="tab active">{html.escape(self.active_file)}</span></div>\n'
            f'<div class="editor-body">\n'
            + "\n".join(rows_html) + "\n"
            f'</div>\n</div>'
        )


class CodeEditorRenderer:
    """Stateful renderer and controller for the code editor."""

    def __init__(self, initial_state: Optional[CodeEditorState] = None) -> None:
        self._state = initial_state or CodeEditorState()

    @property
    def state(self) -> CodeEditorState:
        return self._state

    def open_file(self, path: str, content: str = "") -> CodeEditorState:
        lines = content.split("\n") if content else [""]
        self._state = CodeEditorState(
            active_file=path,
            content=content,
            lines=lines,
            cursor_line=1,
            cursor_col=1,
            selection=None,
            highlighted_symbol=None,
            highlighted_lines=[],
            zoom_level=self._state.zoom_level,
            scroll_top_line=1,
            focus_mode=False,
        )
        return self._state

    def set_content(self, content: str) -> CodeEditorState:
        lines = content.split("\n") if content else [""]
        self._state.content = content
        self._state.lines = lines
        return self._state

    def type_text(self, text: str, append: bool = True) -> CodeEditorState:
        if append:
            if self._state.content:
                new_content = self._state.content + "\n" + text if not self._state.content.endswith("\n") else self._state.content + text
            else:
                new_content = text
        else:
            new_content = text

        lines = new_content.split("\n")
        self._state.content = new_content
        self._state.lines = lines
        self._state.cursor_line = len(lines)
        self._state.cursor_col = len(lines[-1]) + 1
        return self._state

    def replace_text(self, new_content: str) -> CodeEditorState:
        return self.set_content(new_content)

    def select_range(self, start_line: int, start_col: int, end_line: int, end_col: int) -> CodeEditorState:
        self._state.selection = (start_line, start_col, end_line, end_col)
        self._state.cursor_line = end_line
        self._state.cursor_col = end_col
        return self._state

    def clear_selection(self) -> CodeEditorState:
        self._state.selection = None
        return self._state

    def highlight_symbol(self, symbol: str) -> CodeEditorState:
        self._state.highlighted_symbol = symbol
        # Also compute lines containing symbol
        matching_lines = [
            idx for idx, line in enumerate(self._state.lines, start=1)
            if symbol in line
        ]
        self._state.highlighted_lines = matching_lines
        return self._state

    def clear_highlights(self) -> CodeEditorState:
        self._state.highlighted_symbol = None
        self._state.highlighted_lines = []
        return self._state

    def scroll_to(self, line: int) -> CodeEditorState:
        self._state.scroll_top_line = max(1, min(line, self._state.line_count))
        return self._state

    def zoom(self, level: float) -> CodeEditorState:
        self._state.zoom_level = max(0.5, min(level, 3.0))
        return self._state

    def set_focus_mode(self, enabled: bool) -> CodeEditorState:
        self._state.focus_mode = enabled
        return self._state

    def apply_action(self, action: Action) -> CodeEditorState:
        """Apply a semantic plan action to update editor state."""
        params = action.params

        if action.action_type == ActionType.OPEN_FILE:
            path = params.get("path", self._state.active_file)
            content = params.get("content", self._state.content)
            self.open_file(path, content)

        elif action.action_type == ActionType.TYPE_TEXT:
            text = params.get("text", "")
            if not text and "source" in params:
                text = params.get("source", "")
            append = params.get("append", True)
            self.type_text(text, append=append)

        elif action.action_type == ActionType.REPLACE_TEXT:
            new_text = params.get("content", params.get("text", ""))
            self.replace_text(new_text)

        elif action.action_type == ActionType.SELECT_RANGE:
            sl = int(params.get("start_line", 1))
            sc = int(params.get("start_col", 1))
            el = int(params.get("end_line", sl))
            ec = int(params.get("end_col", 1))
            self.select_range(sl, sc, el, ec)

        elif action.action_type == ActionType.HIGHLIGHT:
            sym = params.get("symbol")
            if sym:
                self.highlight_symbol(sym)
            lines = params.get("lines")
            if lines and isinstance(lines, list):
                self._state.highlighted_lines = [int(l) for l in lines]

        elif action.action_type == ActionType.SCROLL:
            target_line = int(params.get("target_line", params.get("line", 1)))
            self.scroll_to(target_line)

        elif action.action_type == ActionType.ZOOM:
            lvl = float(params.get("zoom_level", params.get("level", 1.2)))
            self.zoom(lvl)

        elif action.action_type == ActionType.RESET_VIEW:
            self.clear_highlights()
            self.clear_selection()
            self.zoom(1.0)
            self.set_focus_mode(False)

        return self._state
