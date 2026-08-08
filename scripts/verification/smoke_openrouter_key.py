"""Smoke test: extract OpenRouter key from run_codex_cli_openrouter.ps1 (never
printed), call deepseek/deepseek-v4-flash-0731 once, print only response shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parents[2]
PS1 = _ROOT / "run_codex_cli_openrouter.ps1"
MODEL = "deepseek/deepseek-v4-flash-0731"
URL = "https://openrouter.ai/api/v1/chat/completions"


def load_key() -> str:
    m = re.search(r'\$NaraApiKey\s*=\s*"([^"]+)"', PS1.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("no key line in ps1")
    key = m.group(1).strip()
    if "REPLACE_WITH_YOUR_REAL" in key or "..." in key or len(key) < 20:
        raise SystemExit("key looks like a placeholder")
    return key


def main() -> None:
    key = load_key()
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system",
             "content": "Ban la nha bien kich phim hoat hinh 3D cho tre em 3-6 tuoi. "
                        "Tra loi CHI JSON hop le, khong them chu thich."},
            {"role": "user",
             "content": "Tao y tuong tap phim 5 phut the loai phieu luu. "
                        "Tra ve JSON: {\"case_id\":\"T01\",\"duration_minutes\":5,"
                        "\"hook\":\"...\",\"conflict\":\"...\",\"premise\":\"...\","
                        "\"differentiation\":\"...\",\"payoff\":\"...\","
                        "\"lesson\":\"...\",\"visual_potential\":\"...\"}"},
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
        "max_tokens": 800,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(URL, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }, json=payload)
    print("status:", r.status_code)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"]
    print("usage:", data.get("usage"))
    parsed = json.loads(content)
    print("keys:", sorted(parsed.keys()))
    print("hook[:60]:", parsed.get("hook", "")[:60])


if __name__ == "__main__":
    main()
