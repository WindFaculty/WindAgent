#!/usr/bin/env python3
"""Phase 5 — isolated upstream characterization probe (plan 02 §12, §16.5).

This is the ONLY component in the repository allowed to launch the quarantined
VideoClaw upstream (third_party/videoclaw/upstream/). It runs as a subprocess
outside the canonical composition root, with:

- network fully blocked by construction (no provider SDK is imported; the heavy
  model modules `config`, `models.*` are stubbed before any agent import);
- CWD redirected to an isolated temp workdir so upstream relative paths
  (code/result/...) never touch the repository;
- deterministic inputs (pinned fixtures) so behavior is recorded, not guessed.

It loads the four pre-production agent modules via a synthetic package that
bypasses the upstream `core/__init__.py` / `core/agents/__init__.py` chain
(which would pull FastAPI/OpenAI/DashScope into the interpreter).

Usage:
    python phase5_upstream_probe.py <spec.json>

`spec.json` is a list of probe invocations:
    [{"probe": "script_build_episodes", "args": {...}}, ...]

Results (JSON, one dict keyed by invocation index) are written to stdout.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

# Never write bytecode into the quarantined upstream tree: importing the
# vendored modules would otherwise create `__pycache__` dirs inside
# third_party/videoclaw/upstream/ and break the Phase 4 quarantine digests
# (file_count / content_sha256 in UPSTREAM_MANIFEST.json).
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_BACKEND = (
    ROOT / "third_party" / "videoclaw" / "upstream"
    / "video-claw" / "video-claw" / "backend"
)
AGENTS_DIR = UPSTREAM_BACKEND / "core" / "agents"

# ---------------------------------------------------------------------------
# Bootstrap: stub the heavy upstream modules so importing the agents never
# pulls in FastAPI / openai / dashscope / playwright or touches the network.
# ---------------------------------------------------------------------------


def _install_stubs() -> None:
    # Synthetic package that shadows the upstream `core` package so we never
    # execute core/__init__.py (which imports the orchestrator + all agents).
    pkg = types.ModuleType("videoclaw_probe")
    pkg.__path__ = [str(AGENTS_DIR)]
    pkg.__package__ = "videoclaw_probe"
    sys.modules["videoclaw_probe"] = pkg

    # `prompts` resolves from the real vendored backend (pure-python loader).
    backend = str(UPSTREAM_BACKEND)
    if backend not in sys.path:
        sys.path.insert(0, backend)

    # Stub config — never let Config.check_dirs() create dirs in the repo.
    cfg = types.ModuleType("config")
    cfg.settings = types.SimpleNamespace(
        RESULT_DIR=os.path.join(backend, "code", "result"),
        TEMP_DIR=os.path.join(backend, "temp"),
        BASE_DIR=backend,
    )
    sys.modules["config"] = cfg

    # Stub the model provider packages so any accidental import fails loudly
    # instead of reaching for credentials or the network.
    for name in ("models", "models.llm_client", "models.image_client",
                 "models.vlm_client", "models.config_model"):
        stub = types.ModuleType(name)
        stub.__path__ = []

        def _forbidden(*_args, _module_name=name, **_kwargs):
            raise RuntimeError(
                f"Network/model access is blocked in the Phase 5 probe: {_module_name}"
            )

        stub.query = _forbidden
        stub.LLM = type("LLM", (), {"__init__": _forbidden})
        stub.ImageClient = type("ImageClient", (), {"__init__": _forbidden})
        stub.VLM = type("VLM", (), {"__init__": _forbidden})
        stub.get_max_concurrency = lambda *a, **k: 1
        sys.modules[name] = stub


def _load_agent(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        f"videoclaw_probe.{module_name}",
        AGENTS_DIR / filename,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"videoclaw_probe.{module_name}"] = mod
    spec.loader.exec_module(mod)
    return mod


INSTALLED = False


def _agents():
    global INSTALLED
    if not INSTALLED:
        _install_stubs()
        # base_agent is a dependency of every agent module; load the four
        # pre-production agents (CAP-001..CAP-005).
        _load_agent("base_agent", "base_agent.py")
        _load_agent("script_agent", "script_agent.py")
        _load_agent("character_agent", "character_agent.py")
        _load_agent("storyboard_agent", "storyboard_agent.py")
        _load_agent("reference_agent", "reference_agent.py")
        INSTALLED = True
    return sys.modules


# ---------------------------------------------------------------------------
# Serialization helper — results must be JSON-safe and free of absolute paths.
# ---------------------------------------------------------------------------


def _clean(value, root_prefix: str):
    """Recursively convert to JSON-safe values, relativizing absolute paths."""
    if isinstance(value, Path):
        return _clean(str(value), root_prefix)
    if isinstance(value, dict):
        return {str(k): _clean(v, root_prefix) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v, root_prefix) for v in value]
    if isinstance(value, str):
        return value.replace(root_prefix, "<WORKDIR>")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return repr(value)


# ---------------------------------------------------------------------------
# Probe registry. Each probe is a pure function that runs real upstream logic
# with deterministic inputs and returns a JSON-serializable dict.
# ---------------------------------------------------------------------------


def _script_writer():
    return _agents()["videoclaw_probe.script_agent"].ScriptWriterAgent


def _storyboard():
    return _agents()["videoclaw_probe.storyboard_agent"].StoryboardAgent


def _character():
    return _agents()["videoclaw_probe.character_agent"].CharacterDesignerAgent


def _reference():
    return _agents()["videoclaw_probe.reference_agent"].ReferenceGeneratorAgent



def probe_script_extract_json(text: str) -> dict:
    """CAP-001: how upstream parses a provider response into JSON."""
    cls = _script_writer()
    return {"extracted": _clean(cls._extract_json_from_text(text), _workdir)}


def probe_script_split_episodes(text: str) -> dict:
    """CAP-001: episode-block segmentation of raw screenplay text."""
    cls = _script_writer()
    blocks = cls._split_episode_blocks(text)
    return {
        "blocks": _clean(
            [{"episode_number": b["episode_number"], "lines": len(b["lines"])}
             for b in blocks],
            _workdir,
        ),
        "block_count": len(blocks),
    }


def probe_script_length_stats(text: str) -> dict:
    """CAP-001: per-episode line-count stats and over-length flags."""
    cls = _script_writer()
    return _clean(cls._script_length_stats(text), _workdir)


def probe_script_episode_count_matches(text: str, episodes: int) -> dict:
    """CAP-001: whether script text contains exactly the expected episodes."""
    cls = _script_writer()
    return {"matches": cls._episode_count_matches(text, episodes)}


def probe_script_build_episodes(text: str, episodes: int) -> dict:
    """CAP-001: deterministic structured episode extraction from text."""
    cls = _script_writer()
    return _clean(cls._build_episodes_from_script_text(text, episodes), _workdir)


def probe_script_gen_id(prefix: str = "char") -> dict:
    """CAP-002/003: ID generation (nondeterministic by design — uuid)."""
    cls = _script_writer()
    return {"generated": cls._gen_id(prefix)}


def probe_storyboard_annotate(text: str, characters: list, settings: list) -> dict:
    """CAP-004: script annotation into units (duration, dialogue, chars)."""
    cls = _storyboard()
    annotated, units = cls._annotate_episode_script(text, characters, settings)
    return {
        "unit_count": len(units),
        "units": _clean(units, _workdir),
        "annotated_lines": len(annotated.splitlines()),
    }


def probe_storyboard_regex_segments(
    ep_n: int, text: str, characters: list, settings: list
) -> dict:
    """CAP-004: deterministic regex-based segmentation into shots/segments."""
    cls = _storyboard()
    return _clean(
        cls._build_segments_by_regex(ep_n, text, characters, settings),
        _workdir,
    )


def probe_storyboard_normalize_design(ep_n: int, plan: dict, raw_design: dict) -> dict:
    """CAP-004: normalize an LLM segment-design response (happy path)."""
    cls = _storyboard()
    return _clean(cls._normalize_segment_design(ep_n, plan, raw_design), _workdir)


def probe_storyboard_fallback_design(ep_n: int, plan: dict) -> dict:
    """CAP-004: deterministic fallback segment design when LLM fails."""
    cls = _storyboard()
    return _clean(cls._fallback_design_segment(ep_n, plan), _workdir)


def probe_storyboard_validate_plan(ep_n: int, raw_plan: list, units: list) -> dict:
    """CAP-004: plan validation — happy and broken paths."""
    cls = _storyboard()
    try:
        return {"ok": True, "plans": _clean(
            cls._validate_segment_plan(ep_n, raw_plan, units), _workdir)}
    except Exception as exc:  # noqa: BLE001 — characterization records failure
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def probe_storyboard_parse_header(line: str, setting_names: list) -> dict:
    """CAP-004: scene header parsing (Chinese and non-Chinese forms)."""
    cls = _storyboard()
    return _clean(cls._parse_scene_header_parts(line, setting_names), _workdir)


def probe_storyboard_dialogue(line: str) -> dict:
    """CAP-004: dialogue/tone/action parsing."""
    cls = _storyboard()
    return _clean(cls._dialogue_parts(line), _workdir)


def probe_storyboard_duration(text: str, is_dialogue: bool) -> dict:
    """CAP-004: script-unit duration heuristic (2-15s clamp)."""
    cls = _storyboard()
    return {"duration": cls._duration_for_script_unit(text, is_dialogue)}


def probe_storyboard_shot_type(value: str, first: bool) -> dict:
    """CAP-004: shot-type normalization with opening constraint."""
    cls = _storyboard()
    return {"shot_type": cls._normalize_shot_type(value, first=first)}


def probe_storyboard_estimate_duration(text: str, is_dialogue: bool) -> dict:
    """CAP-004: legacy duration estimator used by regex segmentation."""
    cls = _storyboard()
    return {"duration": cls._estimate_duration(text, is_dialogue)}


def probe_storyboard_infer_shot_type(text: str, is_dialogue: bool) -> dict:
    """CAP-004: shot-type inference from line keywords (Chinese-biased)."""
    cls = _storyboard()
    return {"shot_type": cls._infer_shot_type(text, is_dialogue)}


def probe_storyboard_cancellation() -> dict:
    """CAP-004: cancellation mid-capability raises RuntimeError (fail closed)."""
    cls = _storyboard()
    agent = cls()
    agent.set_cancellation_check(lambda: True)
    try:
        agent._check_cancel()
        return {"cancelled": False}
    except RuntimeError as exc:
        return {"cancelled": True, "error": str(exc)}


def probe_character_char_prompt(name: str, desc: str, style: str) -> dict:
    """CAP-002: character image prompt building from upstream template."""
    cls = _character()
    try:
        return {"prompt": _clean(cls._char_prompt(name, desc, style), _workdir)}
    except Exception as exc:  # noqa: BLE001
        return {"prompt": None, "error": f"{type(exc).__name__}: {exc}"}


def probe_character_setting_prompt(name: str, desc: str, style: str) -> dict:
    """CAP-003: setting image prompt building from upstream template."""
    cls = _character()
    try:
        return {"prompt": _clean(cls._setting_prompt(name, desc, style), _workdir)}
    except Exception as exc:  # noqa: BLE001
        return {"prompt": None, "error": f"{type(exc).__name__}: {exc}"}


def probe_character_next_version(sid: str, asset_type: str, asset_id: str) -> dict:
    """CAP-002/003: versioned asset path naming (resume/idempotency)."""
    agent = _character()()
    path = agent._next_version_path(sid, asset_type, asset_id)
    return {"next_path": _clean(os.path.relpath(path, _workdir), _workdir)}


def probe_character_list_versions(sid: str, asset_type: str, asset_id: str) -> dict:
    """CAP-002/003: existing version discovery (mtime-sorted)."""
    agent = _character()()
    return {"versions": _clean(
        [os.path.relpath(p, _workdir) for p in agent._list_versions(sid, asset_type, asset_id)],
        _workdir,
    )}


def probe_reference_ratio(ratio: str) -> dict:
    """CAP-005: aspect-ratio → pixel-size mapping."""
    mod = _agents()["videoclaw_probe.reference_agent"]
    return {"size": mod.ratio_to_size(ratio)}


def probe_reference_build_asset_map(character_design: dict) -> dict:
    """CAP-005: character/setting design → asset path map."""
    mod = _agents()["videoclaw_probe.reference_agent"]
    agent = mod.ReferenceGeneratorAgent()
    return _clean(agent._build_asset_map(character_design), _workdir)


def probe_reference_collect_refs(
    segment: dict, asset_map: dict, char_id_map: dict, setting_id_map: dict
) -> dict:
    """CAP-005: collect reference images for a segment (fuzzy name matching)."""
    mod = _agents()["videoclaw_probe.reference_agent"]
    agent = mod.ReferenceGeneratorAgent()
    return _clean(
        [os.path.relpath(p, _workdir) for p in agent._collect_refs(
            segment, asset_map, char_id_map, setting_id_map)],
        _workdir,
    )


def probe_reference_list_versions_static(sid: str, shot_id: str) -> dict:
    """CAP-005: existing shot version discovery (empty → failed status)."""
    mod = _agents()["videoclaw_probe.reference_agent"]
    return {"versions": _clean(
        [os.path.relpath(p, _workdir) for p in
         mod.ReferenceGeneratorAgent._list_versions_static(sid, shot_id)],
        _workdir,
    )}


def probe_reference_next_version(sid: str, shot_id: str) -> dict:
    """CAP-005: next version path for a shot (resume-safe)."""
    agent = _reference()()
    path = agent._next_version_path(sid, shot_id)
    return {"next_path": _clean(os.path.relpath(path, _workdir), _workdir)}


def probe_require_input(key: str, input_data: dict) -> dict:
    """All CAP: missing required model config raises ValueError."""
    # AgentInterface is abstract (process() is abstract); use a concrete agent.
    cls = _script_writer()
    agent = cls()
    try:
        return {"ok": True, "value": agent._require_input(input_data, key)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


# Registry
PROBES = {
    "script_extract_json": probe_script_extract_json,
    "script_split_episodes": probe_script_split_episodes,
    "script_length_stats": probe_script_length_stats,
    "script_episode_count_matches": probe_script_episode_count_matches,
    "script_build_episodes": probe_script_build_episodes,
    "script_gen_id": probe_script_gen_id,
    "storyboard_annotate": probe_storyboard_annotate,
    "storyboard_regex_segments": probe_storyboard_regex_segments,
    "storyboard_normalize_design": probe_storyboard_normalize_design,
    "storyboard_fallback_design": probe_storyboard_fallback_design,
    "storyboard_validate_plan": probe_storyboard_validate_plan,
    "storyboard_parse_header": probe_storyboard_parse_header,
    "storyboard_dialogue": probe_storyboard_dialogue,
    "storyboard_duration": probe_storyboard_duration,
    "storyboard_shot_type": probe_storyboard_shot_type,
    "storyboard_estimate_duration": probe_storyboard_estimate_duration,
    "storyboard_infer_shot_type": probe_storyboard_infer_shot_type,
    "storyboard_cancellation": probe_storyboard_cancellation,
    "character_char_prompt": probe_character_char_prompt,
    "character_setting_prompt": probe_character_setting_prompt,
    "character_next_version": probe_character_next_version,
    "character_list_versions": probe_character_list_versions,
    "reference_ratio": probe_reference_ratio,
    "reference_build_asset_map": probe_reference_build_asset_map,
    "reference_collect_refs": probe_reference_collect_refs,
    "reference_list_versions_static": probe_reference_list_versions_static,
    "reference_next_version": probe_reference_next_version,
    "require_input": probe_require_input,
}

_workdir = ""


def _make_workdir() -> str:
    """Isolated CWD so upstream relative artifact paths stay out of the repo."""
    global _workdir
    workdir = tempfile.mkdtemp(prefix="videoclaw_probe_")
    _workdir = workdir
    os.chdir(workdir)
    # Upstream expects result dirs relative to CWD (code/result/...).
    os.makedirs(os.path.join(workdir, "code", "result", "image"), exist_ok=True)
    os.makedirs(os.path.join(workdir, "code", "result", "script"), exist_ok=True)
    return workdir


def main(argv: list[str]) -> int:
    # Force UTF-8 stdout so Chinese/Unicode screenplay text survives on Windows
    # consoles that default to a legacy codepage (cp1252).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if len(argv) < 2:
        print(json.dumps({"error": "spec path required"}), file=sys.stderr)
        return 2
    # Resolve the spec to an absolute path BEFORE changing CWD into the temp
    # workdir (os.chdir would otherwise break relative spec paths).
    spec_path = Path(argv[1]).resolve()
    if not spec_path.is_file():
        print(json.dumps({"error": f"spec not found: {spec_path}"}), file=sys.stderr)
        return 2

    _make_workdir()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    results: dict[str, object] = {}
    errors: list[str] = []
    for idx, invocation in enumerate(spec):
        name = invocation.get("probe")
        args = invocation.get("args") or {}
        probe_fn = PROBES.get(name)
        if probe_fn is None:
            errors.append(f"[{idx}] unknown probe: {name}")
            continue
        try:
            results[str(idx)] = {"probe": name, "result": probe_fn(**args)}
        except Exception as exc:  # noqa: BLE001 — characterization records failures
            results[str(idx)] = {
                "probe": name,
                "result": {"error": f"{type(exc).__name__}: {exc}"},
            }
    payload = {
        "workdir": _workdir,
        "results": results,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
