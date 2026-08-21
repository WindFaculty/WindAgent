"""
Unit tests for the VP3D Phase 1 Canonical Production IR.

Covers (plan §4 "Kiểm thử"):
- JSON round-trip and stable canonical hash;
- unknown MAJOR version fails closed; additive unknown fields accepted;
- no domain model imports Flow / Blender / Unreal (asserted here and in the
  architecture test);
- validation rules: unique ids, resolvable references, `.blend` always
  derived, camera present, duration matches camera;
- track-scoped invalidation: dialogue -> audio/facial/final cut;
  camera -> scene compile + dependent render.
"""

import hashlib

import pytest

from windagent_core.domain.video_production import (
    ProductionIrDocument,
    ProductionIrValidator,
    invalidate_scope,
    affected_outputs,
    IrComponentKind,
    IrInvalidationScope,
    DerivedArtifactKind,
)
from windagent_core.domain.video_production.errors import UnsupportedMajorVersionError
from windagent_core.domain.video_production.production_ir.enums import IrAssetFormat

from tests.fixtures.video_production.ir_fixture_builder import (
    build_valid_ir,
    build_valid_ir_dict,
)


class TestRoundTripAndHash:
    def test_json_round_trip(self):
        doc = build_valid_ir()
        raw = doc.serialize()
        restored = ProductionIrDocument.deserialize(raw)
        assert restored.model_dump() == doc.model_dump()

    def test_canonical_hash_stable_for_same_content(self):
        d1 = build_valid_ir()
        d2 = ProductionIrDocument.deserialize(d1.serialize())
        assert d1.content_hash() == d2.content_hash()
        assert len(d1.content_hash()) == 64

    def test_hash_changes_when_camera_changes(self):
        from windagent_core.domain.video_production.enums import CameraMovement

        base = build_valid_ir()
        changed = base.model_copy(
            deep=True,
            update={
                "shots": [
                    shot.model_copy(
                        deep=True,
                        update={
                            "camera": shot.camera.model_copy(
                                update={"movement": CameraMovement.PAN}
                            ),
                        },
                    )
                    for shot in base.shots
                ]
            },
        )
        assert changed.content_hash() != base.content_hash()

    def test_hash_excludes_provenance_and_lock_state(self):
        base = build_valid_ir()
        locked = base.model_copy(update={"locked": True, "provenance": {"created_by": "other"}})
        assert locked.content_hash() == base.content_hash()


class TestFailClosedVersioning:
    def test_unknown_major_version_fails_closed(self):
        data = build_valid_ir_dict()
        data["schema_version"] = "2.0.0"
        with pytest.raises(UnsupportedMajorVersionError):
            ProductionIrDocument.model_validate(data)

    def test_additive_unknown_field_accepted_within_major(self):
        data = build_valid_ir_dict()
        data["future_metadata"] = {"note": "forward compatible"}
        doc = ProductionIrDocument.model_validate(data)
        assert doc.schema_version == "1.0.0"

    def test_unknown_event_type_fails_closed(self):
        from windagent_core.events.video_production_ir import (
            ProductionIrEventEnvelope,
        )

        with pytest.raises(ValueError):
            ProductionIrEventEnvelope(
                event_type="video_production_ir.not_real",
                project_id="vp_ir_0001",
                revision_id="rev_0001",
                ir_id="ir_0001",
                aggregate_id="vp_ir_0001",
            )


class TestValidation:
    def test_valid_document_has_no_blocking_issues(self):
        doc = build_valid_ir()
        issues = ProductionIrValidator().validate(doc)
        assert [i for i in issues if i.blocking] == []

    def test_duplicate_shot_id_fails(self):
        doc = build_valid_ir()
        dup = doc.model_copy(
            deep=True,
            update={
                "shots": [doc.shots[0], doc.shots[0].model_copy()],
            },
        )
        issues = ProductionIrValidator().validate(dup)
        assert any(i.code.value == "DUPLICATE_SHOT_ID" for i in issues)

    def test_broken_reference_fails(self):
        doc = build_valid_ir()
        broken = doc.model_copy(
            deep=True,
            update={
                "shots": [
                    shot.model_copy(update={"scene_id": "scn_missing"})
                    for shot in doc.shots
                ]
            },
        )
        issues = ProductionIrValidator().validate(broken)
        assert any(i.code.value == "BROKEN_REFERENCE" for i in issues)

    def test_blend_asset_must_be_derived(self):
        doc = build_valid_ir()
        scene = doc.scenes[0]
        char = scene.characters[0]
        new_mesh = char.mesh.model_copy(
            update={
                "format": IrAssetFormat.BLEND,
                "uri": "file:///out/hero.blend",
                "derived": False,
            }
        )
        changed_scene = scene.model_copy(
            deep=True,
            update={
                "characters": [
                    char.model_copy(update={"mesh": new_mesh}) for _ in [char]
                ]
            },
        )
        changed = doc.model_copy(
            deep=True,
            update={"scenes": [changed_scene]},
        )
        issues = ProductionIrValidator().validate(changed)
        assert any(i.code.value == "BLEND_MUST_BE_DERIVED" for i in issues)

    def test_duration_mismatch_fails(self):
        doc = build_valid_ir()
        changed = doc.model_copy(
            deep=True,
            update={
                "shots": [
                    shot.model_copy(update={"duration_seconds": 9.0})
                    for shot in doc.shots
                ]
            },
        )
        issues = ProductionIrValidator().validate(changed)
        assert any(i.code.value == "DURATION_MISMATCH" for i in issues)

    def test_ensure_valid_document_raises_on_blocking_issue(self):
        from windagent_core.domain.video_production.production_ir.validation import (
            ensure_valid_document,
        )
        from windagent_core.domain.video_production.errors import VideoProductionProtocolError

        assert ensure_valid_document(build_valid_ir()) is None
        broken = build_valid_ir().model_copy(
            deep=True,
            update={"shots": [shot.model_copy(update={"scene_id": "scn_missing"}) for shot in build_valid_ir().shots]},
        )
        with pytest.raises(VideoProductionProtocolError):
            ensure_valid_document(broken)


class TestTrackScopedInvalidation:
    def test_dialogue_change_invalidates_audio_facial_cut(self):
        scope = invalidate_scope(IrComponentKind.DIALOGUE)
        assert scope == IrInvalidationScope.AUDIO_AND_FACIAL_AND_CUT
        outputs = affected_outputs(IrComponentKind.DIALOGUE)
        assert DerivedArtifactKind.MIXED_AUDIO in outputs
        assert DerivedArtifactKind.FACIAL_RENDER in outputs
        assert DerivedArtifactKind.FINAL_CUT in outputs
        # dialogue change NEVER invalidates baked scene geometry
        assert DerivedArtifactKind.SCENE_BLEND not in outputs

    def test_camera_change_invalidates_scene_compile_and_render(self):
        scope = invalidate_scope(IrComponentKind.CAMERA)
        assert scope == IrInvalidationScope.SCENE_COMPILE_AND_RENDER
        outputs = affected_outputs(IrComponentKind.CAMERA)
        assert DerivedArtifactKind.SCENE_BLEND in outputs
        assert DerivedArtifactKind.RENDERED_CLIP in outputs

    def test_render_profile_change_is_render_only(self):
        assert invalidate_scope(IrComponentKind.RENDER_PROFILE) == IrInvalidationScope.RENDER_ONLY
        outputs = affected_outputs(IrComponentKind.RENDER_PROFILE)
        assert DerivedArtifactKind.SCENE_BLEND not in outputs
        assert DerivedArtifactKind.RENDERED_CLIP in outputs

    def test_unknown_component_kind_fails_closed(self):
        from windagent_core.domain.video_production.errors import VideoProductionProtocolError

        class FakeKind:
            value = "NOT_A_KIND"

        with pytest.raises(VideoProductionProtocolError):
            invalidate_scope(FakeKind())  # type: ignore[arg-type]


class TestNoForbiddenConcepts:
    def test_ir_dump_contains_no_generation_mode_or_provider(self):
        raw = build_valid_ir().serialize()
        for forbidden in ("TEXT_TO_VIDEO", "IMAGE_TO_VIDEO", "VIDEO_EXTENSION", "generation_mode"):
            assert forbidden not in raw, f"IR leaks forbidden concept {forbidden}"

    def test_canonical_hash_matches_sha256_of_canonical_bytes(self):
        doc = build_valid_ir()
        assert doc.content_hash() == hashlib.sha256(doc.canonical_bytes()).hexdigest()


class TestDeepImmutability:
    """VP3D deep-immutability: frozen=True blocks reassignment AND the IR
    containers (list/dict, including nested) reject mutation at runtime.

    The plan (§4) requires "model immutable"; Phase 1 verdict claimed it, but
    frozen=True alone still lets `doc.shots.append(...)` and
    `doc.provenance['x']=1` mutate the document. These tests lock the
    deep-immutability contract (audit finding #4).
    """

    def test_list_field_rejects_mutation(self):
        doc = build_valid_ir()
        with pytest.raises(TypeError):
            doc.shots.append(doc.shots[0])
        with pytest.raises(TypeError):
            doc.shots[0] = doc.shots[0]

    def test_dict_field_rejects_mutation(self):
        doc = build_valid_ir()
        with pytest.raises(TypeError):
            doc.provenance["mutated"] = True
        with pytest.raises(TypeError):
            doc.model_copy(deep=True).provenance.clear()

    def test_nested_containers_are_frozen_recursively(self):
        doc = build_valid_ir()
        shot = doc.shots[0]
        for target in (shot.metadata, shot.camera.metadata):
            with pytest.raises(TypeError):
                target["mutated"] = True

    def test_model_copy_deep_and_serialization_still_work(self):
        doc = build_valid_ir()
        dup = doc.model_copy(deep=True)
        assert dup.model_dump() == doc.model_dump()
        assert ProductionIrDocument.deserialize(doc.serialize()).model_dump() == doc.model_dump()
        assert dup.content_hash() == doc.content_hash()
