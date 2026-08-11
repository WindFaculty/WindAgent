from __future__ import annotations

import json

import pytest

from scripts.studio_roadmap.c7_slice_harness import SliceError
from scripts.studio_roadmap.c8_recovery_harness import (
    _artifact_duplicate_keys,
    assert_recovery_report,
    sqlite_path_from_url,
)
from scripts.studio_roadmap.produce_c9_evidence import evidence_sha, evidence_verdict
from scripts.studio_roadmap.produce_c8_evidence import _source_dirty_paths as c8_source_dirty
from scripts.studio_roadmap.produce_c9_evidence import _source_dirty_paths as c9_source_dirty


def test_c8_sqlite_path_is_resolved_inside_repository() -> None:
    path = sqlite_path_from_url("sqlite+aiosqlite:///certification.db")
    assert path.is_absolute()
    assert path.name == "certification.db"


def test_c8_duplicate_artifact_detection_is_revision_scoped() -> None:
    artifacts = [
        {"revision_id": "rev_1", "artifact_type": "ScreenplayDraft", "content_hash": "a"},
        {"revision_id": "rev_2", "artifact_type": "ScreenplayDraft", "content_hash": "a"},
        {"revision_id": "rev_1", "artifact_type": "ScreenplayDraft", "content_hash": "a"},
    ]
    assert _artifact_duplicate_keys(artifacts) == ["rev_1|ScreenplayDraft|a"]


def test_c8_gate_assertion_fails_closed() -> None:
    with pytest.raises(SliceError, match="stale_fence_rejected"):
        assert_recovery_report(
            {"checks": {"lease_takeover_generation_increased": True, "stale_fence_rejected": False}}
        )


def test_c9_reads_json_gate_and_integration_sha(tmp_path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps(
            {
                "gate": "REAL_VERTICAL_SLICE_GATE",
                "verdict": "PASS",
                "contract": "studio.contract/v0.1",
                "redaction_safe": True,
                "versions": {"integration_sha": "abc123"},
            }
        ),
        encoding="utf-8",
    )
    observed = evidence_verdict(path, "REAL_VERTICAL_SLICE_GATE")
    assert observed["result"] == "PASS"
    assert observed["source_sha"] == "abc123"
    assert evidence_sha(json.loads(path.read_text(encoding="utf-8"))) == "abc123"


def test_c9_rejects_gate_mismatch_even_when_json_says_pass(tmp_path) -> None:
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps(
            {
                "gate": "RECOVERY_VERTICAL_SLICE_GATE",
                "verdict": "PASS",
                "integration_sha": "abc123",
            }
        ),
        encoding="utf-8",
    )
    observed = evidence_verdict(path, "REAL_VERTICAL_SLICE_GATE")
    assert observed["result"] == "FAIL"
    assert observed["reason"].startswith("gate_mismatch")


def test_c9_rejects_unredacted_real_slice(tmp_path) -> None:
    path = tmp_path / "unredacted.json"
    path.write_text(
        json.dumps(
            {
                "gate": "RECOVERY_VERTICAL_SLICE_GATE",
                "verdict": "PASS",
                "contract": "studio.contract/v0.1",
                "integration_sha": "abc123",
                "redaction_safe": False,
            }
        ),
        encoding="utf-8",
    )
    assert evidence_verdict(path, "RECOVERY_VERTICAL_SLICE_GATE")["result"] == "FAIL"


def test_c9_markdown_requires_gate_and_pass_on_same_line(tmp_path) -> None:
    path = tmp_path / "gate.md"
    path.write_text("**`IDEA_GATE`: PASS.**\n", encoding="utf-8")
    assert evidence_verdict(path, "IDEA_GATE")["result"] == "PASS"
    assert evidence_verdict(path, "OUTLINE_GATE")["result"] == "FAIL"


def test_certification_reports_do_not_make_the_source_tree_dirty() -> None:
    paths = [
        "artifacts/studio_roadmap_01/c7/evidence.json",
        "artifacts/studio_roadmap_01/c8/evidence.json",
        "artifacts/studio_roadmap_01/c9/evidence.json",
        "apps/api/windagent_api/main.py",
    ]
    assert c8_source_dirty(paths) == [
        "artifacts/studio_roadmap_01/c9/evidence.json",
        "apps/api/windagent_api/main.py",
    ]
    assert c9_source_dirty(paths) == ["apps/api/windagent_api/main.py"]
