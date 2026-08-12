"""C7 Google provider qualification harness (S3=694362c, adapter fix pending S4).

Runs the frozen C7 screenplay input through the REAL Google Gemini API via
the existing ``GoogleGeminiProviderAdapter`` + the REAL prompt registry
(v1.2.0) + REAL product services (ScreenplayGenerationService, review prompt
rendering). No mock provider, no Ollama fallback, no threshold changes.

Stages (each persists its evidence file before moving on):
  1. environment.json + frozen_input_manifest.json
  2. writer runs: 5 independent generations per writer model
  3. reviewer reliability: 10 repeated reviews of ONE fixed artifact per model
  4. cross-review matrix: 4 pairings x 5 writer outputs x 5 reviews
  5. qualification_matrix.json + selected_pair.json

Secrets policy: API key is read from the environment only and never written
to any evidence file; error text is redacted with the key removed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from windagent_core.contracts.providers import ProviderRequest  # noqa: E402
from windagent_core.domain.story.outline.models import EpisodeOutline  # noqa: E402
from windagent_core.domain.story.screenplay import ScreenplayDraft  # noqa: E402
from windagent_intelligence.story.prompts import StoryModelBoundary  # noqa: E402
from windagent_intelligence.story.prompts.registry import (  # noqa: E402
    prompt_for,
)
from windagent_intelligence.story.screenplay.service import (  # noqa: E402
    ScreenplayGenerationService,
)
from windagent_intelligence.story.review.service import (  # noqa: E402
    _scene_summary,
)
from windagent_intelligence.video.ports import (  # noqa: E402
    ModelCompletionRequest,
    ModelCompletionResult,
)
from windagent_providers.base.errors import (  # noqa: E402
    NetworkFailure,
    ProviderFailure,
    ProviderUnavailableFailure,
    RateLimitFailure,
    TimeoutFailure,
)
from windagent_providers.google import GoogleGeminiProviderAdapter  # noqa: E402

GEMINI = "gemini-3.5-flash-lite"
GEMMA = "gemma-4-31b-it"
MODELS = [GEMINI, GEMMA]
SOURCE_SHA = "694362c741b2005632d5efc03898c02710f02386"
OUT_DIR = REPO_ROOT / "artifacts" / "studio_roadmap_01" / "c7" / "google_qualification"
FROZEN_OUTLINE_PATH = REPO_ROOT / ".tmp" / "c7_frozen_outline.json"
FIXED_DRAFT_PATH = REPO_ROOT / ".tmp" / "c7_fixed_draft.json"
LANGUAGE_THRESHOLD = 0.85
PREFERRED_THRESHOLD = 0.88
RELIABILITY_SPREAD_MAX = 0.05
RELIABILITY_SPREAD_PREFERRED = 0.03
MAX_REVIEW_ATTEMPTS = 5
RETRYABLE = (RateLimitFailure, NetworkFailure, TimeoutFailure, ProviderUnavailableFailure)
ENGLISH_STOPLIST = {
    "the", "and", "is", "are", "with", "hello", "good", "yes", "no", "of",
    "to", "in", "it", "you", "that", "for", "on", "was", "at", "a",
}
GENERIC_LINES = {"...", "vâng.", "ừ.", "vậy à.", "ok", "ồ", "à", "vâng", "ừ"}


def _write_json(name: str, payload: Any) -> None:
    """Persist one evidence file; fail loudly with the offending field name."""
    try:
        (OUT_DIR / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except TypeError as exc:
        raise TypeError(f"{name}: {exc}") from exc


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact(value: str) -> str:
    key = os.environ.get("GOOGLE_API_KEY", "")
    if key and key in value:
        return value.replace(key, "[REDACTED]")
    return value


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "spread": round(max(values) - min(values), 4),
        "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "n": len(values),
    }


# ---------------------------------------------------------------------------
# Google-backed port (harness-only, mirrors RouteLockedModelPort semantics)
# ---------------------------------------------------------------------------


class GooglePort:
    """PreproductionModelPort over GoogleGeminiProviderAdapter (harness-only)."""

    def __init__(self, adapter: GoogleGeminiProviderAdapter, model: str) -> None:
        self._adapter = adapter
        self._model = model

    async def complete(self, request: ModelCompletionRequest) -> ModelCompletionResult:
        # gemini-3.5-flash-lite: sampling parameters are deprecated for the
        # new Gemini line — omit temperature (spec section 4). Gemma keeps
        # the registry temperature. thinking_level is NOT supported by the
        # current adapter; recorded as evidence, never faked.
        temperature = (
            None if self._model == GEMINI else request.temperature
        )
        provider_request = ProviderRequest(
            provider_id="google",
            model_id=self._model,
            prompt=request.user,
            messages=[],
            system_instruction=request.system,
            temperature=temperature,
            max_output_tokens=request.max_tokens,
            structured_output_schema=request.structured_output_schema,
            request_id=(request.metadata or {}).get("task_id", "qualification"),
            timeout_seconds=300.0,
        )
        started = time.perf_counter()
        response = await self._adapter.generate(provider_request, model_id=self._model)
        latency_ms = (time.perf_counter() - started) * 1000.0
        raw_text = response.text or ""
        return ModelCompletionResult(
            capability=request.capability,
            content=raw_text,
            finish_reason=response.finish_reason or "stop",
            provider=f"google/{self._model}",
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.prompt_tokens + response.usage.completion_tokens,
                "latency_ms": round(latency_ms, 1),
                "provider_model_id": response.provider_model_id or self._model,
                "endpoint_id": response.endpoint_id,
                "canonical_model_id": self._model,
                "provider_request_id": response.provider_request_id,
                "raw_response": raw_text,
                "response_hash": sha256(raw_text),
            },
        )


async def call_with_retry(coro_factory, *, attempts: int = MAX_REVIEW_ATTEMPTS) -> tuple[Any, Dict[str, Any]]:
    """Retry only transient provider failures; fail closed on everything else."""
    last_error: Optional[ProviderFailure] = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory(), {"attempts": attempt}
        except RETRYABLE as exc:
            last_error = exc
            await asyncio.sleep(min(2 ** attempt * 5, 60))
        except ProviderFailure:
            raise
    assert last_error is not None
    raise last_error


# ---------------------------------------------------------------------------
# Deterministic dialogue checks (spec section 7 defect list)
# ---------------------------------------------------------------------------


def check_dialogue(draft: Any, *, finish_reason: str, repair_count: int) -> Dict[str, Any]:
    scenes = draft.scenes
    lines: List[str] = []
    for scene in scenes:
        lines.extend(line.text for line in scene.dialogue)
    unique = len(set(lines))
    ascii_letters = sum(1 for ch in "".join(lines) if ch.isascii() and ch.isalpha())
    total_letters = sum(1 for ch in "".join(lines) if ch.isalpha())
    english_words = sum(
        1
        for word in "".join(lines).lower().split()
        if word.strip(".,!?;:") in ENGLISH_STOPLIST
    )
    return {
        "scene_count": len(scenes),
        "dialogue_count": len(lines),
        "missing_dialogue": len(lines) == 0,
        "empty_dialogue_lines": sum(1 for t in lines if not t.strip()),
        "generic_dialogue_lines": sum(1 for t in lines if t.strip().lower() in GENERIC_LINES),
        "narration_like_dialogue_lines": sum(1 for t in lines if len(t) > 150),
        "short_dialogue_lines": sum(1 for t in lines if 0 < len(t.strip()) < 4),
        "duplicate_dialogue_lines": len(lines) - unique,
        "truncated": finish_reason in ("length", "max_tokens"),
        "json_repair_needed": repair_count > 0,
        "ascii_letter_ratio": round(ascii_letters / total_letters, 4) if total_letters else 0.0,
        "english_word_ratio": round(english_words / max(len(lines), 1), 4),
        "unnatural_vietnamese_flag": (
            round(english_words / max(len(lines), 1), 4) > 0.2
        ),
    }


def review_variables(draft: Any, outline: Any) -> Dict[str, Any]:
    """Replicates ReviewService.generate's model-invocation variables exactly."""
    from windagent_core.domain.story.screenplay import validate_screenplay_draft

    report = validate_screenplay_draft(draft, outline=outline)
    findings = [
        {
            "code": issue.code,
            "severity": issue.severity,
            "location": issue.location,
            "evidence": issue.evidence,
        }
        for issue in report.issues
    ]
    deterministic_text = "\n".join(
        f"- [{f['severity'].value}] {f['code']} @{f['location']}: {f['evidence']}"
        for f in findings
    ) or "none"
    return {
        "title": draft.title,
        "logline": draft.logline,
        "language": draft.language,
        "audience_band": draft.audience_band,
        "target_duration_seconds": draft.target_duration_seconds,
        "total_estimated_seconds": draft.total_estimated_seconds,
        "scene_count": draft.scene_count,
        "dialogue_count": draft.dialogue_count,
        "scene_summary": _scene_summary(draft),
        "deterministic_findings": deterministic_text,
    }


def notes_content_tokens() -> List[str]:
    return ["thỏ", "diều", "nhím", "kite", "đồi", "bạn bè", "gió"]


def notes_correlate(notes: List[str]) -> Dict[str, Any]:
    tokens = notes_content_tokens()
    hits = sum(
        1
        for note in notes
        if any(tok in note.lower() for tok in tokens)
    )
    return {
        "notes_count": len(notes),
        "content_token_hits": hits,
        "correlates_with_content": hits >= max(1, len(notes) // 2),
    }


# ---------------------------------------------------------------------------
# Stage drivers
# ---------------------------------------------------------------------------


async def writer_runs(adapter, model: str, outline: EpisodeOutline, n: int = 5) -> List[Dict[str, Any]]:
    port = GooglePort(adapter, model)
    boundary = StoryModelBoundary(port)
    service = ScreenplayGenerationService(boundary)
    entry = prompt_for("story.screenplay.structured")
    runs: List[Dict[str, Any]] = []
    for i in range(1, n + 1):
        run: Dict[str, Any] = {
            "run_id": f"{model.replace('.', '-')}-w{i:02d}",
            "provider": "google",
            "model": model,
            "input_hash": sha256(json.dumps(outline.model_dump(), sort_keys=True, ensure_ascii=False)),
            "input_kind": "EpisodeOutline(frozen S2 diagnostic)",
            "prompt_id": entry.prompt_id,
            "prompt_version": entry.version,
            "writer_prompt_hash": entry.content_hash,
            "system_prompt_hash": sha256(entry.system),
            "thinking_level": "not_supported_by_adapter (evidence, not faked)",
            "temperature_sent": "no" if model == GEMINI else str(entry.temperature),
            "error": None,
        }
        try:
            started = time.perf_counter()
            result, retry_info = await call_with_retry(
                lambda: service.generate(
                    outline,
                    language="vi",
                    audience_band="5-8",
                    target_duration_seconds=240,
                )
            )
            run["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            run["retry_attempts"] = retry_info["attempts"]
            draft = result.draft
            run["parsed_response"] = json.loads(draft.model_dump_json())
            run["response_hash"] = sha256(draft.model_dump_json())
            run["finish_reason"] = result.provenance.finish_reason
            run["usage"] = result.provenance.usage
            run["repair_count"] = result.provenance.repair_count
            run["raw_response"] = result.provenance.usage.get("raw_response", "")
            run["response_hash"] = result.provenance.usage.get("response_hash", "")
            run["checks"] = check_dialogue(
                draft,
                finish_reason=result.provenance.finish_reason or "stop",
                repair_count=result.provenance.repair_count,
            )
            run["validation"] = result.validation
        except Exception as exc:  # noqa: BLE001 — per-run fail record, no silent fallback
            run["error"] = f"{type(exc).__name__}: {redact(str(exc))[:300]}"
        runs.append(run)
        print(f"[qual] writer {model} run {i}/{n}: {'OK' if not run['error'] else 'ERR ' + run['error'][:80]}")
    return runs


async def review_evals(
    adapter, model: str, draft: Any, outline: Any, *, n: int, tag: str
) -> List[Dict[str, Any]]:
    """n independent review evaluations of one draft by one reviewer model."""
    port = GooglePort(adapter, model)
    boundary = StoryModelBoundary(port)
    entry = prompt_for("story.review.assess")
    variables = review_variables(draft, outline)
    evals: List[Dict[str, Any]] = []
    for i in range(1, n + 1):
        record: Dict[str, Any] = {
            "eval_id": f"{tag}-{i:02d}",
            "reviewer_model": model,
            "prompt_id": entry.prompt_id,
            "prompt_version": entry.version,
            "review_prompt_hash": entry.content_hash,
            "system_prompt_hash": sha256(entry.system),
            "input_artifact": str(getattr(draft, "draft_id", "")),
            "error": None,
        }
        try:
            started = time.perf_counter()
            result, retry_info = await call_with_retry(
                lambda: boundary.invoke("story.review.assess", variables=variables)
            )
            record["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
            record["retry_attempts"] = retry_info["attempts"]
            record["language_score"] = float(result.data["language_score"])
            record["narrative_score"] = float(result.data["narrative_score"])
            record["age_fit_score"] = float(result.data["age_fit_score"])
            record["notes"] = list(result.data.get("notes", []))
            record["response_hash"] = sha256(json.dumps(result.data, sort_keys=True, ensure_ascii=False))
            record["finish_reason"] = result.provenance.finish_reason
            record["usage"] = result.provenance.usage
            record["notes_correlation"] = notes_correlate(record["notes"])
        except Exception as exc:  # noqa: BLE001
            record["error"] = f"{type(exc).__name__}: {redact(str(exc))[:300]}"
        evals.append(record)
        print(f"[qual] review {model} ({tag}) {i}/{n}: lang={record.get('language_score')} {'OK' if not record['error'] else 'ERR'}")
    return evals


async def main() -> int:
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        print(json.dumps({"status": "FAIL", "error": "GOOGLE_API_KEY not set"}))
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    outline = EpisodeOutline(**json.loads(FROZEN_OUTLINE_PATH.read_text(encoding="utf-8")))
    fixed_draft = ScreenplayDraft(**json.loads(FIXED_DRAFT_PATH.read_text(encoding="utf-8")))

    environment = {
        "source_sha": SOURCE_SHA,
        "generated_at": utc_now_iso(),
        "google_api_key": "present (never persisted)",
        "models": MODELS,
        "language_threshold": LANGUAGE_THRESHOLD,
        "reliability_spread_max": RELIABILITY_SPREAD_MAX,
        "reliability_spread_preferred": RELIABILITY_SPREAD_PREFERRED,
        "prompt_registry_version": "v1.2.0 (review/revise) / v1.0.3 (screenplay) — unchanged",
        "frozen_input": {"kind": "EpisodeOutline from S2 ornith diagnostic run", "hash": sha256(json.dumps(outline.model_dump(), sort_keys=True, ensure_ascii=False))},
        "fixed_artifact": {"kind": "ScreenplayDraft initial (S2 run)", "draft_id": fixed_draft.draft_id.value},
    }
    (OUT_DIR / "environment.json").write_text(json.dumps(environment, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "generated_at": utc_now_iso(),
        "source_sha": SOURCE_SHA,
        "input": {
            "kind": "EpisodeOutline",
            "input_hash": sha256(json.dumps(outline.model_dump(), sort_keys=True, ensure_ascii=False)),
            "title": outline.title,
            "scene_count": outline.scene_count,
            "target_duration_seconds": outline.target_duration_seconds,
        },
        "prompts": {
            "registry": "story prompts (frozen)",
            "writer_prompt_id": "story.screenplay.structured",
            "writer_prompt_version": prompt_for("story.screenplay.structured").version,
            "writer_prompt_hash": prompt_for("story.screenplay.structured").content_hash,
            "review_prompt_id": "story.review.assess",
            "review_prompt_version": prompt_for("story.review.assess").version,
            "review_prompt_hash": prompt_for("story.review.assess").content_hash,
            "revise_prompt_id": "story.revise.rewrite",
            "revise_prompt_version": prompt_for("story.revise.rewrite").version,
            "revise_prompt_hash": prompt_for("story.revise.rewrite").content_hash,
            "system_prompt_hashes": {
                pid: sha256(prompt_for(pid).system)
                for pid in ("story.screenplay.structured", "story.review.assess", "story.revise.rewrite")
            },
        },
    }
    (OUT_DIR / "frozen_input_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    adapter = GoogleGeminiProviderAdapter(api_key=key, timeout_seconds=300.0)

    # Stage 2: writer runs
    writer_results: Dict[str, List[Dict[str, Any]]] = {}
    for model in MODELS:
        runs = await writer_runs(adapter, model, outline)
        writer_results[model] = runs
        _write_json(
            f"{'gemini' if model == GEMINI else 'gemma'}_writer_runs.json", runs
        )

    # Stage 3: reviewer reliability on the fixed artifact
    reliability: Dict[str, Dict[str, Any]] = {}
    for model in MODELS:
        evals = await review_evals(adapter, model, fixed_draft, outline, n=10, tag=f"rel-{'gemini' if model == GEMINI else 'gemma'}")
        languages = [e["language_score"] for e in evals if "language_score" in e]
        narratives = [e["narrative_score"] for e in evals if "narrative_score" in e]
        reliability[model] = {
            "artifact": fixed_draft.draft_id.value,
            "artifact_hash": sha256(fixed_draft.model_dump_json()),
            "evaluations": evals,
            "language_stats": _stats(languages),
            "narrative_stats": _stats(narratives),
            "reviewer_reliable": (
                bool(languages)
                and _stats(languages)["spread"] <= RELIABILITY_SPREAD_MAX
            ),
            "reviewer_preferred": (
                bool(languages)
                and _stats(languages)["spread"] <= RELIABILITY_SPREAD_PREFERRED
            ),
            "notes_correlation": {
                m: notes_correlate([n for e in evals if "notes" in e for n in e["notes"]])
                for m in ["aggregate"]
            },
        }
        _write_json(
            f"{'gemini' if model == GEMINI else 'gemma'}_reviewer_reliability.json",
            reliability[model],
        )

    # Stage 4: cross-review matrix (4 configs x 5 writer outputs x 5 evals)
    configs = {
        "Q1": {"writer": GEMINI, "reviewer": GEMINI},
        "Q2": {"writer": GEMMA, "reviewer": GEMMA},
        "Q3": {"writer": GEMMA, "reviewer": GEMINI},
        "Q4": {"writer": GEMINI, "reviewer": GEMMA},
    }
    drafts_by_run: Dict[str, Any] = {}
    for model in MODELS:
        for run in writer_results[model]:
            if run.get("error") or "parsed_response" not in run:
                continue
            drafts_by_run[run["run_id"]] = ScreenplayDraft(**run["parsed_response"])

    matrix: Dict[str, Any] = {"configs": {}}
    for config_id, cfg in configs.items():
        writer_runs_for = writer_results[cfg["writer"]]
        config_entry: Dict[str, Any] = {
            "config": config_id,
            "writer": cfg["writer"],
            "reviewer": cfg["reviewer"],
            "runs": [],
            "all_language_scores": [],
        }
        for run in writer_runs_for:
            if run.get("error") or run["run_id"] not in drafts_by_run:
                config_entry["runs"].append({"run_id": run["run_id"], "error": run.get("error")})
                continue
            evals = await review_evals(
                adapter, cfg["reviewer"], drafts_by_run[run["run_id"]], outline,
                n=5, tag=f"{config_id}-{run['run_id']}",
            )
            languages = [e["language_score"] for e in evals if "language_score" in e]
            config_entry["all_language_scores"].extend(languages)
            config_entry["runs"].append({
                "run_id": run["run_id"],
                "evaluations": evals,
                "run_language_stats": _stats(languages),
                "run_language_median": _stats(languages).get("median"),
                "run_passes_threshold": bool(languages) and statistics.median(languages) >= LANGUAGE_THRESHOLD,
                "run_passes_preferred": bool(languages) and statistics.median(languages) >= PREFERRED_THRESHOLD,
            })
        all_scores = config_entry["all_language_scores"]
        stats = _stats(all_scores)
        pass_runs = sum(1 for r in config_entry["runs"] if r.get("run_passes_threshold"))
        config_entry.update({
            "config_language_stats": stats,
            "config_language_median": stats.get("median"),
            "writer_pass_rate": f"{pass_runs}/5",
            "writer_qualified": pass_runs >= 4,
        })
        matrix["configs"][config_id] = config_entry
        print(f"[qual] {config_id} {cfg['writer']}/{cfg['reviewer']}: median={stats.get('median')} pass={pass_runs}/5")
    _write_json("cross_review_matrix.json", matrix)

    # Stage 5: qualification matrix + selected pair
    qual_rows: List[Dict[str, Any]] = []
    for config_id, cfg in configs.items():
        entry = matrix["configs"][config_id]
        stats = entry["config_language_stats"]
        rev_spread = reliability[cfg["reviewer"]]["language_stats"].get("spread")
        qual_rows.append({
            "config": config_id,
            "writer": cfg["writer"],
            "reviewer": cfg["reviewer"],
            "writer_runs": 5,
            "language_median": stats.get("median"),
            "language_min": stats.get("min"),
            "language_max": stats.get("max"),
            "pass_rate": entry["writer_pass_rate"],
            "reviewer_spread": rev_spread,
            "median_latency_ms": None,
            "verdict": (
                "QUALIFIED" if entry["writer_qualified"] and rev_spread is not None and rev_spread <= RELIABILITY_SPREAD_MAX
                else "NOT_QUALIFIED"
            ),
        })
    _write_json(
        "qualification_matrix.json",
        {"rows": qual_rows, "ornith_baseline": {"model": "ornith:9b", "language_mean": 0.79, "observed_range": [0.75, 0.85]}},
    )

    best = max(qual_rows, key=lambda r: (r["language_median"] or 0, -(r["reviewer_spread"] or 1)))
    _write_json(
        "selected_pair.json",
        {
            "selected": best,
            "selection_criteria": "1 quality (median language) 2 stability (reviewer spread) 3 natural dialogue (checks) — spec section 12",
            "generated_at": utc_now_iso(),
        },
    )

    print(json.dumps({"status": "DONE", "best_pair": best}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
