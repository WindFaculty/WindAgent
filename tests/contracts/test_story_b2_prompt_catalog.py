"""Plan B B2 contract tests over the committed prompt catalog fixtures.

Every committed manifest/schema/corpus artifact must match the live code:
prompt entries (id/version/hash), schema bundle bytes + checksums, and the
invalid-output corpus results re-run through the real StoryModelBoundary.
This is the fixture-side half of STRUCTURED_MODEL_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verification.produce_b2_evidence import CORPUS, run_corpus, schema_bundle

from windagent_intelligence.story.prompts import (
    STORY_PROMPT_REGISTRY,
    prompt_manifest,
    registered_prompt_ids,
    validate_registry_invariants,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_prompts"
)


def _canonical_bytes(payload) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def load_checksums() -> dict:
    return json.loads((PROMPTS_DIR / "checksums.json").read_text(encoding="utf-8"))


def test_manifest_file_matches_live_registry():
    committed = json.loads((PROMPTS_DIR / "prompt_manifest.json").read_text(encoding="utf-8"))
    live = json.loads(_canonical_bytes(prompt_manifest()))
    assert committed == live
    assert list(committed["entries"]) == registered_prompt_ids()
    for prompt_id, entry in STORY_PROMPT_REGISTRY.items():
        row = committed["entries"][prompt_id]
        assert row["content_hash"] == entry.content_hash
        assert row["version"] == entry.version
        assert row["output_schema_ref"] == f"schemas/{entry._schema_file_name()}"


def test_manifest_checksum_matches_committed_file():
    checksums = load_checksums()
    raw = (PROMPTS_DIR / "prompt_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["manifest"]


def test_schema_bundle_files_match_code_and_checksums():
    checksums = load_checksums()
    bundle = schema_bundle()
    assert set(checksums["schemas"]) == set(bundle)
    for name, payload in bundle.items():
        path = PROMPTS_DIR / "schemas" / name
        assert path.exists(), f"missing committed schema {name}"
        assert path.read_bytes() == payload, f"schema {name} drifted from code"
        assert hashlib.sha256(payload).hexdigest() == checksums["schemas"][name]


def test_every_registry_entry_has_committed_schema_file():
    for entry in STORY_PROMPT_REGISTRY.values():
        path = PROMPTS_DIR / "schemas" / entry._schema_file_name()
        assert path.exists(), f"no committed schema for {entry.prompt_id}"


def test_output_schemas_accept_reject_samples():
    """Each JSON output schema admits a valid payload and rejects a bad one."""
    from jsonschema import Draft202012Validator

    brief = STORY_PROMPT_REGISTRY["story.brief_expansion.expand"].output_schema
    valid = {
        "title": "Con thỏ và cánh diều",
        "logline": "l",
        "genre": "thiếu nhi",
        "tone": "vui",
        "audience": "5-8",
        "target_duration_seconds": 240,
    }
    assert Draft202012Validator(brief).is_valid(valid)
    assert not Draft202012Validator(brief).is_valid({"title": "X"})  # missing required

    outline = STORY_PROMPT_REGISTRY["story.outline.generate"].output_schema
    assert Draft202012Validator(outline).is_valid(
        {"title": "T", "premise": "p", "synopsis": "s", "themes": ["a"], "beats": ["b"]}
    )
    assert not Draft202012Validator(outline).is_valid(
        {"title": "T", "themes": ["a", "a"]}  # duplicate theme + missing fields
    )


def test_corpus_file_matches_code():
    committed = json.loads((PROMPTS_DIR / "invalid_output_corpus.json").read_text(encoding="utf-8"))
    assert committed["cases"] == CORPUS
    checksums = load_checksums()
    raw = (PROMPTS_DIR / "invalid_output_corpus.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["corpus"]


def test_corpus_results_match_live_boundary_run():
    """Re-run every case through the real boundary; must equal committed."""
    committed = json.loads(
        (PROMPTS_DIR / "invalid_output_corpus_results.json").read_text(encoding="utf-8")
    )
    live = run_corpus(CORPUS)
    assert committed["cases"] == live
    # every case got an expected outcome
    for case in CORPUS:
        expected = case["expected"]
        actual = live[case["id"]]
        assert actual["outcome"] == expected["outcome"], case["id"]
        if "code" in expected:
            assert actual.get("code") == expected["code"], case["id"]
        if "repair_count" in expected:
            assert actual.get("repair_count") == expected["repair_count"], case["id"]


def test_registry_invariants_clean_and_all_schemas_declared():
    """Gate invariant: all Roadmap 1 prompts declare schemas."""
    assert validate_registry_invariants() == []
    for entry in STORY_PROMPT_REGISTRY.values():
        assert entry.output_schema
        assert entry.safety.max_output_chars > 0
