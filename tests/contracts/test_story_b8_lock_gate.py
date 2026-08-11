"""Plan B B8 contract tests over the committed lock fixtures (S10).

Every committed fixture must match live behavior: the golden package assembly
under all three approval modes (AUTO, HUMAN_REQUIRED, QUALITY_GATE_ONLY), the
negative lock corpus results re-run through the real LockService, the
handler/task-type surface, and the story_task_io.json input/output contract.
This is the fixture-side half of LOCKED_SCREENPLAY_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.verification.produce_b8_evidence import (
    golden_lock,
    lineage_refs,
    lock_corpus,
    lock_corpus_manifest,
    run_lock_corpus,
)

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_intelligence.story import (
    HANDLER_REGISTRY,
    LockHandler,
    registered_story_task_types,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_lock"
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
    return json.loads((LOCK_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Golden lock: three approval modes
# ---------------------------------------------------------------------------


def test_golden_lock_matches_live_behavior():
    assert load("lock_golden.json") == golden_lock()


def test_golden_packages_valid_under_each_approval_mode():
    golden = load("lock_golden.json")
    assert set(golden["approval_modes"]) == {"AUTO", "HUMAN_REQUIRED", "QUALITY_GATE_ONLY"}
    for mode in golden["approval_modes"]:
        entry = golden[mode]
        assert entry["package"]["artifact_type"] == "LockedScreenplayPackage"
        assert entry["receipt"]["state"] == "READY_FOR_PRODUCTION"
        assert entry["receipt"]["approval_mode"] == mode
        assert entry["package"]["receipt_id"] == entry["receipt"]["receipt_id"]
        assert len(entry["package"]["manifest"]) == 11
        assert entry["idempotent"] is True
        assert entry["validation"]["pass"] is True


def test_golden_package_checksum_stable():
    golden = load("lock_golden.json")
    # The committed package bytes hash matches the recorded content hash.
    package_payload = golden["AUTO"]["package"]
    live_hash = hashlib.sha256(_canonical_bytes(package_payload)).hexdigest()
    assert live_hash == golden["AUTO"]["package_content_hash"]


# ---------------------------------------------------------------------------
# Negative corpus
# ---------------------------------------------------------------------------


def test_corpus_results_match_live_behavior():
    assert load("lock_corpus.json") == lock_corpus_manifest()
    assert load("invalid_lock_results.json") == run_lock_corpus()


def test_every_corpus_case_refused_with_expected_codes():
    results = {r["case"]: r for r in load("invalid_lock_results.json")["results"]}
    for case in lock_corpus():
        row = results[case["case"]]
        assert row["outcome"] == "refused", case["case"]
        assert set(case["expect"]) <= set(row["codes"]), case["case"]


def test_corpus_checksums_match_committed():
    checksums = load("checksums.json")
    assert hashlib.sha256(_canonical_bytes(lock_corpus_manifest())).hexdigest() == checksums["corpus"]
    assert hashlib.sha256(_canonical_bytes(run_lock_corpus())).hexdigest() == checksums["results"]
    assert hashlib.sha256(_canonical_bytes(golden_lock())).hexdigest() == checksums["golden"]


# ---------------------------------------------------------------------------
# Handler surface + contract
# ---------------------------------------------------------------------------


def test_lock_handler_registered():
    assert StudioTaskType.LOCK.value in registered_story_task_types()
    assert StudioTaskType.LOCK in HANDLER_REGISTRY
    assert HANDLER_REGISTRY[StudioTaskType.LOCK] is LockHandler
    assert LockHandler().task_type == StudioTaskType.LOCK


def test_lock_io_contract_matches_story_task_io():
    task_io = json.loads(TASK_IO_PATH.read_text(encoding="utf-8"))
    lock_task = next(t for t in task_io["tasks"] if t["task_type"] == "studio.story.lock")
    assert lock_task["input_artifact_types"] == ["ScreenplayDraft", "ReviewReport"]
    assert lock_task["output_artifact_types"] == ["LockedScreenplayReceipt", "LockedScreenplayPackage"]


def test_lock_handler_imports_no_infrastructure():
    import inspect

    from windagent_intelligence.story import runtime_handlers as module

    source = inspect.getsource(module.lock)
    for forbidden in ("sqlalchemy", "storage", "queue", "WorkflowEngine", "alembic", "ModelPort"):
        assert forbidden not in source, f"lock handler leaks {forbidden}"
    assert "LockService" in source
    assert "FixtureModelPort" not in source


def test_lock_handler_roundtrip_from_committed_golden():
    import asyncio

    from scripts.verification.produce_b7_evidence import GOLDEN_DRAFT

    from windagent_core.domain.story.review import (
        LockedScreenplayReceipt,
        ReviewReport,
    )

    golden = load("lock_golden.json")["AUTO"]
    receipt = LockedScreenplayReceipt(**golden["receipt"])
    report = ReviewReport(
        report_id="report_lock_clean_pass",
        draft_id=GOLDEN_DRAFT.draft_id,
        review_iteration=1,
        verdict="PASS",
        quality_summary="0 findings (0 blocking, 0 warnings).",
    )
    handler = LockHandler()
    result = asyncio.run(handler.handle(
        GOLDEN_DRAFT,
        report,
        receipt,
        lineage_refs=lineage_refs(report=report, receipt=receipt),
    ))
    assert result.package.package_id.value == golden["package"]["package_id"]
    assert result.package.content_hash() == golden["package_content_hash"]
