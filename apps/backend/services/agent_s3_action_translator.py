"""Agent-S3 raw-action translator.

This is the **safety boundary** between the upstream Agent-S3 SDK
(which emits raw Python code -- typically a sequence of
``pyautogui.click(...)`` / ``pyautogui.typewrite(...)`` / ``time.sleep(...)``
calls) and WindAgent's whitelist-based tool executor.

Rules:

  1. **Never exec the raw code.** We parse it as text and extract
     recognised patterns only.
  2. **Whitelist-based.** Every recognised pattern maps to one of the
     existing WindAgent tools (see ``services/tool_registry.py``).
  3. **Reject by default.** Anything that isn't on the whitelist --
     ``import``, ``open(``, ``subprocess``, ``os.system``, file
     writes outside our screenshot dir, custom functions, etc. --
     is rejected and reported in the ``rejected`` list.
  4. **Audit-friendly.** Both accepted and rejected lines are
     returned so the caller can mirror them into the JSONL audit log
     (see ``services/event_hooks.py``).

The translator is **pure** -- no I/O, no globals, no logging -- so it
is straightforward to unit test. The runtime adapter layer is in
``agent_s3_adapter.py``.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------- Result dataclasses ----------

@dataclass(frozen=True)
class TranslatedAction:
    """A single Agent-S3 line mapped to a WindAgent tool call.

    ``confidence`` is informational -- the caller may downgrade it
    based on its own policy (e.g. always require confirmation for
    ``click_xy`` even though the upstream said ``high``).
    """

    tool_name: str
    params: Dict[str, Any]
    source_line: str
    confidence: str  # "high" | "medium" | "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "params": dict(self.params),
            "source_line": self.source_line,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class RejectedAction:
    """A line that did not match any whitelist pattern.

    ``reason`` is short and human-readable so the audit log + UI can
    surface it. The original line is preserved verbatim so the
    operator can debug.
    """

    source_line: str
    reason: str
    line_number: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_line": self.source_line,
            "reason": self.reason,
            "line_number": self.line_number,
        }


@dataclass(frozen=True)
class TranslationResult:
    accepted: List[TranslatedAction]
    rejected: List[RejectedAction]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": [a.to_dict() for a in self.accepted],
            "rejected": [r.to_dict() for r in self.rejected],
        }


# ---------- Helpers ----------

# Match a literal string argument: "..." or '...' (no f-strings, no
# escapes other than \\ and \'; we don't try to be exhaustive because
# Agent-S3's emitted code is LLM-generated and can be wild).
_STR_LIT = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''

# Whitelist patterns. Order matters only for readability -- the
# translator tries them all and picks the first match. Confidence
# reflects how unambiguous the mapping is.

# click / rightClick / doubleClick / middleClick / tripleClick -- the
# method name implies the button for everything except plain
# pyautogui.click(...) which defaults to left.
_RE_CLICK_VARIANT = re.compile(
    r"^\s*pyautogui\.(?P<method>"
    r"leftClick|rightClick|middleClick|doubleClick|tripleClick"
    r")"
    r"\(\s*"
    r"(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)"
    r"(?:\s*,\s*(?P<button>['\"][a-zA-Z]+['\"]|\d+))?"
    r"\s*\)\s*$"
)
_RE_CLICK_XY = re.compile(
    r"^\s*pyautogui\.click\(\s*"
    r"(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)"
    r"(?:\s*,\s*(?P<button>['\"][a-zA-Z]+['\"]))?"
    r"\s*\)\s*$"
)

# typewrite / write (newer alias)
_RE_TYPEWRITE = re.compile(
    r"^\s*pyautogui\.(?:typewrite|write)\(\s*"
    r"(?P<text>" + _STR_LIT + r")"
    r"(?:\s*,\s*interval\s*=\s*(?P<interval>-?\d+(?:\.\d+)?))?"
    r"\s*\)\s*$"
)

# hotkey
_RE_HOTKEY = re.compile(
    r"^\s*pyautogui\.hotkey\(\s*(?P<keys>.+?)\s*\)\s*$"
)

# press
_RE_PRESS = re.compile(
    r"^\s*pyautogui\.press\(\s*(?P<key>" + _STR_LIT + r")\s*\)\s*$"
)

# scroll (vertical) / hscroll (horizontal) / vscroll (alias)
_RE_SCROLL = re.compile(
    r"^\s*pyautogui\.(?:scroll|vscroll)\(\s*(?P<amount>-?\d+)\s*\)\s*$"
)
_RE_HSCROLL = re.compile(
    r"^\s*pyautogui\.hscroll\(\s*(?P<amount>-?\d+)\s*\)\s*$"
)

# moveTo -> not a tool call, but useful as a no-op anchor (we drop it
# and report the rejection with reason="no_tool_mapping").
_RE_MOVETO = re.compile(
    r"^\s*pyautogui\.moveTo\("
)

# sleep
_RE_SLEEP = re.compile(
    r"^\s*(?:time\.sleep|pyautogui\.PAUSE\s*=\s*-?\d+(?:\.\d+)?)\s*"
    r"(?:\(\s*(?P<seconds>-?\d+(?:\.\d+)?)\s*\))?\s*$"
)

# screenshot
_RE_SCREENSHOT = re.compile(
    r"^\s*pyautogui\.screenshot\(\s*(?:" + _STR_LIT + r")?\s*\)\s*$"
)


# Patterns whose match ALWAYS means rejection. These are common LLM
# slip-ups -- a model trying to "be helpful" by reading / writing
# arbitrary files, calling out to the OS, etc. We surface them
# verbatim so the operator knows the upstream model attempted them.
_DENY_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\s*import\s+"), "import statement"),
    (re.compile(r"^\s*from\s+\S+\s+import\s+"), "import statement"),
    (re.compile(r"\bopen\s*\("), "open() call"),
    (re.compile(r"\bsubprocess\b"), "subprocess"),
    (re.compile(r"\bos\.system\b"), "os.system"),
    (re.compile(r"\bos\.popen\b"), "os.popen"),
    (re.compile(r"\bexec\s*\("), "exec()"),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\b__import__\s*\("), "__import__()"),
    (re.compile(r"\brequests\.\b"), "requests.*"),
    (re.compile(r"\burllib\b"), "urllib"),
    (re.compile(r"\bsocket\b"), "socket"),
]


# ---------- Translator ----------

def translate(raw_actions: List[str]) -> TranslationResult:
    """Translate a list of Agent-S3 action strings into WindAgent tool calls.

    Each element of ``raw_actions`` is one line of Python code as
    emitted by Agent-S3's planner. We process line-by-line; comments
    and blank lines are silently ignored. Multi-line statements
    (e.g. ``if`` blocks, function defs) are rejected with
    ``reason="multi_line_statement_unsupported"``.

    The translator is **deterministic**: same input -> same output.
    """
    accepted: List[TranslatedAction] = []
    rejected: List[RejectedAction] = []

    for idx, raw in enumerate(raw_actions):
        line = raw.rstrip("\n")
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        # Cheap deny-by-pattern check first -- catches the obvious
        # bad cases before we bother trying to match.
        for pat, label in _DENY_PATTERNS:
            if pat.search(stripped):
                rejected.append(RejectedAction(
                    source_line=line,
                    reason=f"denied: {label}",
                    line_number=idx + 1,
                ))
                break
        else:
            translated = _translate_line(stripped, line)
            if translated is None:
                rejected.append(RejectedAction(
                    source_line=line,
                    reason="no whitelist match",
                    line_number=idx + 1,
                ))
            else:
                accepted.append(translated)

    return TranslationResult(accepted=accepted, rejected=rejected)


# ---------- Internals ----------

def _translate_line(stripped: str, original: str) -> Optional[TranslatedAction]:
    """Try to map a single line to a TranslatedAction.

    Returns ``None`` if no whitelist pattern matched.
    """
    # click variants (leftClick / rightClick / middleClick / ...)
    m = _RE_CLICK_VARIANT.match(stripped)
    if m:
        x = int(m.group("x"))
        y = int(m.group("y"))
        method = m.group("method")
        # Method name implies the button unless the caller passed an
        # explicit button argument.
        button_raw = m.group("button")
        if button_raw is not None:
            button = _parse_button(button_raw, default="left")
        else:
            button = _method_to_button(method)
        return TranslatedAction(
            tool_name="click_xy",
            params={"x": x, "y": y, "button": button},
            source_line=original,
            confidence="high",
        )

    m = _RE_CLICK_XY.match(stripped)
    if m:
        x = int(m.group("x"))
        y = int(m.group("y"))
        button = _parse_button(m.group("button"), default="left")
        return TranslatedAction(
            tool_name="click_xy",
            params={"x": x, "y": y, "button": button},
            source_line=original,
            confidence="high",
        )

    # typewrite / write
    m = _RE_TYPEWRITE.match(stripped)
    if m:
        text = _unquote(m.group("text"))
        if not text:
            return TranslatedAction(
                tool_name="type_text",
                params={"text": "", "method": "type"},
                source_line=original,
                confidence="medium",
            )
        # Non-ASCII -> paste via clipboard (matches PyAutoGuiAdapter).
        method = "paste" if any(ord(c) > 127 for c in text) else "type"
        return TranslatedAction(
            tool_name="type_text",
            params={"text": text, "method": method},
            source_line=original,
            confidence="high",
        )

    # hotkey
    m = _RE_HOTKEY.match(stripped)
    if m:
        keys = _parse_str_list(m.group("keys"))
        if not keys:
            return None
        return TranslatedAction(
            tool_name="hotkey",
            params={"keys": keys},
            source_line=original,
            confidence="high",
        )

    # press
    m = _RE_PRESS.match(stripped)
    if m:
        key = _unquote(m.group("key"))
        if not key:
            return None
        return TranslatedAction(
            tool_name="press_key",
            params={"key": key},
            source_line=original,
            confidence="high",
        )

    # scroll
    m = _RE_SCROLL.match(stripped)
    if m:
        amount = int(m.group("amount"))
        direction = "up" if amount > 0 else "down"
        clicks = abs(amount)
        return TranslatedAction(
            tool_name="scroll",
            params={"clicks": clicks, "direction": direction},
            source_line=original,
            confidence="high",
        )

    # hscroll
    m = _RE_HSCROLL.match(stripped)
    if m:
        amount = int(m.group("amount"))
        direction = "right" if amount > 0 else "left"
        return TranslatedAction(
            tool_name="scroll",
            params={"clicks": abs(amount), "direction": direction},
            source_line=original,
            confidence="high",
        )

    # sleep
    m = _RE_SLEEP.match(stripped)
    if m:
        secs_str = m.group("seconds")
        if secs_str is None:
            return None
        secs = float(secs_str)
        # WindAgent's ``wait`` tool caps at 60s; clamp to keep the
        # contract. Anything above 60 is reported as a rejection so
        # the user can manually insert a longer pause if they want.
        if secs <= 0 or secs > 60:
            return None
        return TranslatedAction(
            tool_name="wait",
            params={"seconds": secs},
            source_line=original,
            confidence="high",
        )

    # screenshot -- parameterless; the executor picks a name.
    if _RE_SCREENSHOT.match(stripped):
        return TranslatedAction(
            tool_name="screenshot",
            params={"name": None},
            source_line=original,
            confidence="medium",
        )

    # moveTo -- intentional no-op.
    if _RE_MOVETO.match(stripped):
        return None  # caller will see a rejection with reason="no_tool_mapping"

    # Anything else -- try the AST as a last-ditch sanity check.
    # We only accept Expr -> Call of an allowed attribute. Anything
    # else (Assign, FunctionDef, If, ...) is rejected.
    if not _is_simple_call(stripped):
        return None
    return None


def _is_simple_call(line: str) -> bool:
    """Return True if ``line`` parses as a single-expression Call."""
    try:
        tree = ast.parse(line, mode="exec")
    except SyntaxError:
        return False
    if not tree.body or len(tree.body) != 1:
        return False
    stmt = tree.body[0]
    if not isinstance(stmt, ast.Expr):
        return False
    return isinstance(stmt.value, ast.Call)


def _unquote(s: Optional[str]) -> str:
    """Strip matching quote pair and interpret common backslash escapes.

    We do NOT use ``ast.literal_eval`` here because the input is not
    trusted -- and ``ast.literal_eval`` would also accept numbers,
    tuples, etc., which we don't want to silently accept.
    """
    if s is None or len(s) < 2:
        return ""
    if s[0] != s[-1] or s[0] not in ("'", '"'):
        return ""
    body = s[1:-1]
    # Only the minimal set Agent-S3 actually emits.
    return (
        body
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _parse_str_list(raw: str) -> List[str]:
    """Parse ``'ctrl', 'c'``-style argument list into a list of strs.

    Falls back to splitting on commas when the AST-based parse fails
    (e.g. when the upstream emitted `pyautogui.hotkey("ctrl+c")` as a
    single combined string).
    """
    try:
        # Wrap in parens to make it a tuple literal; ast will accept.
        tree = ast.parse(f"({raw})", mode="eval")
    except SyntaxError:
        # Single string with separators like 'ctrl+c' or 'ctrl+c+v'.
        if raw.startswith(("'", '"')) and raw.endswith(("'", '"')) and len(raw) >= 2:
            value = _unquote(raw)
            return [value] if value else []
        return []
    node = tree.body  # type: ignore[attr-defined]
    if isinstance(node, ast.Tuple):
        out: List[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
            else:
                return []
        return out
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        # Single string argument.
        return [node.value]
    return []


def _parse_button(raw: Optional[str], default: str) -> str:
    """Map a pyautogui button argument to ``left`` / ``right`` / ``middle``."""
    if raw is None:
        return default
    s = raw.strip().strip("'\"")
    if s in ("left", "right", "middle"):
        return s
    # Numeric codes used by pyautogui: 1=left, 2=middle, 3=right.
    if s == "1":
        return "left"
    if s == "2":
        return "middle"
    if s == "3":
        return "right"
    return default


def _method_to_button(method: str) -> str:
    """Infer the WindAgent button from a pyautogui *Click method name."""
    if method == "rightClick":
        return "right"
    if method == "middleClick":
        return "middle"
    # leftClick / doubleClick / tripleClick are all left-button.
    return "left"


__all__ = [
    "TranslationResult",
    "TranslatedAction",
    "RejectedAction",
    "translate",
]