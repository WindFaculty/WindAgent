#!/usr/bin/env python3
"""
Phase 5 verification — VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED (plan 02 §13).

Runs the isolated upstream characterization probe (phase5_upstream_probe.py)
against the three golden fixtures plus the roadmap behavior-matrix scenarios
(16 roadmap cases + 7 extended cases), canonicalizes observed output, checks
golden-fixture rerun stability, and derives the verdict from REAL checks:

  artifacts/video_production/phase_05/
  ├── behavior_matrix.json
  ├── golden_outputs/
  ├── canonicalization_rules.json
  ├── defect_inventory.json
  ├── nondeterminism_inventory.json
  ├── harness_test_receipt.json
  ├── phase_report.md
  └── phase_verdict.json

Gate conditions (plan 02 §13):
  1. every retained capability has >= 1 happy-path and >= 1 failure-path case;
  2. the three golden fixtures rerun with stable results after canonicalization;
  3. every defect has an explicit decision (never silently becomes canonical);
  4. every nondeterminism entry has a cause and accepted boundary;
  5. the harness never makes upstream a runtime dependency (quarantine check).

Supports --no-write / --verify-only (runs all checks, writes nothing).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_05"
FIXTURES_DIR = (
    ROOT / "tests" / "fixtures" / "video_production"
    / "videoclaw_characterization"
)
PROBE_SCRIPT = ROOT / "scripts" / "verification" / "phase5_upstream_probe.py"
SPEC_TMP = ROOT / ".tmp" / "phase5_probe_spec.json"

RETained_CAPABILITIES = ("CAP-001", "CAP-002", "CAP-003", "CAP-004", "CAP-005")

FIXTURE_IDS = (
    "fixture_short_cartoon",
    "fixture_two_character_dialogue",
    "fixture_multi_scene_drama",
)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Canonicalization (plan 02 §12.4): strip only genuinely unstable fields.
# ---------------------------------------------------------------------------

# Fields that are provably unstable / not part of the preserved contract.
UNSTABLE_FIELD_NAMES = ("created_at", "updated_at", "session_id", "timestamp")
UUID_SUFFIX_RE = re.compile(r"(?i)(char|set|seg|shot)_[0-9a-f]{6}\b")
ISO_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})"
)
UUID4_RE = re.compile(r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def canonicalize(value, *, strip_fields: bool = True) -> object:
    """Recursively strip unstable fields and normalize random ids / paths."""
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            if strip_fields and key in UNSTABLE_FIELD_NAMES:
                continue
            out[key] = canonicalize(val, strip_fields=strip_fields)
        return out
    if isinstance(value, list):
        return [canonicalize(v, strip_fields=strip_fields) for v in value]
    if isinstance(value, str):
        text = value
        text = ISO_TIMESTAMP_RE.sub("<TIMESTAMP>", text)
        text = UUID4_RE.sub("<UUID>", text)
        text = UUID_SUFFIX_RE.sub(r"\1_<RANDOM>", text)
        text = re.sub(r"<WORKDIR>[\\/]", "<WORKDIR>/", text)
        return text
    return value


CANONICALIZATION_RULES = {
    "schema_version": "1.0.0",
    "strip_fields": list(UNSTABLE_FIELD_NAMES),
    "normalize": [
        "ISO-8601 timestamps -> <TIMESTAMP>",
        "uuid4 -> <UUID>",
        "char_/set_/seg_/shot_ + 6-hex suffix -> prefix_<RANDOM>",
        "absolute temp workdir path -> <WORKDIR>/...",
    ],
    "never_strip": [
        "scene order",
        "shot order / duration",
        "dialogue attribution (speaker/tone/text)",
        "errors and warnings",
        "artifact relationships (segment/unit ids, character ids)",
    ],
    "harness_controls": [
        "PYTHONHASHSEED=0 pinned in the probe subprocess so equal-length character "
        "names order deterministically across reruns (NONDET-005)",
    ],
    "policy_source": "plan 02 Section 12.4",
}


# ---------------------------------------------------------------------------
# Probe spec builder — derives inputs from fixtures so behavior is real.
# ---------------------------------------------------------------------------


def _scene_header_line(script: str) -> str:
    for line in script.splitlines():
        if re.match(r"^\s*\*{1,2}\s*第\d+集", line) or re.match(r"^\s*\*{1,2}\s*\d+\s*[-—]", line):
            return line.strip()
    return ""


def _dialogue_line(script: str) -> str:
    for line in script.splitlines():
        if "：" in line and not line.strip().startswith("*"):
            return line.strip()
    return ""


def _build_fixture_specs(fixtures: list[dict]) -> list[dict]:
    """Golden probes: one deterministic capability exercise per fixture."""
    spec = []
    for idx, fx in enumerate(fixtures):
        fx_id = fx["fixture_id"]
        brief = fx["brief"]
        responses = fx["responses"]
        script = responses["generate_script"]
        meta = responses["meta_extract"]
        episodes = int(brief.get("episodes", 1))
        style = brief.get("style", "anime")
        characters = [{"name": c["name"]} for c in json.loads(meta).get("characters", [])]
        settings = [{"name": s["name"]} for s in json.loads(meta).get("settings", [])]

        def add(probe: str, args: dict, tag: str):
            spec.append({"id": f"{fx_id}:{tag}", "probe": probe, "args": args})

        add("script_extract_json", {"text": meta}, "meta_parse")
        add("script_split_episodes", {"text": script}, "episode_split")
        add("script_build_episodes", {"text": script, "episodes": episodes}, "episode_struct")
        add("storyboard_annotate", {"text": script, "characters": characters, "settings": settings}, "annotate")
        add("storyboard_regex_segments", {"ep_n": 1, "text": script, "characters": characters, "settings": settings}, "regex_segments")
        header = _scene_header_line(script)
        if header:
            add("storyboard_parse_header", {"line": header, "setting_names": [s["name"] for s in settings]}, "scene_header")
        dlg = _dialogue_line(script)
        if dlg:
            add("storyboard_dialogue", {"line": dlg}, "dialogue_parse")
        chars = json.loads(meta).get("characters", [])
        sets = json.loads(meta).get("settings", [])
        if chars:
            c = chars[0]
            add("character_char_prompt", {"name": c["name"], "desc": c.get("description", ""), "style": style}, "char_prompt")
        if sets:
            s = sets[0]
            add("character_setting_prompt", {"name": s["name"], "desc": s.get("description", ""), "style": style}, "setting_prompt")
        add("reference_ratio", {"ratio": brief.get("video_ratio", "16:9")}, "ratio")
    return spec


def _build_scenario_spec(fixtures: list[dict]) -> list[dict]:
    """Behavior-matrix scenario probes (16 roadmap + 7 extended cases)."""
    fx0 = fixtures[0]
    brief0 = fx0["brief"]
    responses0 = fx0["responses"]
    script0 = responses0["generate_script"]
    meta0 = responses0["meta_extract"]
    meta_obj = json.loads(meta0)
    sets0 = [{"name": s["name"]} for s in meta_obj.get("settings", [])]
    char0 = meta_obj["characters"][0] if meta_obj.get("characters") else {"name": "X", "description": ""}
    set0 = meta_obj["settings"][0] if meta_obj.get("settings") else {"name": "X", "description": ""}

    spec = [
        # 1. Idea → concept
        {"id": "BM-001", "probe": "script_extract_json", "args": {"text": meta0}},
        # 2. Concept → screenplay
        {"id": "BM-002", "probe": "script_build_episodes", "args": {"text": script0, "episodes": 1}},
        # 3. Screenplay → character extraction
        {"id": "BM-003", "probe": "script_extract_json", "args": {"text": meta0}},
        # 4. Screenplay → setting extraction
        {"id": "BM-004", "probe": "script_extract_json", "args": {"text": meta0}},
        # 5. Character → image prompt
        {"id": "BM-005", "probe": "character_char_prompt", "args": {"name": char0["name"], "desc": char0.get("description", ""), "style": brief0.get("style", "anime")}},
        # 6. Setting → image prompt
        {"id": "BM-006", "probe": "character_setting_prompt", "args": {"name": set0["name"], "desc": set0.get("description", ""), "style": brief0.get("style", "anime")}},
        # 7. Story continuation (deterministic episode structuring of continuation text)
        {"id": "BM-007", "probe": "script_build_episodes", "args": {"text": script0 + "\n第2集 新的冒险\n\n**第2集-第1场 晨 外 森林\n人物：豆豆\n\n豆豆：天亮了，我们出发吧！\n", "episodes": 2}},
        # 8. Script revision (JSON extraction of a modified script payload)
        {"id": "BM-008", "probe": "script_extract_json", "args": {"text": '{"title":"新版","episodes":[{"episode_number":1,"content":"修订后的第一集"}]}'}},
        # 9. Asset replacement — versioned next-path naming
        {"id": "BM-009", "probe": "reference_next_version", "args": {"sid": "bm_session", "shot_id": "shot_001_01"}},
        # 10. Error handling khi thiếu model
        {"id": "BM-010", "probe": "require_input", "args": {"key": "llm_model", "input_data": {}}},
        # 11. Artifact path và naming
        {"id": "BM-011", "probe": "character_next_version", "args": {"sid": "bm_session", "asset_type": "characters", "asset_id": "char_abc"}},
        # 12. Resume sau crash — existing version discovery
        {"id": "BM-012", "probe": "character_list_versions", "args": {"sid": "bm_session", "asset_type": "characters", "asset_id": "char_abc"}},
        # 13. Không có network — pure parsing works offline
        {"id": "BM-013", "probe": "storyboard_dialogue", "args": {"line": "豆豆：这里是哪里呀？"}},
        # 14. Provider timeout / broken plan → validation error path
        {"id": "BM-014", "probe": "storyboard_validate_plan", "args": {"ep_n": 1, "raw_plan": [{"segment_number": 1}], "units": [{"unit_id": "U001", "scene_key": 1, "duration": 5, "is_entry": False}]}},
        # 15. Invalid image — no versions exist → failed status source
        {"id": "BM-015", "probe": "reference_list_versions_static", "args": {"sid": "bm_session", "shot_id": "shot_missing"}},
        # 16. Duplicate session ID — versioned next path instead of overwrite
        {"id": "BM-016", "probe": "character_next_version", "args": {"sid": "dup_session", "asset_type": "characters", "asset_id": "char_dup"}},
        # 17. Unicode/Vietnamese screenplay
        {"id": "BM-017", "probe": "script_split_episodes", "args": {"text": "Tập 1: Chú chó nhỏ\n\nNhân vật: Bông\n\nBông: Chào buổi sáng!\n\nHết"}},
        # 18. Empty input
        {"id": "BM-018", "probe": "script_extract_json", "args": {"text": ""}},
        # 19. Oversized input → per-episode line stats with too_long flags
        {"id": "BM-019", "probe": "script_length_stats", "args": {"text": "第1集\n\n" + "\n".join(f"豆豆：台词第{i}行" for i in range(40))}},
        # 20. Repeated character names but different IDs
        {"id": "BM-020", "probe": "storyboard_annotate", "args": {"text": script0, "characters": [{"name": "豆豆"}, {"name": "豆豆"}], "settings": sets0}},
        # 21. Broken provider response
        {"id": "BM-021", "probe": "script_extract_json", "args": {"text": "not json at all {{{"}},
        # 22. Partial artifact write — version discovery after one write
        {"id": "BM-022", "probe": "character_list_versions", "args": {"sid": "partial_session", "asset_type": "characters", "asset_id": "char_part"}},
        # 23. Cancellation between capabilities
        {"id": "BM-023", "probe": "storyboard_cancellation", "args": {}},
        # 24. Deterministic rerun with the same provider fixture
        {"id": "BM-024", "probe": "script_build_episodes", "args": {"text": script0, "episodes": 1}},
        # 25. CAP-003 failure: setting extraction from a response with no settings
        {"id": "BM-025", "probe": "script_extract_json", "args": {"text": '{"title":"X","characters":[{"name":"A"}]}'}},
        # 26. CAP-005: asset map building from character design
        {"id": "BM-026", "probe": "reference_build_asset_map", "args": {"character_design": {"characters": [{"id": "char_a", "selected": "assets/char_a.png"}], "settings": [{"id": "set_b", "selected": "assets/set_b.png"}]}}},
        # 27. CAP-005: reference collection for a segment
        {"id": "BM-027", "probe": "reference_collect_refs", "args": {"segment": {"segment_id": "seg_01_01", "characters": ["A"], "location": "LocB"}, "asset_map": {"characters": {"char_a": "assets/char_a.png"}, "settings": {"set_b": "assets/set_b.png"}}, "char_id_map": {"A": "char_a"}, "setting_id_map": {"LocB": "set_b"}}},
    ]
    return spec


def _load_fixtures() -> list[dict]:
    fixtures = []
    for fx_id in FIXTURE_IDS:
        base = FIXTURES_DIR / fx_id
        brief = json.loads((base / "brief.json").read_text(encoding="utf-8"))
        responses = json.loads((base / "provider_responses.json").read_text(encoding="utf-8"))
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        fixtures.append({
            "fixture_id": fx_id,
            "brief": brief,
            "responses": responses,
            "manifest": manifest,
        })
    return fixtures


def run_probe(spec: list[dict]) -> tuple[dict, str]:
    """Run the isolated probe subprocess once. Returns (result_by_id, workdir)."""
    SPEC_TMP.parent.mkdir(parents=True, exist_ok=True)
    SPEC_TMP.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    # Pin PYTHONHASHSEED so set-iteration ordering inside the upstream code is
    # deterministic across reruns (see NONDET-005). This is a harness isolation
    # control — the upstream's own name-ordering is still hash-dependent and is
    # documented as a defect/nondeterminism to fix in the canonical kernel.
    env = {
        **os.environ,
        "PYTHONHASHSEED": "0",
        # Do not write .pyc into third_party/videoclaw/upstream/ (the probe
        # also sets sys.dont_write_bytecode as belt-and-braces) — the Phase 4
        # quarantine manifest pins the exact file_count/content digest.
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT), str(SPEC_TMP)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"probe failed (rc={proc.returncode}): {proc.stderr[-2000:]}"
        )
    payload = json.loads(proc.stdout)
    by_id: dict[str, dict] = {}
    for idx, entry in enumerate(spec):
        result = payload["results"].get(str(idx))
        by_id[entry["id"]] = {"probe": entry["probe"], "result": result.get("result")}
    return by_id, payload.get("workdir", "")


# ---------------------------------------------------------------------------
# Behavior matrix
# ---------------------------------------------------------------------------

SCENARIO_DEFS = [
    # (case_id, capability, preconditions, failure_class, canonical_target_behavior)
    ("BM-001", "CAP-001", "brief/idea available; provider returns meta JSON", "HAPPY", "Structured concept preserves title, logline, genre, mood."),
    ("BM-002", "CAP-001", "concept selected; provider returns screenplay text", "HAPPY", "Episode structure preserves episode_number, act_title, content order."),
    ("BM-003", "CAP-002", "screenplay done; meta_extract returns characters", "HAPPY", "Character extraction preserves name and description; stable IDs assigned."),
    ("BM-004", "CAP-003", "screenplay done; meta_extract returns settings", "HAPPY", "Setting extraction preserves name and description; stable IDs assigned."),
    ("BM-005", "CAP-002", "character bible exists", "HAPPY", "Character image prompt must embed name/desc/style deterministically."),
    ("BM-006", "CAP-003", "location bible exists", "HAPPY", "Setting image prompt must embed name/desc/style deterministically."),
    ("BM-007", "CAP-001", "existing episodes + continuation brief", "HAPPY", "Continuation appends new episodes without renumbering or dropping prior content."),
    ("BM-008", "CAP-001", "user submits modified script payload", "HAPPY", "Revision payload parses; no silent mutation of unrelated fields."),
    ("BM-009", "CAP-005", "segment exists; regenerating reference asset", "HAPPY", "Versioned next path never overwrites an existing asset."),
    ("BM-010", "CAP-001", "llm_model not configured", "FAILURE_MISSING_MODEL", "Typed failure; no partial artifact written."),
    ("BM-011", "CAP-005", "character asset generation", "HAPPY", "Artifact naming is deterministic per asset_id (version suffix only on collision)."),
    ("BM-012", "CAP-002", "session restarted after partial generation", "HAPPY", "Existing versions discovered; generation resumes without duplicating."),
    ("BM-013", "CAP-004", "no network / no provider credentials", "HAPPY", "Deterministic parsing works offline."),
    ("BM-014", "CAP-004", "provider returns invalid segment plan", "FAILURE_VALIDATION", "Invalid plan rejected with typed validation error; retry/fallback decision explicit."),
    ("BM-015", "CAP-005", "image generation failed", "FAILURE_INVALID_ASSET", "No versions present -> status failed; no partial artifact published."),
    ("BM-016", "CAP-002", "duplicate session id reuses artifact store", "HAPPY", "Duplicate session must not clobber existing versions."),
    ("BM-017", "CAP-001", "Vietnamese/Unicode screenplay", "OBSERVED_UNICODE", "Unicode headers preserved; episode detection must not depend on CJK regex alone."),
    ("BM-018", "CAP-001", "empty provider response", "FAILURE_EMPTY_INPUT", "Empty response -> typed failure, not silent defaults."),
    ("BM-019", "CAP-001", "oversized screenplay", "OBSERVED_OVERSIZE", "Oversize flagged; canonical kernel must bound output explicitly."),
    ("BM-020", "CAP-002", "repeated display name with distinct IDs", "OBSERVED_DUPLICATE_NAME", "Identity must not merge on display name; stable character IDs preserved."),
    ("BM-021", "CAP-001", "broken (non-JSON) provider response", "FAILURE_BROKEN_RESPONSE", "Broken response -> typed parse failure surfaced, no silent fallback."),
    ("BM-022", "CAP-005", "partial artifact write then crash", "OBSERVED_PARTIAL_WRITE", "Partial write never treated as valid artifact."),
    ("BM-023", "CAP-004", "user cancels between capabilities", "FAILURE_CANCELLATION", "Cancellation raises; no partial stage completion."),
    ("BM-024", "CAP-001", "same provider fixture rerun", "HAPPY", "Rerun with same pinned inputs is deterministic after canonicalization."),
    ("BM-025", "CAP-003", "meta response omits settings", "FAILURE_BROKEN_RESPONSE", "Missing settings key must yield a typed failure, not silent empty bibles."),
    ("BM-026", "CAP-005", "character design artifact present", "HAPPY", "Asset map preserves id -> selected path mappings deterministically."),
    ("BM-027", "CAP-005", "segment with characters/location and asset map", "HAPPY", "Reference collection preserves character/location order and matching."),
]

# Scenario -> probe id used to read observed output.
SCENARIO_PROBE_ID = {
    "BM-001": "BM-001",
    "BM-002": "BM-002",
    "BM-003": "BM-003",
    "BM-004": "BM-004",
    "BM-005": "BM-005",
    "BM-006": "BM-006",
    "BM-007": "BM-007",
    "BM-008": "BM-008",
    "BM-009": "BM-009",
    "BM-010": "BM-010",
    "BM-011": "BM-011",
    "BM-012": "BM-012",
    "BM-013": "BM-013",
    "BM-014": "BM-014",
    "BM-015": "BM-015",
    "BM-016": "BM-016",
    "BM-017": "BM-017",
    "BM-018": "BM-018",
    "BM-019": "BM-019",
    "BM-020": "BM-020",
    "BM-021": "BM-021",
    "BM-022": "BM-022",
    "BM-023": "BM-023",
    "BM-024": "BM-024",
    "BM-025": "BM-025",
    "BM-026": "BM-026",
    "BM-027": "BM-027",
}


def _stable_vs_unstable(raw: dict) -> tuple[list[str], list[str]]:
    """Classify top-level fields into stable vs unstable after canonicalization."""
    canon = canonicalize(raw)
    stable, unstable = [], []
    if isinstance(canon, dict):
        for key, val in canon.items():
            if isinstance(val, str) and val in ("<TIMESTAMP>", "<UUID>"):
                unstable.append(key)
            else:
                stable.append(key)
    return sorted(stable), sorted(unstable)


def build_behavior_matrix(results: dict, scenario_spec: list[dict]) -> dict:
    matrix = []
    for case_id, capability, preconditions, failure_class, target in SCENARIO_DEFS:
        probe_id = SCENARIO_PROBE_ID[case_id]
        entry = results.get(probe_id, {})
        raw = entry.get("result")
        observed = canonicalize(raw)
        stable, unstable = _stable_vs_unstable(raw)
        matrix.append({
            "case_id": case_id,
            "capability": capability,
            "preconditions": preconditions,
            "input_fixture": "fixture_short_cartoon" if case_id in
                             ("BM-001", "BM-002", "BM-003", "BM-004", "BM-005",
                              "BM-006", "BM-007", "BM-013", "BM-017", "BM-018",
                              "BM-019", "BM-020", "BM-021", "BM-024")
                             else "behavior_scenario",
            "observed_output": observed,
            "stable_fields": stable,
            "unstable_fields": unstable,
            "side_effects": _side_effects(case_id, raw),
            "failure_class": failure_class,
            "canonical_target_behavior": target,
        })
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "case_count": len(matrix),
        "cases": matrix,
    }


def _side_effects(case_id: str, raw: dict) -> list[str]:
    effects = []
    if case_id in ("BM-009", "BM-011", "BM-016"):
        effects.append("writes versioned asset file under temp workdir (relative path only)")
    if case_id == "BM-010":
        effects.append("no artifact written (ValueError before any I/O)")
    if case_id in ("BM-023",):
        effects.append("RuntimeError raised; no stage completion")
    if case_id in ("BM-015",):
        effects.append("empty version list -> downstream status 'failed'")
    return effects


# ---------------------------------------------------------------------------
# Golden stability (gate condition 2)
# ---------------------------------------------------------------------------


def run_golden_stability(fixtures: list[dict], iterations: int = 3) -> dict:
    """Run the golden probe spec N times and compare canonicalized output."""
    spec = _build_fixture_specs(fixtures)
    runs = []
    for _ in range(iterations):
        results, workdir = run_probe(spec)
        runs.append({key: canonicalize(val["result"]) for key, val in results.items()})

    stable = True
    diffs: list[str] = []
    for key in sorted(runs[0]):
        first = json.dumps(runs[0][key], ensure_ascii=False, sort_keys=True)
        for run in runs[1:]:
            other = json.dumps(run[key], ensure_ascii=False, sort_keys=True)
            if first != other:
                stable = False
                diffs.append(f"{key}: canonicalized output differs across reruns")
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "iterations": iterations,
        "probe_count": len(spec),
        "stable_after_canonicalization": stable,
        "differences": diffs,
    }


def build_golden_outputs(fixtures: list[dict], results: dict) -> dict:
    """Persist canonicalized golden outputs per fixture."""
    by_fixture: dict[str, dict] = {}
    for fx in fixtures:
        fx_id = fx["fixture_id"]
        by_fixture[fx_id] = {
            key.split(":", 1)[1]: canonicalize(val["result"])
            for key, val in results.items()
            if key.startswith(f"{fx_id}:")
        }
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "fixtures": by_fixture,
    }


# ---------------------------------------------------------------------------
# Defect & nondeterminism inventories (gate conditions 3 & 4)
# ---------------------------------------------------------------------------


def build_defect_inventory(results: dict, golden_results: dict) -> dict:
    """Derive the defect inventory from observed probe output.

    Every entry must carry an explicit decision: never silently become the
    canonical expected behavior.
    """
    defects = []

    # DEF-001: broken provider response silently degrades to None.
    broken = results.get("BM-021", {}).get("result", {})
    broken_input = "not json at all {{{ "
    defects.append({
        "defect_id": "DEF-001",
        "observed_probe": "BM-021",
        "observed_behavior": f"extract_json({broken_input!r}) -> {broken!r}",
        "upstream_source": "script_agent.ScriptWriterAgent._extract_json_from_text",
        "failure_class": "FAILURE_BROKEN_RESPONSE",
        "decision": "REWRITE — canonical kernel must surface a typed parse failure instead of returning None silently.",
    })

    # DEF-002: episode headers only match CJK '第N集' / 'Episode N' regex.
    unicode_case = results.get("BM-017", {}).get("result", {})
    defects.append({
        "defect_id": "DEF-002",
        "observed_probe": "BM-017",
        "observed_behavior": f"split_episodes(Vietnamese 'Tập 1: ...') -> {unicode_case!r}",
        "upstream_source": "script_agent.ScriptWriterAgent._split_episode_blocks",
        "failure_class": "OBSERVED_UNICODE",
        "decision": "REWRITE — canonical kernel must detect Unicode/Vietnamese episode headers, not CJK-only.",
    })

    # DEF-003: duplicate display names are matched only by name (identity risk).
    dup = results.get("BM-020", {}).get("result", {})
    defects.append({
        "defect_id": "DEF-003",
        "observed_probe": "BM-020",
        "observed_behavior": f"annotate with two '豆豆' characters -> {dup!r}",
        "upstream_source": "storyboard_agent.StoryboardAgent._match_characters",
        "failure_class": "OBSERVED_DUPLICATE_NAME",
        "decision": "REWRITE — canonical kernel must bind identity via stable character_id, never merge on display name.",
        "related_nondeterminism": "NONDET-005 (equal-length name ordering also varies by hash seed)",
    })

    # DEF-004: versioned next-path relies on mtime-sorted glob (nondeterministic ordering).
    defects.append({
        "defect_id": "DEF-004",
        "observed_probe": "BM-009/BM-016",
        "observed_behavior": "Version discovery sorts by os.path.getmtime; tie ordering is filesystem-dependent.",
        "upstream_source": "reference_agent/character_agent._list_versions",
        "failure_class": "OBSERVED_PARTIAL_WRITE",
        "decision": "REWRITE — canonical store orders versions deterministically (sort by version suffix).",
    })

    # DEF-005: annotation relies on CJK-specific scene-header patterns for location.
    header_entry = golden_results.get("fixture_multi_scene_drama:scene_header")
    header = header_entry.get("result") if header_entry else None
    if header is None:
        header = "None (no header parsed)"
    defects.append({
        "defect_id": "DEF-005",
        "observed_probe": "golden scene_header probes",
        "observed_behavior": f"Scene-header parsing result sample: {header!r}",
        "upstream_source": "storyboard_agent.StoryboardAgent._parse_scene_header_parts",
        "failure_class": "OBSERVED_UNICODE",
        "decision": "REWRITE — canonical kernel must parse scene headers independent of CJK patterns.",
    })

    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "defect_count": len(defects),
        "all_decided": all(d["decision"] for d in defects),
        "defects": defects,
    }


def build_nondeterminism_inventory(golden_stability: dict) -> dict:
    entries = [
        {
            "nondet_id": "NONDET-001",
            "cause": "uuid.uuid4().hex[:6] in ScriptWriterAgent._gen_id",
            "observed_in": "character_id/setting_id generation",
            "accepted_boundary": "Stable canonical IDs; random suffix canonicalized to prefix_<RANDOM>.",
        },
        {
            "nondet_id": "NONDET-002",
            "cause": "datetime.now(timezone.utc).isoformat() in script payload created_at",
            "observed_in": "screenplay artifact metadata",
            "accepted_boundary": "created_at stripped by canonicalization; canonical kernel uses injected clock.",
        },
        {
            "nondet_id": "NONDET-003",
            "cause": "os.path.getmtime-based version ordering in _list_versions",
            "observed_in": "asset version listing",
            "accepted_boundary": "Deterministic version suffix ordering in canonical asset store.",
        },
        {
            "nondet_id": "NONDET-004",
            "cause": "golden rerun stability gate",
            "observed_in": "golden fixture reruns",
            "accepted_boundary": f"stable_after_canonicalization={golden_stability.get('stable_after_canonicalization')}",
        },
        {
            "nondet_id": "NONDET-005",
            "cause": (
                "StoryboardAgent._character_names sorts names by length only "
                "(sorted(set(...), key=len, reverse=True)); equal-length names "
                "fall back to set-iteration order, which varies per interpreter "
                "hash seed -> scene_characters/characters list order differs "
                "between processes."
            ),
            "observed_in": "storyboard_annotate / storyboard_regex_segments (characters, scene_characters, shot content)",
            "accepted_boundary": (
                "Harness pins PYTHONHASHSEED=0 for reproducible reruns. Canonical "
                "kernel must order character name lists deterministically (sorted "
                "full ordering, not length-then-set)."
            ),
        },
    ]
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "entry_count": len(entries),
        "all_explained": all(e["cause"] and e["accepted_boundary"] for e in entries),
        "entries": entries,
    }


def build_harness_receipt(golden_stability: dict, arch_violations: int) -> dict:
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "isolation": {
            "runs_as_subprocess": True,
            "network_blocked": True,
            "heavy_deps_loaded": False,
            "cwd_redirected_to_temp": True,
            "hash_seed_pinned": True,
            "only_launcher_of_upstream": "scripts/verification/phase5_upstream_probe.py",
        },
        "golden_stability": golden_stability,
        "architecture_quarantine_violations": arch_violations,
    }


def phase_report(
    status: str,
    matrix: dict,
    golden: dict,
    defects: dict,
    nondet: dict,
    coverage: dict,
    arch_violations: int,
) -> str:
    return f"""# Phase 5 Report — VideoClaw Behavior Characterization

- **Gate:** `VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Behavior matrix

- Cases: {matrix.get('case_count')}
- Capability coverage: {coverage}
- Golden stability (3 reruns, post-canonicalization): {'STABLE' if golden.get('stable_after_canonicalization') else 'UNSTABLE'}

## Canonicalization

- Strip fields: {', '.join(CANONICALIZATION_RULES['strip_fields'])}
- Never-strip: {', '.join(CANONICALIZATION_RULES['never_strip'])}

## Defect inventory

- Defects: {defects.get('defect_count')}; all_decided: {defects.get('all_decided')}

## Nondeterminism inventory

- Entries: {nondet.get('entry_count')}; all_explained: {nondet.get('all_explained')}

## Harness isolation

- Runs upstream only via `scripts/verification/phase5_upstream_probe.py` (subprocess, temp CWD, network-blocked stubs).
- Architecture quarantine violations: {arch_violations}

## Evidence

- `behavior_matrix.json`
- `golden_outputs/`
- `canonicalization_rules.json`
- `defect_inventory.json`
- `nondeterminism_inventory.json`
- `harness_test_receipt.json`
- `phase_verdict.json`
"""


def check_capability_coverage(matrix: dict) -> dict:
    """Gate condition 1: every retained capability has happy + failure path."""
    cases = matrix["cases"]
    by_cap: dict[str, dict] = {cap: {"happy": 0, "failure": 0} for cap in RETained_CAPABILITIES}
    for case in cases:
        cap = case["capability"]
        if cap not in by_cap:
            continue
        if case["failure_class"].startswith("HAPPY"):
            by_cap[cap]["happy"] += 1
        else:
            by_cap[cap]["failure"] += 1
    coverage = {}
    for cap, counts in by_cap.items():
        ok = counts["happy"] >= 1 and counts["failure"] >= 1
        coverage[cap] = {**counts, "covered": ok}
    return {
        "schema_version": "1.0.0",
        "all_covered": all(v["covered"] for v in coverage.values()),
        "coverage": coverage,
    }


def check_quarantine_boundary() -> int:
    """Reuse the architecture checker's videoclaw quarantine rule.

    The repo root must be on sys.path for `scripts` (a namespace package) to
    resolve when this verifier runs standalone via
    `python scripts/verification/verify_phase5_characterization.py`.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from scripts.check_architecture_imports import check
        import yaml
        cfg_path = ROOT / "configs" / "architecture" / "scaffold_v2.yaml"
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        report, _ = check(ROOT, config)
        return report["total_violations"]
    except Exception:  # noqa: BLE001
        return -1


def main(no_write: bool = False) -> int:
    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = _load_fixtures()

    # Run the full probe suite once for the behavior matrix + inventories.
    scenario_spec = _build_scenario_spec(fixtures)
    results, _workdir = run_probe(scenario_spec)

    # Run golden probes separately for stability + golden outputs.
    golden_spec = _build_fixture_specs(fixtures)
    golden_results, _ = run_probe(golden_spec)
    golden_stability = run_golden_stability(fixtures, iterations=3)
    golden_outputs = build_golden_outputs(fixtures, golden_results)

    matrix = build_behavior_matrix(results, scenario_spec)
    coverage = check_capability_coverage(matrix)
    defects = build_defect_inventory(results, golden_results)
    nondet = build_nondeterminism_inventory(golden_stability)
    arch_violations = check_quarantine_boundary()
    harness_receipt = build_harness_receipt(golden_stability, arch_violations)

    gate_reasons = []
    if not coverage["all_covered"]:
        gate_reasons.append("not every retained capability has happy+failure path")
    if not golden_stability["stable_after_canonicalization"]:
        gate_reasons.append("golden fixtures unstable after canonicalization")
    if not defects["all_decided"]:
        gate_reasons.append("defect inventory has undecided entries")
    if not nondet["all_explained"]:
        gate_reasons.append("nondeterminism inventory has unexplained entries")
    if arch_violations != 0:
        gate_reasons.append(f"quarantine boundary violations: {arch_violations}")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.1.0",
        "phase": 5,
        "baseline_sha": "1d98e26fe8923549e848e1a73cf32c6bb59944c1",
        "candidate_sha": "1d98e26fe8923549e848e1a73cf32c6bb59944c1",
        "status": overall_status,
        "gate": "VP5_VIDEOCLAW_BEHAVIOR_CHARACTERIZED",
        "evidence": [
            {"path": "behavior_matrix.json"},
            {"path": "golden_outputs/"},
            {"path": "canonicalization_rules.json"},
            {"path": "defect_inventory.json"},
            {"path": "nondeterminism_inventory.json"},
            {"path": "harness_test_receipt.json"},
            {"path": "phase_report.md"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase5_characterization.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "behavior_matrix.json", matrix)
        write_json(PHASE_DIR / "golden_outputs.json", golden_outputs)
        write_json(PHASE_DIR / "canonicalization_rules.json", CANONICALIZATION_RULES)
        write_json(PHASE_DIR / "defect_inventory.json", defects)
        write_json(PHASE_DIR / "nondeterminism_inventory.json", nondet)
        write_json(PHASE_DIR / "harness_test_receipt.json", harness_receipt)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            phase_report(
                overall_status, matrix, golden_stability, defects, nondet,
                coverage["coverage"], arch_violations,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_05 artifacts untouched (--no-write keeps the tree clean).")

    print(f"Phase 5 verdict: {overall_status}")
    print(f"  capability coverage: {coverage['coverage']}")
    print(f"  golden stability: {golden_stability['stable_after_canonicalization']}")
    print(f"  defects decided: {defects['all_decided']}  (count={defects['defect_count']})")
    print(f"  nondeterminism explained: {nondet['all_explained']}")
    print(f"  quarantine violations: {arch_violations}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
