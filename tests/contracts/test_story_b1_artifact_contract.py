"""Plan B B1 contract tests over the committed fixture bundle.

Every golden fixture (13 types, Vietnamese rabbit-and-kite slice) must parse,
round-trip, and pass its registered validator; every invalid fixture must fail
closed; the checksum bundle must match the committed files. This is the
fixture-side half of STORY_ARTIFACT_CONTRACT_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


from windagent_core.domain.story import (
    STORY_ARTIFACT_REGISTRY,
    find_duplicate_canonical_models,
)
from windagent_core.domain.story.validation import VALIDATION_CODE_CATALOG
from windagent_core.domain.studio.artifact import ArtifactType

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_artifacts"
)
GOLDEN_DIR = ARTIFACTS_DIR / "golden"
INVALID_DIR = ARTIFACTS_DIR / "invalid"


def load_checksums() -> dict:
    return json.loads((ARTIFACTS_DIR / "checksums.json").read_text(encoding="utf-8"))


def test_golden_fixture_files_match_checksums():
    checksums = load_checksums()
    for name, expected in checksums["golden"].items():
        raw = (GOLDEN_DIR / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected, f"golden {name} drifted"


def test_every_frozen_type_has_golden_fixture():
    files = {p.stem for p in GOLDEN_DIR.glob("*.json")}
    assert files == {t.value for t in ArtifactType}


def test_golden_fixtures_parse_and_pass_registered_validators():
    failures = []
    for artifact_type in ArtifactType:
        registration = STORY_ARTIFACT_REGISTRY[artifact_type]
        raw = (GOLDEN_DIR / f"{artifact_type.value}.json").read_text(encoding="utf-8")
        model = registration.content_model.deserialize(raw)
        restored = registration.content_model.deserialize(model.serialize())
        if restored != model:
            failures.append(f"{artifact_type.value}: round trip mismatch")
        if registration.validator is not None:
            report = registration.validator(restored)
            if not report.is_pass():
                failures.append(f"{artifact_type.value}: {report.summary()}")
    assert not failures, failures


def test_invalid_fixtures_fail_closed():
    """Parse failures or failed validation for every invalid fixture."""
    boundary_leaks = {"invalid_envelope_field_leak.json": "content_hash"}
    for path in INVALID_DIR.glob("*.json"):
        raw = path.read_text(encoding="utf-8")
        name = path.name
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue  # malformed JSON rejected
        if name in boundary_leaks:
            assert boundary_leaks[name] in data, f"{name} missing envelope-field leak"
            continue
        try:
            artifact_type = ArtifactType(data["artifact_type"])
        except (KeyError, ValueError):
            continue  # unknown discriminator rejected
        registration = STORY_ARTIFACT_REGISTRY.get(artifact_type)
        if registration is None:
            continue
        try:
            model = registration.content_model.model_validate(data)
        except Exception:
            continue  # schema failure at parse rejected
        if registration.validator is not None:
            assert not registration.validator(model).is_pass(), f"{name} unexpectedly passes"


def test_registry_completeness_and_no_duplicates():
    assert set(STORY_ARTIFACT_REGISTRY) == set(ArtifactType)
    assert find_duplicate_canonical_models() == []
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        for code in registration.validation_codes:
            assert code in VALIDATION_CODE_CATALOG, f"{artifact_type.value} -> {code}"


def test_registry_manifest_matches_code():
    manifest = json.loads((ARTIFACTS_DIR / "story_artifact_registry.json").read_text(encoding="utf-8"))
    assert set(manifest["registry"]) == {t.value for t in ArtifactType}
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        entry = manifest["registry"][artifact_type.value]
        assert entry["content_model"] == registration.content_model.__name__
        assert entry["validation_codes"] == list(registration.validation_codes)


def test_golden_draft_fits_duration_envelope():
    draft = json.loads((GOLDEN_DIR / "ScreenplayDraft.json").read_text(encoding="utf-8"))
    total = sum(s["estimated_seconds"] for s in draft["scenes"])
    assert 180 <= total <= 300
    assert abs(total - draft["target_duration_seconds"]) <= draft["tolerance_seconds"]


def test_golden_package_manifest_lineage_complete():
    package = json.loads((GOLDEN_DIR / "LockedScreenplayPackage.json").read_text(encoding="utf-8"))
    types = {ref["artifact_type"] for ref in package["manifest"]}
    required = {
        "ScreenplayDraft", "ReviewReport", "LockedScreenplayReceipt",
        "SelectedIdea", "StoryBible", "WorldBible", "CharacterCanon",
        "BeatSheet", "EpisodeOutline",
    }
    assert required <= types
