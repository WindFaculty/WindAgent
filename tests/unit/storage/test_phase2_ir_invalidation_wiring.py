"""
VP3D Stage A Phase 2 — track-scoped IR invalidation WIRING test.

Proves the canonical `invalidate_scope` / `affected_outputs` mapping is USED by
a real storage caller (`IrTrackInvalidationService`), not merely unit-tested at
the domain layer:

- DIALOGUE change  -> ONLY audio / facial / final-cut records marked STALE
                      (scene geometry survives);
- CAMERA change    -> scene compile (SCENE_BLEND) + render records marked
                      STALE;
- unknown component kind -> fails closed (no silent no-op);
- a missing derived-artifact record fails closed (no silent no-op).
"""

import pytest

from windagent_core.domain.video_production.errors import VideoProductionProtocolError
from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    IrComponentKind,
)
from windagent_storage.video_production import (
    ArtifactRecord,
    ArtifactStatus,
    ArtifactType,
    ArtifactRecordStore,
    IrTrackInvalidationService,
)

SCENE = "scn_01"


def _record(artifact_id: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=artifact_id,
        artifact_type=ArtifactType.OTHER,
        content_sha256="0" * 64,
        byte_size=1,
        media_type="application/octet-stream",
        storage_locator="hash",
        producer="ir-fixture",
        project_id="vp_ir_0001",
        revision_id="rev_0001",
    )


def _aid(kind: DerivedArtifactKind) -> str:
    return f"{SCENE}__{kind.value}"


def _seed_store(tmp_path) -> ArtifactRecordStore:
    store = ArtifactRecordStore(tmp_path / "records")
    for kind in (
        DerivedArtifactKind.MIXED_AUDIO,
        DerivedArtifactKind.FACIAL_RENDER,
        DerivedArtifactKind.FINAL_CUT,
        DerivedArtifactKind.SCENE_BLEND,
        DerivedArtifactKind.FRAME_SEQUENCE,
        DerivedArtifactKind.RENDERED_CLIP,
    ):
        store.save(_record(_aid(kind)))
    return store


class TestDialogueChangeInvalidatesAudioFacialCutOnly:
    def test_dialogue_marks_only_audio_facial_cut(self, tmp_path):
        store = _seed_store(tmp_path)
        service = IrTrackInvalidationService(record_store=store)

        result = service.invalidate_component(
            IrComponentKind.DIALOGUE, SCENE, reason="dialogue line edited"
        )

        assert result.scope == "AUDIO_AND_FACIAL_AND_CUT"
        assert sorted(result.affected_artifact_kinds) == sorted(
            [
                DerivedArtifactKind.MIXED_AUDIO.value,
                DerivedArtifactKind.FACIAL_RENDER.value,
                DerivedArtifactKind.FINAL_CUT.value,
            ]
        )
        # Only those three were marked stale; scene geometry survives.
        assert sorted(result.marked_stale) == sorted(result.affected_artifact_ids)
        assert store.load(_aid(DerivedArtifactKind.SCENE_BLEND)).status == ArtifactStatus.VALID
        assert store.load(_aid(DerivedArtifactKind.FRAME_SEQUENCE)).status == ArtifactStatus.VALID
        assert store.load(_aid(DerivedArtifactKind.MIXED_AUDIO)).status == ArtifactStatus.STALE
        assert store.load(_aid(DerivedArtifactKind.FINAL_CUT)).status == ArtifactStatus.STALE
        # Audit entries are append-only.
        assert store.load(_aid(DerivedArtifactKind.FINAL_CUT)).history


class TestCameraChangeInvalidatesSceneCompileAndRender:
    def test_camera_marks_scene_blend_and_renders(self, tmp_path):
        store = _seed_store(tmp_path)
        service = IrTrackInvalidationService(record_store=store)

        result = service.invalidate_component(IrComponentKind.CAMERA, SCENE)

        assert result.scope == "SCENE_COMPILE_AND_RENDER"
        expected = {
            DerivedArtifactKind.SCENE_BLEND,
            DerivedArtifactKind.FRAME_SEQUENCE,
            DerivedArtifactKind.RENDERED_CLIP,
            DerivedArtifactKind.FINAL_CUT,
        }
        assert {DerivedArtifactKind(k) for k in result.affected_artifact_kinds} == expected
        # Audio is NOT invalidated by a camera change.
        assert store.load(_aid(DerivedArtifactKind.MIXED_AUDIO)).status == ArtifactStatus.VALID
        assert store.load(_aid(DerivedArtifactKind.SCENE_BLEND)).status == ArtifactStatus.STALE


class TestFailClosed:
    def test_unknown_component_kind_fails_closed(self, tmp_path):
        store = _seed_store(tmp_path)
        service = IrTrackInvalidationService(record_store=store)
        # A kind not in the canonical mapping must fail closed (never a
        # silent no-op). Enum construction rejects unknown members, so we pass
        # the raw value the canonical lookup would receive after coercion.
        with pytest.raises(VideoProductionProtocolError):
            service.affected_artifact_ids("NOT_A_KIND", SCENE)  # type: ignore[arg-type]

    def test_missing_derived_artifact_record_fails_closed(self, tmp_path):
        store = _seed_store(tmp_path)
        service = IrTrackInvalidationService(
            record_store=store,
            artifact_id_for=lambda scene_id, kind: f"{scene_id}__MISSING__{kind.value}",
        )
        with pytest.raises(ValueError):
            service.invalidate_component(IrComponentKind.DIALOGUE, SCENE)
