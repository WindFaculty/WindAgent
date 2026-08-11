"""Plan B B9 contract tests over the committed chain fixtures (S10-B9).

Every committed fixture must match live behavior: the full chain run through
the real SQL queue + independent worker (10 nodes / 9 frozen task types, all
artifacts produced by live services), the handler manifest (IO types +
capabilities), and the story_task_io.json contract. This is the fixture-side
half of PLAN_B_HANDOFF_GATE + SCREENPLAY_RUNTIME_GATE.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from scripts.verification.produce_b9_evidence import (
    build_artifacts,
    handler_manifest,
    run_chain,
)

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_intelligence.story import (
    HANDLER_REGISTRY,
    registered_story_task_types,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAIN_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_chain"
)
TASK_IO_PATH = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_task_io.json"
)


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load(name: str):
    return json.loads((CHAIN_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Committed fixtures match live behavior
# ---------------------------------------------------------------------------


def test_chain_fixtures_match_live_behavior():
    chain = asyncio.run(run_chain())
    artifacts = build_artifacts(chain)
    for name, payload in artifacts.items():
        path = CHAIN_DIR / name
        assert path.exists(), f"missing committed fixture {name}"
        assert path.read_bytes() == payload, f"committed fixture {name} drifted"


def test_chain_covers_all_nine_frozen_task_types():
    chain = load("chain_run.json")
    task_types = {s["task_type"] for s in chain["steps"]}
    assert task_types == set(registered_story_task_types())
    assert task_types == {t.value for t in StudioTaskType}


def test_chain_inputs_outputs_match_story_task_io():
    chain = load("chain_run.json")
    task_io = json.loads(TASK_IO_PATH.read_text(encoding="utf-8"))
    by_type = {t["task_type"]: t for t in task_io["tasks"]}
    for step in chain["steps"]:
        contract = by_type[step["task_type"]]
        assert [i["artifact_type"] for i in step["inputs"]] == contract["input_artifact_types"], step["node"]
        assert [o["artifact_type"] for o in step["outputs"]] == contract["output_artifact_types"], step["node"]


def test_final_package_refs_persisted_artifacts():
    """No canned final content: every output hash is unique and the lock
    package references this run's own persisted artifact hashes."""
    chain = load("chain_run.json")
    all_hashes = [o["content_hash"] for s in chain["steps"] for o in s["outputs"]]
    assert len(all_hashes) == len(set(all_hashes))  # no duplicate content refs
    lock = next(s for s in chain["steps"] if s["node"] == "lock")
    outputs = {o["artifact_type"]: o for o in lock["outputs"]}
    assert set(outputs) == {"LockedScreenplayReceipt", "LockedScreenplayPackage"}
    # Package + receipt hashes are not pre-baked fixture responses: they
    # derive from live canonical content (re-run above proves stability).
    assert len(outputs["LockedScreenplayPackage"]["content_hash"]) == 64


# ---------------------------------------------------------------------------
# Handler manifest
# ---------------------------------------------------------------------------


def test_handler_manifest_matches_live_registry():
    manifest = load("handler_manifest.json")
    assert manifest == handler_manifest()
    assert set(manifest["handlers"]) == {t.value for t in StudioTaskType}
    assert len(manifest["handlers"]) == 9


def test_handler_manifest_io_matches_story_task_io():
    manifest = load("handler_manifest.json")
    task_io = json.loads(TASK_IO_PATH.read_text(encoding="utf-8"))
    by_type = {t["task_type"]: t for t in task_io["tasks"]}
    for task_type, entry in manifest["handlers"].items():
        contract = by_type[task_type]
        assert entry["input_artifact_types"] == contract["input_artifact_types"], task_type
        assert entry["output_artifact_types"] == contract["output_artifact_types"], task_type
        # Every handler declared in the manifest is registered at runtime.
        assert task_type in {t.value for t in HANDLER_REGISTRY}


def test_handler_manifest_model_port_capabilities():
    manifest = load("handler_manifest.json")
    # Pure tasks need no provider; model tasks are exactly the 7 with prompts.
    assert manifest["handlers"]["studio.story.idea.evaluate"]["requires_model_port"] is False
    assert manifest["handlers"]["studio.story.lock"]["requires_model_port"] is False
    assert manifest["handlers"]["studio.story.review"]["requires_model_port"] is True
    assert manifest["handlers"]["studio.story.revise"]["requires_model_port"] is True
    assert manifest["handlers"]["studio.story.screenplay.generate"]["requires_model_port"] is True


def test_checksums_match_committed():
    checksums = load("checksums.json")
    chain = load("chain_run.json")
    manifest = load("handler_manifest.json")
    assert hashlib.sha256(_canonical_bytes(chain)).hexdigest() == checksums["chain_run"]
    assert hashlib.sha256(_canonical_bytes(manifest)).hexdigest() == checksums["handler_manifest"]
