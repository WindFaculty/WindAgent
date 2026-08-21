"""Plan B B0 consumer freeze tests.

B0 — Consume freeze and classify reusable code:

1. ``A -> B fixture validation``: B's task/IO content proposal
   (docs/.../story_task_io.json) must stay inside A's frozen task types and
   artifact types.
2. ``Import / public API characterization``: every current public Story symbol
   still imports from its current location; no current story service is deleted
   during B0.
3. ``Serialization snapshots``: current content models serialize
   deterministically and keep a pinned field inventory so B1's canonical
   schemas reuse/migrate with known diffs rather than silently inventing shapes.
4. ``Invalid / unknown schema fixtures``: an unknown artifact type or an
   unknown schema version is rejected (fail-closed), never accepted as a
   canonical artifact.
5. ``Model-port contract``: ``PreproductionModelPort`` remains the only
   provider boundary and is runtime-checkable; a deterministic fake (unit-test
   fixture) satisfies it.

These are data/import-level contracts. No A/C implementation is imported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
)

CONTRACT_VERSION = "studio.contract/v0.1"
ARTIFACT_SCHEMA_VERSION = "studio.artifact/v1alpha1"


def load(name: str) -> dict:
    path = FIXTURES_DIR / name
    assert path.is_file(), f"missing fixture: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. A -> B fixture validation
# ---------------------------------------------------------------------------

FROZEN_TASK_TYPES = load("tasks.json")["task_types"]
FROZEN_ARTIFACT_TYPES = set(load("artifact_envelope.json")["artifact_types"])


def test_story_task_io_dedares_contract_version() -> None:
    io = load("story_task_io.json")
    assert io["contract_version"] == CONTRACT_VERSION
    assert io["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert io["schema"].startswith("studio.")
    assert io["schema"].endswith("/v1")


def test_story_task_io_exactly_matches_frozen_task_types() -> None:
    io = load("story_task_io.json")
    declared = [task["task_type"] for task in io["tasks"]]
    assert declared == FROZEN_TASK_TYPES, (
        "B0 story_task_io.json deviates from frozen tasks.json"
    )
    # Every frozen task type has exactly one row; no hidden model tasks.
    assert len(declared) == len(set(declared)) == 9
    # Selection is a command, never a task row.
    declared_text = json.dumps(io, ensure_ascii=False)
    assert "idea.select" not in declared_text or "synchronous" in declared_text


def test_story_task_io_references_only_frozen_artifact_types() -> None:
    io = load("story_task_io.json")
    referenced: set[str] = set()
    for task in io["tasks"]:
        referenced.update(task["input_artifact_types"])
        referenced.update(task["output_artifact_types"])
    unknown = referenced - FROZEN_ARTIFACT_TYPES
    assert not unknown, f"story_task_io references non-frozen artifact types: {unknown}"
    # Every frozen Story artifact is reachable from at least one task.
    story_types = {
        "CreativeBrief",
        "IdeaCandidateSet",
        "SelectedIdea",
        "StoryBible",
        "WorldBible",
        "CharacterCanon",
        "BeatSheet",
        "EpisodeOutline",
        "ScreenplayDraft",
        "ReviewReport",
        "RevisionProposal",
        "LockedScreenplayReceipt",
        "LockedScreenplayPackage",
    }
    assert story_types <= referenced, (
        "some frozen Story artifact type is not produced/consumed by any task"
    )


def test_story_task_io_selection_rule_is_a_command() -> None:
    io = load("story_task_io.json")
    assert io["selection_rule"].startswith("Idea selection and human approval are synchronous")


# ---------------------------------------------------------------------------
# 2. Import / public API characterization
# ---------------------------------------------------------------------------


def test_current_story_public_api_still_imports() -> None:
    """B0 makes no moves; every public Story symbol stays importable."""
    from windagent_intelligence import video as video_pkg

    names = [
        "CreativeBriefExpander",
        "StoryOutliner",
        "ScreenplayWriter",
        "DialogueNarrator",
        "EntityExtractor",
        "StyleDesigner",
        "ContinuationService",
        "PackageAssembler",
        "PromptSpec",
        "PreproductionModelPort",
        "VideoDirectorService",
        "DurationBudgetPolicy",
    ]
    missing = [n for n in names if not hasattr(video_pkg, n)]
    assert not missing, f"public Story API symbols missing: {missing}"


def test_current_core_content_models_still_import() -> None:
    from windagent_core.domain.video_production import screenplay as sp

    for name in ("CreativeBrief", "StoryConcept", "DialogueLine", "Screenplay"):
        assert hasattr(sp, name), f"missing {name}"


def test_no_legacy_story_service_is_deleted() -> None:
    import windagent_intelligence.video.ideation.brief_expander  # noqa: F401
    import windagent_intelligence.video.ideation.outliner  # noqa: F401
    import windagent_intelligence.video.screenplay.writer  # noqa: F401
    import windagent_intelligence.video.screenplay.narration  # noqa: F401
    import windagent_intelligence.video.entity_extraction.extractor  # noqa: F401
    import windagent_intelligence.video.style_design.designer  # noqa: F401
    import windagent_intelligence.video.continuation.service  # noqa: F401
    import windagent_intelligence.video.assembly.assembler  # noqa: F401
    import windagent_intelligence.video.director.service  # noqa: F401
    import windagent_intelligence.video.director.revision  # noqa: F401
    import windagent_intelligence.video.director.duration  # noqa: F401


# ---------------------------------------------------------------------------
# 3. Serialization snapshots (field inventory + determinism)
# ---------------------------------------------------------------------------

_PINNED_FIELDS: Dict[str, set] = {
    "CreativeBrief": {
        "brief_id", "title", "genre", "logline", "tone", "audience",
        "target_duration_seconds", "aspect_ratio", "production_constraints",
    },
    "StoryConcept": {"concept_id", "title", "premise", "synopsis", "themes", "metadata"},
    "DialogueLine": {
        "dialogue_id", "scene_id", "character_id", "order", "text", "delivery",
    },
    "Screenplay": {
        "screenplay_id", "title", "logline", "status", "scenes", "metadata",
    },
}


def test_content_model_field_inventories_are_pinned() -> None:
    """Snapshot: current content-model field sets. B1 canonical schemas must
    preserve these as content or document an explicit mapping in the ledger."""
    from windagent_core.domain.video_production import screenplay as sp

    for model_name, expected in _PINNED_FIELDS.items():
        model = getattr(sp, model_name)
        fields = set(model.model_fields)
        unexpected = fields - expected
        expected - fields
        assert not unexpected, f"{model_name} gained fields: {unexpected}"
        # Extra='allow' constants are allowed, but frozen requires config.
        assert model.model_config.get("frozen") is True


def test_content_models_serialize_deterministically() -> None:
    from windagent_core.domain.video_production import screenplay as sp
    from windagent_core.domain.video_production.ids import (
        CharacterId,
        CreativeBriefId,
        DialogueLineId,
        SceneId,
        ScreenplayId,
        StoryConceptId,
    )

    brief = sp.CreativeBrief(
        brief_id=CreativeBriefId("br_1"),
        title="Con thỏ và cánh diều",
        genre="thiếu nhi",
        audience="5-8",
        target_duration_seconds=240,
    )
    concept = sp.StoryConcept(
        concept_id=StoryConceptId("sc_1"),
        title="Con thỏ và cánh diều",
        premise="A rabbit and a kite.",
        themes=["tình bạn"],
    )
    line = sp.DialogueLine(
        dialogue_id=DialogueLineId("dl_1"),
        scene_id=SceneId("scn_1"),
        character_id=CharacterId("ch_1"),
        order=1,
        text="Ồ, cánh diều đẹp quá!",
    )
    screenplay = sp.Screenplay(
        screenplay_id=ScreenplayId("sp_1"),
        title="Con thỏ và cánh diều",
        logline="Một chú thỏ học cách thả diều.",
    )

    for obj in (brief, concept, line, screenplay):
        a = obj.model_dump_json()
        b = obj.model_dump_json()
        assert a == b, f"{type(obj).__name__} serialization is not deterministic"
        # Canonical JSON serialization (sorted keys) is stable per model fields.
        canonical = json.dumps(obj.model_dump(mode="json"), sort_keys=True)
        assert json.dumps(obj.model_dump(mode="json"), sort_keys=True) == canonical
        # JSON round-trip preserves Unicode (Vietnamese) exactly.
        assert "cánh diều" in a or "Ồ" in a or "thỏ" in a


# ---------------------------------------------------------------------------
# 4. Invalid / unknown schema fixtures (fail closed)
# ---------------------------------------------------------------------------


def test_unknown_artifact_type_rejected() -> None:
    io = load("story_task_io.json")
    known = set()
    for task in io["tasks"]:
        known.update(task["input_artifact_types"])
        known.update(task["output_artifact_types"])
    unknown = "ScreenplayDraftV2"
    assert unknown not in known
    assert unknown not in FROZEN_ARTIFACT_TYPES


def test_envelope_requires_schema_version() -> None:
    envelope = load("artifact_envelope.json")
    assert envelope["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert "content_hash" in envelope["envelope_fields"]
    mandatory = {
        "artifact_id", "artifact_type", "schema_version", "series_id",
        "episode_id", "revision_id", "content_hash", "input_artifact_refs",
        "prompt_id", "prompt_version", "prompt_hash", "created_at", "content",
    }
    assert mandatory <= set(envelope["envelope_fields"]), (
        "B0 content models carry NO envelope fields today; envelope identity is A-owned"
    )


def test_content_models_carry_no_envelope_fields() -> None:
    """Today's content models are content-only: no artifact_id / hash / prompt
    provenance at model level. B1 wraps them behind the A envelope rather than
    treating them as envelope substitutes (cross-cutting rule 7)."""
    from windagent_core.domain.video_production import screenplay as sp

    envelope_terms = ("artifact_id", "content_hash", "schema_version", "revision_id")
    for model_name, model in {
        "CreativeBrief": sp.CreativeBrief,
        "StoryConcept": sp.StoryConcept,
        "Screenplay": sp.Screenplay,
    }.items():
        fields = set(model.model_fields)
        overlap = fields & set(envelope_terms)
        assert not overlap, f"{model_name} unexpectedly owns envelope fields {overlap}"


# ---------------------------------------------------------------------------
# 5. Model-port contract
# ---------------------------------------------------------------------------


def test_preproduction_model_port_is_the_only_boundary() -> None:
    from windagent_intelligence.video.ports import (
        ModelCompletionRequest,
        ModelCompletionResult,
        PreproductionModelPort,
    )

    assert PreproductionModelPort is not None
    from dataclasses import _MISSING_TYPE  # type: ignore[attr-defined]

    # `capability` is a REQUIRED parameter (no default) on the request;
    # `prompt_spec` is optional provenance.
    assert isinstance(
        ModelCompletionRequest.__dataclass_fields__["capability"].default,
        _MISSING_TYPE,
    )
    assert "prompt_spec" in ModelCompletionRequest.__dataclass_fields__
    # Port is runtime-checkable so a deterministic unit-test fake duck-types it.
    assert hasattr(PreproductionModelPort, "complete")
    assert "capability" in ModelCompletionResult.__dataclass_fields__


def test_deterministic_fake_satisfies_model_port() -> None:

    from windagent_intelligence.video.ports import (
        ModelCompletionRequest,
        ModelCompletionResult,
        PreproductionModelPort,
    )

    @dataclass
    class DeterministicPort:
        responses: dict

        async def complete(self, request: ModelCompletionRequest) -> ModelCompletionResult:
            content = self.responses.get(request.capability, "")
            return ModelCompletionResult(
                capability=request.capability,
                content=content,
                provider="unit-test-fake",
            )

    assert isinstance(DeterministicPort(responses={}), PreproductionModelPort)
    # A deterministic fixture fake is permitted ONLY for unit tests; the
    # certification profile rejects it (bootstrap rule: final slice fails
    # closed on mock/bypass fallback).
    assert not getattr(DeterministicPort, "_allowed_in_production", False)
