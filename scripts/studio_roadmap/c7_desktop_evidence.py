"""Capture fail-closed evidence from the real Tauri C7 desktop surface."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.studio_roadmap.c7_slice_harness import SliceError, _get

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = REPO_ROOT / "apps" / "desktop"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=DESKTOP_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SliceError(f"desktop tool unavailable ({command[0]}): {exc}") from exc
    if result.returncode != 0:
        raise SliceError(
            f"desktop tool failed ({' '.join(command)}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return (result.stdout or result.stderr).strip().splitlines()[0]


def _powershell(script: str, *, timeout: float = 30) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=DESKTOP_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise SliceError(f"desktop evidence PowerShell failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _window() -> Optional[Dict[str, Any]]:
    raw = _powershell(
        "$p=Get-Process -Name 'windagent-desktop' -ErrorAction SilentlyContinue | "
        "Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -First 1; "
        "if ($p) {$p | Select-Object Id,MainWindowHandle,MainWindowTitle | "
        "ConvertTo-Json -Compress}",
    )
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SliceError(f"desktop window probe returned invalid JSON: {raw}") from exc
    return value if isinstance(value, dict) else None


def _accessible_text(window_handle: int) -> list[str]:
    raw = _powershell(
        "Add-Type -AssemblyName UIAutomationClient; "
        "$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]"
        f"{window_handle}); "
        "$items=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants, "
        "[System.Windows.Automation.Condition]::TrueCondition); "
        "$names=@(); foreach($item in $items){$name=$item.Current.Name; "
        "if($name -and $name.Trim()){$names += $name.Trim()}}; "
        "$names | Select-Object -Unique | ConvertTo-Json -Compress",
    )
    if not raw:
        return []
    value = json.loads(raw)
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value] if isinstance(value, list) else []


def _capture_window(window_handle: int, path: Path) -> None:
    escaped = str(path).replace("'", "''")
    _powershell(
        "Add-Type -AssemblyName System.Drawing; "
        "Add-Type @'\nusing System;\nusing System.Runtime.InteropServices;\n"
        "public class C7Win32 { [DllImport(\"user32.dll\")] public static extern "
        "bool GetWindowRect(IntPtr hWnd, out RECT r); public struct RECT { public int "
        "Left; public int Top; public int Right; public int Bottom; }}\n'@; "
        f"$h=[IntPtr]{window_handle}; $r=New-Object C7Win32+RECT; "
        "if(-not [C7Win32]::GetWindowRect($h,[ref]$r)){throw 'GetWindowRect failed'}; "
        "$w=$r.Right-$r.Left; $hgt=$r.Bottom-$r.Top; "
        "if($w -lt 100 -or $hgt -lt 100){throw 'invalid desktop window bounds'}; "
        "$bmp=New-Object System.Drawing.Bitmap($w,$hgt); "
        "$g=[System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($r.Left,$r.Top,0,0,$bmp.Size); "
        f"$bmp.Save('{escaped}',[System.Drawing.Imaging.ImageFormat]::Png); "
        "$g.Dispose(); $bmp.Dispose()",
    )
    if not path.is_file() or path.stat().st_size < 10_000:
        raise SliceError("real Tauri screenshot was not captured or is unexpectedly empty")


def _stop_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    else:  # pragma: no cover - current certification host is Windows
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def probe_c7_desktop_environment() -> Dict[str, str]:
    """Fail before Series creation unless the real Tauri toolchain is available."""

    if sys.platform != "win32":
        raise SliceError(f"real Tauri screenshot capture is unsupported on {sys.platform}")
    npm = "npm.cmd"
    return {
        "node": _version(["node", "--version"]),
        "npm": _version([npm, "--version"]),
        "cargo": _version(["cargo", "--version"]),
        "rustc": _version(["rustc", "--version"]),
        "tauri_cli": _version([npm, "run", "tauri", "--", "--version"]),
    }


def capture_c7_desktop_evidence(
    *,
    api_base: str,
    episode_id: str,
    run_id: str,
    output_dir: Path,
    timeout_seconds: float = 300,
    health_check: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """Launch Tauri, prove server-backed visible state, and capture its window."""

    guard = health_check or (lambda: None)
    guard()
    tool_versions = probe_c7_desktop_environment()
    guard()
    status, episode = _get(api_base, f"/api/v3/studio/episodes/{episode_id}")
    if status != 200:
        raise SliceError(f"desktop evidence episode read failed: {status} {episode}")
    if episode.get("state") != "READY_FOR_PRODUCTION":
        raise SliceError("desktop evidence requires a READY_FOR_PRODUCTION episode")

    npm = "npm.cmd"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = REPO_ROOT / ".tmp" / "studio-c7" / "desktop"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "tauri.stdout.log"
    stderr_path = log_dir / "tauri.stderr.log"
    screenshot_path = output_dir / "desktop-tauri.png"
    command = [npm, "run", "tauri", "--", "dev", "--no-watch"]
    env = os.environ.copy()
    env.update(
        {
            "VITE_API_BASE": api_base,
            "VITE_STUDIO_CERTIFICATION_EPISODE_ID": episode_id,
        }
    )
    started_at = _utc_now()
    window: Optional[Dict[str, Any]] = None
    names: list[str] = []
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=DESKTOP_ROOT,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        try:
            deadline = time.monotonic() + timeout_seconds
            expected = {
                str(episode.get("title")),
                "READY_FOR_PRODUCTION",
                run_id,
                "Artifacts",
                "ScreenplayDraft",
                "ReviewReport",
            }
            while time.monotonic() < deadline:
                guard()
                if process.poll() is not None:
                    raise SliceError(
                        f"Tauri dev process exited before evidence: {process.returncode}"
                    )
                window = _window()
                if window:
                    names = _accessible_text(int(window["MainWindowHandle"]))
                    visible = "\n".join(names)
                    if all(token in visible for token in expected):
                        break
                time.sleep(1)
            else:
                raise SliceError(
                    "Tauri window did not expose all required C7 server-backed text: "
                    f"{sorted(expected - set(token for token in expected if token in chr(10).join(names)))}"
                )
            _capture_window(int(window["MainWindowHandle"]), screenshot_path)
            ready_at = _utc_now()
        finally:
            _stop_tree(process)
            ended_at = _utc_now()

    screenshot_hash = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
    return {
        "surface": "real-tauri-webview2",
        "platform": platform.platform(),
        "command": command,
        "cli_pid": process.pid,
        "app_pid": int(window["Id"]) if window else None,
        "window_title": window.get("MainWindowTitle") if window else None,
        "started_at": started_at,
        "ready_at": ready_at,
        "ended_at": ended_at,
        "api_base": api_base,
        "episode_id": episode_id,
        "run_id": run_id,
        "visible_accessibility_text": names,
        "required_visible_text": sorted(expected),
        "screenshot_path": screenshot_path.relative_to(REPO_ROOT).as_posix(),
        "screenshot_sha256": screenshot_hash,
        "stdout_log": stdout_path.relative_to(REPO_ROOT).as_posix(),
        "stderr_log": stderr_path.relative_to(REPO_ROOT).as_posix(),
        "tool_versions": tool_versions,
        "pass": True,
    }


__all__ = ["capture_c7_desktop_evidence", "probe_c7_desktop_environment"]
