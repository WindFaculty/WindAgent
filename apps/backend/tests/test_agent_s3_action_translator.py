"""Tests for ``services.agent_s3_action_translator``.

These are the **safety boundary** tests -- if a regression here would
let Agent-S3 execute raw code, this file will catch it. Each test is
written so that the *expected* translation is unambiguous.

The translator is pure (no I/O, no globals, no logging) so we don't
need any fixtures beyond ``pytest``.
"""
from __future__ import annotations

import pytest

from services.agent_s3_action_translator import (
    RejectedAction,
    TranslatedAction,
    TranslationResult,
    translate,
)


# ---------- Happy path: every recognised pattern ----------

def test_translate_pyautogui_click_xy():
    out = translate(["pyautogui.click(500, 300)"])
    assert len(out.accepted) == 1
    a = out.accepted[0]
    assert a.tool_name == "click_xy"
    assert a.params == {"x": 500, "y": 300, "button": "left"}
    assert a.confidence == "high"
    assert out.rejected == []


def test_translate_pyautogui_click_with_button():
    out = translate(["pyautogui.click(100, 100, 'right')"])
    a = out.accepted[0]
    assert a.tool_name == "click_xy"
    assert a.params == {"x": 100, "y": 100, "button": "right"}


def test_translate_right_click():
    out = translate(["pyautogui.rightClick(10, 20)"])
    a = out.accepted[0]
    assert a.tool_name == "click_xy"
    assert a.params == {"x": 10, "y": 20, "button": "right"}


def test_translate_double_click_is_left():
    out = translate(["pyautogui.doubleClick(1, 2)"])
    a = out.accepted[0]
    assert a.tool_name == "click_xy"
    # doubleClick == left button (we don't track click count in MVP).
    assert a.params["button"] == "left"


def test_translate_middle_click():
    out = translate(["pyautogui.middleClick(7, 8)"])
    a = out.accepted[0]
    assert a.tool_name == "click_xy"
    assert a.params["button"] == "middle"


def test_translate_typewrite_ascii_uses_type_method():
    out = translate(["pyautogui.typewrite('hello')"])
    a = out.accepted[0]
    assert a.tool_name == "type_text"
    assert a.params == {"text": "hello", "method": "type"}


def test_translate_typewrite_double_quoted():
    out = translate(['pyautogui.write("world")'])
    a = out.accepted[0]
    assert a.tool_name == "type_text"
    assert a.params["text"] == "world"


def test_translate_typewrite_non_ascii_uses_paste_method():
    out = translate(["pyautogui.typewrite('Xin chào')"])
    a = out.accepted[0]
    assert a.tool_name == "type_text"
    assert a.params["text"] == "Xin chào"
    assert a.params["method"] == "paste"


def test_translate_typewrite_with_interval_ignored_but_still_maps():
    # interval=... is not a WindAgent concept; we still produce the
    # right tool call so the action isn't lost.
    out = translate(["pyautogui.typewrite('hi', interval=0.05)"])
    a = out.accepted[0]
    assert a.tool_name == "type_text"
    assert a.params["text"] == "hi"


def test_translate_hotkey_single_string():
    out = translate(["pyautogui.hotkey('ctrl', 'c')"])
    a = out.accepted[0]
    assert a.tool_name == "hotkey"
    assert a.params == {"keys": ["ctrl", "c"]}


def test_translate_hotkey_three_keys():
    out = translate(['pyautogui.hotkey("ctrl", "shift", "esc")'])
    a = out.accepted[0]
    assert a.params == {"keys": ["ctrl", "shift", "esc"]}


def test_translate_press():
    out = translate(["pyautogui.press('enter')"])
    a = out.accepted[0]
    assert a.tool_name == "press_key"
    assert a.params == {"key": "enter"}


def test_translate_scroll_positive_is_up():
    out = translate(["pyautogui.scroll(5)"])
    a = out.accepted[0]
    assert a.tool_name == "scroll"
    assert a.params == {"clicks": 5, "direction": "up"}


def test_translate_scroll_negative_is_down():
    out = translate(["pyautogui.scroll(-3)"])
    a = out.accepted[0]
    assert a.tool_name == "scroll"
    assert a.params == {"clicks": 3, "direction": "down"}


def test_translate_hscroll_positive_is_right():
    out = translate(["pyautogui.hscroll(2)"])
    a = out.accepted[0]
    assert a.tool_name == "scroll"
    assert a.params == {"clicks": 2, "direction": "right"}


def test_translate_hscroll_negative_is_left():
    out = translate(["pyautogui.hscroll(-1)"])
    a = out.accepted[0]
    assert a.tool_name == "scroll"
    assert a.params == {"clicks": 1, "direction": "left"}


def test_translate_sleep():
    out = translate(["time.sleep(2.5)"])
    a = out.accepted[0]
    assert a.tool_name == "wait"
    assert a.params == {"seconds": 2.5}


def test_translate_screenshot():
    out = translate(["pyautogui.screenshot('foo.png')"])
    a = out.accepted[0]
    assert a.tool_name == "screenshot"
    assert a.params == {"name": None}


def test_translate_screenshot_no_arg():
    out = translate(["pyautogui.screenshot()"])
    a = out.accepted[0]
    assert a.tool_name == "screenshot"


# ---------- Safety: denial patterns ----------

@pytest.mark.parametrize("line", [
    "import os",
    "from subprocess import call",
    "open('/etc/passwd')",
    "subprocess.Popen(['ls'])",
    "os.system('rm -rf /')",
    "os.popen('ls')",
    "exec('print(1)')",
    "eval('1+1')",
    "__import__('os')",
    "requests.get('http://evil')",
    "urllib.request.urlopen('http://evil')",
    "socket.socket()",
])
def test_translate_denies_dangerous_calls(line):
    out = translate([line])
    assert out.accepted == []
    assert len(out.rejected) == 1
    assert out.rejected[0].line_number == 1
    assert "denied" in out.rejected[0].reason


def test_translate_rejects_unrecognised_pyautogui():
    # moveTo has no WindAgent equivalent -- should be rejected (not
    # silently swallowed).
    out = translate(["pyautogui.moveTo(100, 100)"])
    assert out.accepted == []
    assert out.rejected and out.rejected[0].line_number == 1


def test_translate_rejects_random_python():
    out = translate(["x = 1 + 2"])
    assert out.accepted == []
    assert out.rejected and "no whitelist match" in out.rejected[0].reason


def test_translate_rejects_arbitrary_function_call():
    out = translate(["do_evil_thing('a', 'b')"])
    assert out.accepted == []
    assert out.rejected


# ---------- Clamping / clamping guards ----------

def test_translate_sleep_too_long_is_rejected():
    out = translate(["time.sleep(120)"])
    assert out.accepted == []
    assert out.rejected


def test_translate_sleep_zero_or_negative_is_rejected():
    assert translate(["time.sleep(0)"]).accepted == []
    assert translate(["time.sleep(-1)"]).accepted == []


# ---------- Multiple lines ----------

def test_translate_mixed_batch():
    actions = [
        "# open notepad",  # comment
        "",                # blank
        "pyautogui.click(100, 200)",
        "pyautogui.typewrite('hello')",
        "time.sleep(1)",
        "pyautogui.screenshot()",
        "import os",        # denied
        "x = 1 + 2",        # rejected
        "pyautogui.hotkey('ctrl', 's')",
    ]
    out = translate(actions)
    tool_names = [a.tool_name for a in out.accepted]
    assert tool_names == [
        "click_xy", "type_text", "wait", "screenshot", "hotkey"
    ]
    # Two rejections: import and assignment.
    assert len(out.rejected) == 2
    assert out.rejected[0].line_number == 7
    assert out.rejected[1].line_number == 8


def test_translate_empty_input_returns_empty_lists():
    out = translate([])
    assert out.accepted == []
    assert out.rejected == []


# ---------- Result dataclass serialisation ----------

def test_translation_result_to_dict():
    out = translate(["pyautogui.click(1, 2)"])
    d = out.to_dict()
    assert "accepted" in d and "rejected" in d
    assert d["accepted"][0]["tool_name"] == "click_xy"


def test_translated_action_to_dict():
    a = TranslatedAction(
        tool_name="click_xy",
        params={"x": 1, "y": 2, "button": "left"},
        source_line="pyautogui.click(1, 2)",
        confidence="high",
    )
    d = a.to_dict()
    assert d["tool_name"] == "click_xy"
    assert d["params"]["x"] == 1
    assert d["confidence"] == "high"


def test_rejected_action_to_dict():
    r = RejectedAction(
        source_line="import os",
        reason="denied: import statement",
        line_number=42,
    )
    d = r.to_dict()
    assert d["line_number"] == 42
    assert "import" in d["reason"]


# ---------- Sanity: never exec anything ----------

def test_translator_does_not_call_exec(monkeypatch):
    """The translator module must never invoke ``exec`` -- assert by
    monkey-patching builtins.exec and ensuring no test calls it."""
    import builtins
    calls: list = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("translator called exec()!")

    monkeypatch.setattr(builtins, "exec", _spy)
    translate([
        "import os",
        "exec('print(1)')",
        "pyautogui.click(1, 2)",
    ])
    assert calls == []