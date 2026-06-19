"""Abstraction over desktop GUI automation.

Why an adapter:
  - Production uses pyautogui (Windows-only, requires GUI).
  - Tests use MockGuiAdapter that records calls and returns canned data.
  - Tool code only sees the Protocol — never imports pyautogui directly.

The adapter is intentionally synchronous (matches pyautogui's API).
The ToolExecutor runs adapter calls via asyncio.to_thread to avoid
blocking the event loop.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

log = logging.getLogger(__name__)


# ---------- Protocol ----------

@runtime_checkable
class GuiAdapter(Protocol):
    """Interface every GUI backend must implement."""

    def open_app(self, app: str) -> Dict[str, Any]: ...
    def open_url(self, url: str) -> Dict[str, Any]: ...
    def type_text(self, text: str, method: Literal["type", "paste"]) -> Dict[str, Any]: ...
    def hotkey(self, keys: List[str]) -> Dict[str, Any]: ...
    def press_key(self, key: str) -> Dict[str, Any]: ...
    def click_xy(self, x: int, y: int, button: str) -> Dict[str, Any]: ...
    def scroll(self, clicks: int, direction: str) -> Dict[str, Any]: ...
    def screenshot(self, name: Optional[str], out_dir: Path) -> Dict[str, Any]: ...
    def wait(self, seconds: float) -> Dict[str, Any]: ...


# ---------- Mock adapter (for tests) ----------

class MockGuiAdapter:
    """Records every call and returns plausible fake outputs."""

    def __init__(self, *, fail_on: Optional[str] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._fail_on = fail_on
        self._pid_counter = 1000

    def _record(self, tool: str, **kwargs: Any) -> None:
        self.calls.append({"tool": tool, **kwargs})
        if self._fail_on == tool:
            raise RuntimeError(f"mock-induced failure on {tool}")

    # ---- tool impls ----

    def open_app(self, app: str) -> Dict[str, Any]:
        self._record("open_app", app=app)
        self._pid_counter += 1
        return {"app": app, "pid": self._pid_counter}

    def open_url(self, url: str) -> Dict[str, Any]:
        self._record("open_url", url=url)
        return {"url": url}

    def type_text(self, text: str, method: str) -> Dict[str, Any]:
        self._record("type_text", text=text, method=method, length=len(text))
        return {"length": len(text), "method": method}

    def hotkey(self, keys: List[str]) -> Dict[str, Any]:
        self._record("hotkey", keys=keys)
        return {"keys": keys}

    def press_key(self, key: str) -> Dict[str, Any]:
        self._record("press_key", key=key)
        return {"key": key}

    def click_xy(self, x: int, y: int, button: str) -> Dict[str, Any]:
        self._record("click_xy", x=x, y=y, button=button)
        return {"x": x, "y": y, "button": button}

    def scroll(self, clicks: int, direction: str) -> Dict[str, Any]:
        self._record("scroll", clicks=clicks, direction=direction)
        return {"clicks": clicks, "direction": direction}

    def screenshot(self, name: Optional[str], out_dir: Path) -> Dict[str, Any]:
        # No real file; the executor treats "path" as opaque string.
        path = str(out_dir / f"{name or 'screenshot'}.png")
        self._record("screenshot", name=name, path=path)
        return {"path": path, "width": 1920, "height": 1080}

    def wait(self, seconds: float) -> Dict[str, Any]:
        # Don't actually sleep in tests — return immediately.
        self._record("wait", seconds=seconds)
        return {"seconds": seconds}

# ---------- Real adapter (pyautogui + subprocess) ----------

# Windows-friendly alias map for `open_app`. Add more if needed.
_OPEN_APP_ALIASES = {
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "mspaint": ["mspaint.exe"],
    "edge": ["msedge.exe"],
    "explorer": ["explorer.exe"],
}


def _has_non_ascii(s: str) -> bool:
    return any(ord(c) > 127 for c in s)


class PyAutoGuiAdapter:
    """Production adapter wrapping pyautogui + subprocess.

    pyautogui import is deferred to runtime so unit tests don't need a
    display / Windows session.
    """

    def __init__(self) -> None:
        self._pg = None
        self._pc = None
        self._pyautogui_available: Optional[bool] = None

    def _ensure_pyautogui(self) -> None:
        if self._pyautogui_available is False:
            raise RuntimeError(
                "pyautogui is not available in this environment "
                "(no GUI session or dependency missing)"
            )
        if self._pyautogui_available is True:
            return
        try:
            import pyautogui  # type: ignore
            import pyperclip  # type: ignore
            self._pg = pyautogui
            self._pc = pyperclip
            self._pyautogui_available = True
        except Exception as exc:
            log.warning("pyautogui import failed: %s", exc)
            self._pyautogui_available = False
            raise RuntimeError(
                "pyautogui is not available in this environment"
            ) from exc

    # ---- open_app: subprocess (no pyautogui needed) ----

    def open_app(self, app: str) -> Dict[str, Any]:
        cmd = _OPEN_APP_ALIASES.get(app)
        if cmd is None:
            raise ValueError(
                f"unknown app '{app}'. "
                f"Supported: {sorted(_OPEN_APP_ALIASES)}"
            )
        proc = subprocess.Popen(cmd, shell=False)
        return {"app": app, "pid": proc.pid}

    # ---- open_url: subprocess `start msedge <url>` ----

    def open_url(self, url: str) -> Dict[str, Any]:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(f"url must be http(s): {url!r}")
        # On Windows, `start` is a cmd builtin; `start "" <url>` lets
        # the shell pick the default handler. We force Edge here per
        # the MVP plan.
        subprocess.Popen(
            ["cmd", "/c", "start", "", "msedge", url],
            shell=False,
        )
        return {"url": url, "browser": "msedge"}

    # ---- type_text: paste via clipboard if non-ASCII, else pyautogui.write ----

    def type_text(self, text: str, method: str) -> Dict[str, Any]:
        self._ensure_pyautogui()
        if not text:
            return {"length": 0, "method": method}

        # Vietnamese / any non-ASCII -> always paste via clipboard.
        if _has_non_ascii(text) or method == "paste":
            self._pc.copy(text)  # type: ignore[union-attr]
            self._pg.hotkey("ctrl", "v")  # type: ignore[union-attr]
            return {"length": len(text), "method": "paste"}

        # Pure ASCII + method=type -> pyautogui.write char by char.
        self._pg.write(text, interval=0.01)  # type: ignore[union-attr]
        return {"length": len(text), "method": "type"}

    # ---- hotkey / press_key / click_xy / scroll ----

    def hotkey(self, keys: List[str]) -> Dict[str, Any]:
        self._ensure_pyautogui()
        if not keys:
            raise ValueError("hotkey requires at least one key")
        self._pg.hotkey(*keys)  # type: ignore[union-attr]
        return {"keys": keys}

    def press_key(self, key: str) -> Dict[str, Any]:
        self._ensure_pyautogui()
        if not key:
            raise ValueError("press_key requires a non-empty key")
        self._pg.press(key)  # type: ignore[union-attr]
        return {"key": key}

    def click_xy(self, x: int, y: int, button: str) -> Dict[str, Any]:
        self._ensure_pyautogui()
        self._pg.click(x=x, y=y, button=button)  # type: ignore[union-attr]
        return {"x": x, "y": y, "button": button}

    def scroll(self, clicks: int, direction: str) -> Dict[str, Any]:
        self._ensure_pyautogui()
        # PyAutoGUI scroll: positive = up, negative = down (wheel away = up).
        amount = clicks if direction == "up" else -clicks
        if direction in ("left", "right"):
            amount = clicks if direction == "right" else -clicks
            self._pg.hscroll(amount)  # type: ignore[union-attr]
        else:
            self._pg.scroll(amount)  # type: ignore[union-attr]
        return {"clicks": clicks, "direction": direction}

    # ---- screenshot ----

    def screenshot(self, name: Optional[str], out_dir: Path) -> Dict[str, Any]:
        self._ensure_pyautogui()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = f"{name or 'screenshot'}-{ts}.png"
        path = out_dir / fname
        img = self._pg.screenshot()  # type: ignore[union-attr]
        img.save(path)
        return {"path": str(path), "width": img.width, "height": img.height}

    # ---- wait ----

    def wait(self, seconds: float) -> Dict[str, Any]:
        if seconds <= 0:
            raise ValueError("wait.seconds must be > 0")
        time.sleep(seconds)
        return {"seconds": seconds}


def make_default_adapter() -> GuiAdapter:
    """Build the production adapter. Tests should construct MockGuiAdapter directly."""
    return PyAutoGuiAdapter()
