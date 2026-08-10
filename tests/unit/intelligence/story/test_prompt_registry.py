"""B2 unit tests: prompt catalog registry invariants and immutability."""

from __future__ import annotations

import pytest

from windagent_intelligence.story.prompts import (
    STORY_PROMPT_REGISTRY,
    SafetyConstraints,
    StoryPromptEntry,
    prompt_for,
    prompt_manifest,
    register_prompt,
    registered_prompt_ids,
    validate_registry_invariants,
)
from windagent_intelligence.story.prompts.schemas import BRIEF_EXPANSION_OUTPUT_SCHEMA


def test_registry_has_extracted_legacy_prompts():
    assert registered_prompt_ids() == [
        "story.beats.generate",
        "story.bibles.generate",
        "story.brief_expansion.expand",
        "story.continuation.continue",
        "story.ideation.generate",
        "story.outline.generate",
        "story.outline.structured",
        "story.screenplay.structured",
        "story.screenplay.write",
    ]
    assert all(
        entry.legacy
        for entry in STORY_PROMPT_REGISTRY.values()
        if entry.prompt_id
        not in (
            "story.ideation.generate",
            "story.bibles.generate",
            "story.beats.generate",
            "story.outline.structured",
            "story.screenplay.structured",
        )
    )


def test_prompt_ids_follow_story_capability_name_pattern():
    for prompt_id in registered_prompt_ids():
        assert prompt_id.startswith("story."), prompt_id
        parts = prompt_id.split(".")
        assert len(parts) >= 3, prompt_id
        assert all(part for part in parts[1:]), prompt_id


def test_every_entry_declares_output_schema_and_safety():
    """Gate invariant: all Roadmap 1 prompts declare schemas + constraints."""
    assert validate_registry_invariants() == []
    for prompt_id, entry in STORY_PROMPT_REGISTRY.items():
        assert entry.output_schema, f"{prompt_id} missing output schema"
        assert entry.safety.max_output_chars > 0
        assert entry.version
        assert entry.template.strip()


def test_content_hash_semantics_stable():
    entry = STORY_PROMPT_REGISTRY["story.brief_expansion.expand"]
    first = entry.content_hash
    assert first == entry.content_hash  # deterministic
    assert len(first) == 64  # sha256 hex


def test_legacy_entry_matches_live_prompt_spec():
    """Extracted entries must equal the live legacy PromptSpec (no drift)."""
    from windagent_intelligence.video.continuation.service import CONTINUATION_PROMPT_V1
    from windagent_intelligence.video.ideation.brief_expander import BRIEF_EXPANSION_PROMPT_V1
    from windagent_intelligence.video.ideation.outliner import OUTLINE_PROMPT_V1
    from windagent_intelligence.video.screenplay.writer import SCREENPLAY_PROMPT_V1

    pairs = {
        "story.brief_expansion.expand": BRIEF_EXPANSION_PROMPT_V1,
        "story.outline.generate": OUTLINE_PROMPT_V1,
        "story.screenplay.write": SCREENPLAY_PROMPT_V1,
        "story.continuation.continue": CONTINUATION_PROMPT_V1,
    }
    for prompt_id, spec in pairs.items():
        entry = STORY_PROMPT_REGISTRY[prompt_id]
        assert entry.capability == spec.capability
        assert entry.version == spec.version
        assert entry.template == spec.template
        assert entry.content_hash == spec.content_hash
        assert entry.to_prompt_spec().content_hash == spec.content_hash


def test_prompt_for_unknown_id_fails_closed():
    with pytest.raises(KeyError):
        prompt_for("story.nonexistent.stage")


def test_register_prompt_rejects_id_version_content_drift(monkeypatch):
    from windagent_intelligence.story.prompts import registry as registry_module

    isolated: dict = {}
    monkeypatch.setattr(registry_module, "STORY_PROMPT_REGISTRY", isolated)
    entry = StoryPromptEntry(
        prompt_id="story.test.drift",
        capability="test",
        version="1.0.0",
        template="v1 template",
        output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        safety=SafetyConstraints(max_output_chars=1000),
    )
    register_prompt(entry)
    drifted = StoryPromptEntry(
        prompt_id="story.test.drift",
        capability="test",
        version="1.0.0",
        template="v1 template CHANGED",
        output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        safety=SafetyConstraints(max_output_chars=1000),
    )
    with pytest.raises(ValueError, match="bump the version"):
        register_prompt(drifted)
    # same version + same content: idempotent re-register is allowed
    register_prompt(entry)


def test_register_prompt_allows_new_version_of_same_id(monkeypatch):
    from windagent_intelligence.story.prompts import registry as registry_module

    isolated: dict = {}
    monkeypatch.setattr(registry_module, "STORY_PROMPT_REGISTRY", isolated)
    v1 = StoryPromptEntry(
        prompt_id="story.test.drift",
        capability="test",
        version="1.0.0",
        template="v1 template",
        output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        safety=SafetyConstraints(max_output_chars=1000),
    )
    v2 = StoryPromptEntry(
        prompt_id="story.test.drift",
        capability="test",
        version="2.0.0",
        template="v2 template",
        output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        safety=SafetyConstraints(max_output_chars=1000),
    )
    register_prompt(v1)
    register_prompt(v2)
    assert isolated["story.test.drift"].version == "2.0.0"
    # the global catalog is untouched by mutation tests
    assert "story.test.drift" not in STORY_PROMPT_REGISTRY


def test_malformed_prompt_id_rejected():
    with pytest.raises(ValueError, match="prompt_id"):
        StoryPromptEntry(
            prompt_id="BriefExpansion!",
            capability="brief_expansion",
            version="1.0.0",
            template="t",
            output_schema=BRIEF_EXPANSION_OUTPUT_SCHEMA,
        )


def test_json_output_without_schema_rejected():
    with pytest.raises(ValueError, match="output schema"):
        StoryPromptEntry(
            prompt_id="story.test.noschema",
            capability="test",
            version="1.0.0",
            template="t",
            output_schema={},
        )


def test_manifest_is_deterministic_and_matches_registry():
    manifest = prompt_manifest()
    assert manifest["prompt_schema_version"] == "studio.prompt/v1alpha1"
    assert list(manifest["entries"]) == registered_prompt_ids()
    assert prompt_manifest() == manifest  # deterministic
    for prompt_id, entry in STORY_PROMPT_REGISTRY.items():
        row = manifest["entries"][prompt_id]
        assert row["content_hash"] == entry.content_hash
        assert row["legacy"] is entry.legacy
        assert row["output_schema_ref"].startswith("schemas/")
