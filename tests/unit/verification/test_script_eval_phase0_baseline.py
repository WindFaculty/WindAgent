"""Script Eval Phase 0 baseline evidence — fail-closed checks.

Gate SCRIPT_EVAL_BASELINE_FROZEN. The producer script
(scripts/verification/produce_script_eval_phase0_baseline.py) must be
re-runnable and emit 5 valid JSON manifests pinning git/model/prompts/env.
Eval-specific prompts are NOT_DEFINED until Phase 1 — that is the honest
freeze, not an error.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _ROOT / "scripts" / "verification" / "produce_script_eval_phase0_baseline.py"
_OUT = _ROOT / "artifacts" / "video_production" / "script_eval" / "phase_00_baseline"
_EXPECTED_FILES = [
    "baseline_manifest.json",
    "model_manifest.json",
    "prompt_manifest.json",
    "environment.json",
    "baseline_verdict.json",
]


def _run_producer() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_ROOT, capture_output=True, text=True, timeout=120,
    )


def _load(name: str) -> dict:
    return json.loads((_OUT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def produced() -> subprocess.CompletedProcess:
    return _run_producer()


def test_producer_exits_zero(produced: subprocess.CompletedProcess) -> None:
    assert produced.returncode == 0, produced.stderr[-2000:]


def test_all_evidence_files_valid_json(produced: subprocess.CompletedProcess) -> None:
    for name in _EXPECTED_FILES:
        assert (_OUT / name).exists(), name
        json.loads((_OUT / name).read_text(encoding="utf-8"))


def test_verdict_gate_pass(produced: subprocess.CompletedProcess) -> None:
    verdict = _load("baseline_verdict.json")
    assert verdict["gate"] == "SCRIPT_EVAL_BASELINE_FROZEN"
    assert verdict["verdict"] == "PASS"
    assert set(verdict["evidence_files"]) == set(_EXPECTED_FILES)


def test_git_sha_pinned_to_head(produced: subprocess.CompletedProcess) -> None:
    manifest = _load("baseline_manifest.json")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_ROOT, capture_output=True, text=True
    ).stdout.strip()
    assert manifest["git"]["head_sha"] == head
    assert manifest["git"]["head_tree_sha"] == subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=_ROOT, capture_output=True, text=True
    ).stdout.strip()


def test_plan_source_hashed(produced: subprocess.CompletedProcess) -> None:
    manifest = _load("baseline_manifest.json")
    plan = _ROOT / manifest["plan_source"]["file"]
    assert manifest["plan_source"]["sha256"] is not None
    assert plan.exists()


def test_eval_prompts_honestly_not_defined(produced: subprocess.CompletedProcess) -> None:
    prompts = _load("prompt_manifest.json")
    for key in ("system_prompt", "story_prompt", "character_prompt", "reviewer_prompt"):
        assert prompts[key]["status"] == "NOT_DEFINED", key
    # existing prompt surface must be hashed
    assert prompts["video_prompts_module"]["status"] == "EXISTS"
    assert len(prompts["video_prompts_module"]["sha256"]) == 64


def test_model_manifest_captures_config(produced: subprocess.CompletedProcess) -> None:
    model = _load("model_manifest.json")
    assert model["provider"]["default_provider"] == "mock"
    assert model["provider"]["default_model"] == "mock-gpt-4o"
    assert model["seed"]["supported"] is False


def test_environment_captured(produced: subprocess.CompletedProcess) -> None:
    env = _load("environment.json")
    assert env["python"].startswith("3.")
    assert env["toolchain"]["uv"]
    assert env["toolchain"]["git"]


def test_producer_is_re_runnable(produced: subprocess.CompletedProcess) -> None:
    """Second run must be byte-identical for static manifests (timestamps live
    only in baseline_manifest/verdict)."""
    static = ["model_manifest.json", "prompt_manifest.json", "environment.json"]
    before = {name: (_OUT / name).read_bytes() for name in static}
    rerun = _run_producer()
    assert rerun.returncode == 0, rerun.stderr[-2000:]
    for name in static:
        assert (_OUT / name).read_bytes() == before[name], name
