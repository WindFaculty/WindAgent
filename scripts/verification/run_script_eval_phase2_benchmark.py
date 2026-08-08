"""Run the Phase 2 idea benchmark: 36 live generation runs (12 briefs x 3
durations) via the NaraRouter/OpenRouter-compatible endpoint, validate each
idea with the Phase 2 fail-closed validator, persist per-run evidence.

Model: deepseek-v4-flash-alibaba (deepseek-v4-flash on this router returns
empty completions; alibaba variant is the same line and works).
Key: read at runtime from run_codex_cli_openrouter.ps1, NEVER printed.

Output per run:
  artifacts/video_production/script_eval/phase_02_idea/runs/<run_id>/
    input.json  idea.json  verdict.json  execution_receipt.json
Aggregate:
  artifacts/video_production/script_eval/phase_02_idea/benchmark_results.json
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from windagent_evals.script_eval import (  # noqa: E402
    BENCHMARK_BRIEFS, benchmark_runs, validate_idea,
)

_PS1 = _ROOT / "run_codex_cli_openrouter.ps1"
_BASE = "https://router.bynara.id/v1"
_MODEL = "deepseek-v4-flash-alibaba"
_RUN_DIR = _ROOT / "artifacts" / "video_production" / "script_eval" / \
    "phase_02_idea" / "runs"

_SYSTEM = (
    "Ban la nha bien kich phim hoat hinh 3D cho tre em 3-6 tuoi. "
    "TOAN BO VAN BAN PHAI BANG TIENG VIET (khong dau, khong tieng Trung, "
    "khong tieng Anh). Tra loi CHI bang mot JSON hop le, khong them chu thich, "
    "khong markdown fence."
)

_JSON_SCHEMA = (
    '{"case_id":"T01","duration_minutes":5,"hook":"...","conflict":"...",'
    '"premise":"...","differentiation":"...","payoff":"...","lesson":"...",'
    '"visual_potential":"..."}'
)


def load_key() -> str:
    m = re.search(r'NaraApiKey\s*=\s*"([^"]+)"', _PS1.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("no key line in ps1")
    key = m.group(1).strip()
    if "REPLACE_WITH_YOUR_REAL" in key or "..." in key or len(key) < 20:
        raise SystemExit("key looks like a placeholder")
    return key


def build_prompt(run: dict, duration_minutes: int) -> str:
    brief = next(b for b in BENCHMARK_BRIEFS if b["case_id"] == run["case_id"])
    return (
        f"Tao y tuong tap phim hoat hinh 3D {duration_minutes} phut, "
        f"the loai {brief['type']} ({brief['genre']}), cho tre em 3-6 tuoi.\n"
        f"Brief: {brief['brief']}\n"
        f"Yeu cau: hook ro rang; conflict phu hop tre em (khong bao luc); "
        f"premise du de duy tri {duration_minutes} phut; khac biet so voi cac "
        f"y tuong khac cung benchmark; co payoff; co lesson nhung khong giao "
        f"dieu; mo ta truc quan de ve duoc bang hinh anh.\n"
        f"Tra ve JSON dung cau truc: {_JSON_SCHEMA}"
    )


def call_model(client: httpx.Client, key: str, prompt: str) -> dict:
    payload = {
        "model": _MODEL,
        "messages": [{"role": "system", "content": _SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 1600,
    }
    r = client.post(f"{_BASE}/chat/completions", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }, json=payload, timeout=180.0)
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"].get("content") or ""
    if not content.strip():
        raise RuntimeError("empty model completion")
    return {"content": content, "usage": data.get("usage"),
            "model": data.get("model")}


def parse_idea(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    idea = json.loads(text)
    if not isinstance(idea, dict):
        raise ValueError("model output is not an object")
    return idea


def run_case(client: httpx.Client, key: str, run: dict) -> dict:
    run_id = run["run_id"]
    out = _RUN_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.json").write_text(json.dumps(run, indent=2, ensure_ascii=False)
                                    + "\n", encoding="utf-8")

    prompt = build_prompt(run, run["duration_minutes"])
    started = time.time()
    raw = None
    idea, report = None, None
    error = None
    for attempt in range(3):
        try:
            raw = call_model(client, key, prompt)
            idea = parse_idea(raw["content"])
            # normalize case_id/duration from the run spec, not the model
            idea["case_id"] = run["case_id"]
            idea["duration_minutes"] = run["duration_minutes"]
            report = validate_idea(idea)
            status = "PASS" if report.valid else "FAIL"
            error = None
            break
        except Exception as exc:  # noqa: BLE001 - evidence captures all failures
            status = "ERROR"
            error = f"{type(exc).__name__}: {exc}"
            idea, report = None, None
            if attempt < 2:
                time.sleep(2)
    elapsed = time.time() - started

    if idea is not None:
        (out / "idea.json").write_text(
            json.dumps(idea, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    (out / "execution_receipt.json").write_text(json.dumps({
        "run_id": run_id, "model": _MODEL, "status": status,
        "elapsed_seconds": round(elapsed, 2),
        "usage": raw.get("usage") if raw else None,
        "error": error,
        "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    verdict = {
        "run_id": run_id, "case_id": run["case_id"],
        "duration_minutes": run["duration_minutes"],
        "status": status,
        "valid": bool(report and report.valid),
        "errors": [{"check": f.check, "message": f.message} for f in
                   (report.errors if report else [])],
        "warnings": [{"check": f.check, "message": f.message} for f in
                     (report.warnings if report else [])],
        "elapsed_seconds": round(elapsed, 2),
        "error": error,
    }
    (out / "verdict.json").write_text(
        json.dumps(verdict, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return verdict


def main() -> int:
    runs = benchmark_runs()
    key = load_key()
    results = []
    with httpx.Client() as client:
        for i, run in enumerate(runs, 1):
            print(f"[{i:02d}/36] {run['run_id']} ...", end=" ", flush=True)
            verdict = run_case(client, key, run)
            print(verdict["status"], f"({verdict['elapsed_seconds']}s)")
            results.append(verdict)

    passed = sum(1 for v in results if v["status"] == "PASS")
    errors = sum(1 for v in results if v["status"] == "ERROR")
    failed = sum(1 for v in results if v["status"] == "FAIL")
    error_checks: dict = {}
    for v in results:
        for e in v["errors"]:
            error_checks[e["check"]] = error_checks.get(e["check"], 0) + 1

    summary = {
        "model": _MODEL, "endpoint": _BASE,
        "run_count": len(results), "passed": passed, "failed": failed,
        "errors": errors,
        "pass_rate": round(passed / len(results), 3),
        "error_check_counts": error_checks,
        "runs": results,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out_file = _RUN_DIR.parent / "benchmark_results.json"
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False)
                        + "\n", encoding="utf-8")
    print(f"\nbenchmark_results.json: {passed}/{len(results)} PASS "
          f"({summary['pass_rate']:.1%}), {failed} FAIL, {errors} ERROR")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
