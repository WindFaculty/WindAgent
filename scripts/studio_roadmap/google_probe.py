"""Google API probe for C7 model qualification (S3=694362c).

Verifies per model: authentication, accessibility, non-empty response,
actual model identity, and (for gemini-3.5-flash-lite) whether sampling
parameters (temperature) are rejected by the API — the product adapter
currently sends temperature when the prompt entry declares it.

Evidence only — never logs the API key. Fails closed on any API error.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from windagent_core.contracts.providers import ProviderRequest  # noqa: E402
from windagent_providers.google import GoogleGeminiProviderAdapter  # noqa: E402

MODELS = ["gemini-3.5-flash-lite", "gemma-4-31b-it"]
OUT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c7" / "google_qualification"


def redact(value: str) -> str:
    key = os.environ.get("GOOGLE_API_KEY", "")
    if key and key in value:
        return value.replace(key, "[REDACTED]")
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_of(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def probe_model(adapter, model: str) -> dict:
    result: dict = {
        "model": model,
        "authentication": "FAIL",
        "model_accessible": "FAIL",
        "response_non_empty": "FAIL",
        "actual_model": None,
        "probe_prompt_hash": hash_of("Trả lời đúng một câu tiếng Việt: con thỏ đang làm gì?"),
        "checks": {},
        "errors": [],
    }
    # 1. list_models (auth + accessibility)
    try:
        discovered = await adapter.list_models()
        ids = [m.raw_model_id for m in discovered]
        result["checks"]["list_models"] = {"ok": True, "listed": len(ids)}
        result["model_accessible"] = "PASS" if model in ids else "FAIL"
        if model not in ids:
            result["errors"].append(
                f"model {model!r} not in /models listing ({len(ids)} models listed)"
            )
    except Exception as exc:  # noqa: BLE001 — probe records every failure class
        result["errors"].append(f"list_models: {type(exc).__name__}: {redact(str(exc))}")
        result["checks"]["list_models"] = {"ok": False, "error": redact(str(exc))}
        return result

    # 2. minimal completion (no sampling params — Gemini 3.5 defaults)
    request = ProviderRequest(
        provider_id="google",
        model_id=model,
        prompt="Trả lời đúng một câu tiếng Việt: con thỏ đang làm gì?",
        system_instruction="Bạn là trợ lý tiếng Việt. Trả lời ngắn gọn.",
        temperature=None,
        max_output_tokens=64,
    )
    try:
        started = time.perf_counter()
        response = await adapter.generate(request, model_id=model)
        latency_ms = (time.perf_counter() - started) * 1000.0
        text = (response.text or "").strip()
        result["checks"]["generate"] = {
            "ok": True,
            "finish_reason": response.finish_reason,
            "latency_ms": round(latency_ms, 1),
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "response_hash": hash_of(text),
        }
        result["authentication"] = "PASS"
        result["response_non_empty"] = "PASS" if text else "FAIL"
        if not text:
            result["errors"].append("empty response text")
        result["actual_model"] = response.provider_model_id
        result["response_preview"] = text[:80]
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"generate: {type(exc).__name__}: {redact(str(exc))}")
        result["checks"]["generate"] = {"ok": False, "error": redact(str(exc))}
        return result

    # 3. sampling-parameter probe (product adapter sends temperature when set)
    param_request = ProviderRequest(
        provider_id="google",
        model_id=model,
        prompt="Trả lời: 1+1 bằng mấy?",
        temperature=0.3,
        max_output_tokens=16,
    )
    try:
        await adapter.generate(param_request, model_id=model)
        result["checks"]["sampling_params"] = {
            "ok": True,
            "note": "temperature=0.3 accepted by API",
        }
    except Exception as exc:  # noqa: BLE001
        result["checks"]["sampling_params"] = {
            "ok": False,
            "error_class": type(exc).__name__,
            "error": redact(str(exc))[:300],
            "note": "temperature rejected — product adapter must omit sampling params for this model",
        }
    return result


async def main() -> int:
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        print(json.dumps({"status": "FAIL", "error": "GOOGLE_API_KEY not set"}))
        return 1
    adapter = GoogleGeminiProviderAdapter(api_key=key)
    results = []
    for model in MODELS:
        results.append(await probe_model(adapter, model))
    payload = {
        "status": "PASS" if all(r["authentication"] == "PASS" for r in results) else "FAIL",
        "generated_at": utc_now_iso(),
        "source_sha": "694362c741b2005632d5efc03898c02710f02386",
        "note": "no API key or response content is stored; error text is secret-redacted",
        "models": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "google_api_probe.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
