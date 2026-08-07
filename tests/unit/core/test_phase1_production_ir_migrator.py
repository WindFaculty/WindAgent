"""
Unit tests for the VP3D Phase 1 legacy-to-IR migrator.

Proves (plan §4 "Kiểm thử"): a legacy VideoProductionPackage v1 fixture
migrates onto the Production IR without losing ID, ordering, provenance or
approval state, and that GenerationModeDecision / FlowGenerationSpecification /
GenerationRequest map onto engine-neutral semantics (mode DROPPED, creative
value + references kept). The legacy input types are imported from the bounded
`legacy_v1` compatibility layer (see legacy_v1/SUNSET.md).
"""

from windagent_core.domain.video_production import (
    ProductionIrDocument,
    ProductionIrMigrator,
)
from windagent_core.domain.video_production.legacy_v1 import (
    FlowGenerationSpecification,
    GenerationMode,
    GenerationModeDecision,
    GenerationModeReasonCode,
    LegacyGenerationRequest,
)
from windagent_core.domain.video_production.package import VideoProductionPackage

from tests.fixtures.video_production.fixture_builder import build_valid_package


class TestPackageMigrationPreservesInvariants:
    def test_ids_and_ordering_preserved(self):
        package = build_valid_package()
        ir = ProductionIrMigrator().migrate_package(package)

        assert ir.project_id == package.project_id
        assert ir.revision_id == package.revision_id
        assert ir.source_package_hash == package.content_hash()

        # scene id preserved
        scene = package.screenplay.scenes[0]
        ir_scene = ir.scenes[0]
        assert str(ir_scene.screenplay_scene_id) == str(scene.scene_id)
        assert str(ir_scene.scene_id) == str(scene.scene_id)

        # shot id + order preserved
        shot = package.cinematic_plan.graph.shots[0]
        ir_shot = ir.shots[0]
        assert str(ir_shot.shot_id) == str(shot.shot_id)
        assert ir_shot.order == shot.order
        assert ir_shot.duration_seconds == shot.duration_seconds

        # character + location ids preserved
        char = package.characters[0]
        loc = package.locations[0]
        assert str(ir_scene.characters[0].character_id) == str(char.character_id)
        assert str(ir_scene.environment[0].location_id) == str(loc.location_id)

    def test_provenance_and_approval_state_preserved(self):
        package = build_valid_package()
        ir = ProductionIrMigrator().migrate_package(package)

        assert ir.provenance.get("created_by") == package.provenance.created_by
        assert ir.locked == package.approvals.locked
        assert ir.approval_state_ref == package.approvals.approvals[-1].target_hash

    def test_dialogue_lines_preserved(self):
        package = build_valid_package()
        ir = ProductionIrMigrator().migrate_package(package)

        shot = package.cinematic_plan.graph.shots[0]
        expected_dialogue = [str(d) for d in shot.dialogue_line_ids]
        if expected_dialogue:
            ir_track = ir.shots[0].dialogue_tracks[0]
            assert [str(d) for d in ir_track.dialogue_line_ids] == expected_dialogue

    def test_ir_contains_no_generation_mode(self):
        package = build_valid_package()
        ir = ProductionIrMigrator().migrate_package(package)
        raw = ir.serialize()
        for forbidden in ("generation_mode", "TEXT_TO_VIDEO", "preferred_mode"):
            assert forbidden not in raw, f"Migrated IR leaks {forbidden}"

    def test_ir_validates_clean(self):
        package = build_valid_package()
        ir = ProductionIrMigrator().migrate_package(package)
        from windagent_core.domain.video_production import ProductionIrValidator

        blocking = [i for i in ProductionIrValidator().validate(ir) if i.blocking]
        assert blocking == []

    def test_document_is_engine_neutral_and_deserializable(self):
        package = build_valid_package()
        ir = ProductionIrMigrator().migrate_package(package)
        restored = ProductionIrDocument.deserialize(ir.serialize())
        assert restored.content_hash() == ir.content_hash()

    def test_multi_character_scene_gets_distinct_instance_ids(self):
        """Regression: instance ids must derive from CHARACTER ids, never from
        the scene id, so a scene with several characters never duplicates ids
        and each CharacterId is preserved."""
        data = build_valid_package().model_dump()
        # second character in the same scene
        data["characters"].append(
            {
                "character_id": "chr_sidekick_02",
                "name": "Sidekick",
                "role": "SUPPORTING",
                "visual_traits": {"age": "young"},
                "costume_descriptions": ["brown tunic"],
                "portrait_asset_ids": [],
            }
        )
        data["screenplay"]["scenes"][0]["character_ids"] = ["chr_hero_01", "chr_sidekick_02"]
        package = VideoProductionPackage.model_validate(data)

        ir = ProductionIrMigrator().migrate_package(package)
        instance_ids = [str(i.instance_id) for i in ir.scenes[0].characters]
        assert len(instance_ids) == len(set(instance_ids)), "duplicate instance ids"
        assert "chr_hero_01" in instance_ids
        assert "chr_sidekick_02" in instance_ids
        # the shot references BOTH characters of its scene
        assert sorted(ir.shots[0].characters) == ["chr_hero_01", "chr_sidekick_02"]

        from windagent_core.domain.video_production import ProductionIrValidator

        blocking = [i for i in ProductionIrValidator().validate(ir) if i.blocking]
        assert blocking == []


class TestComponentMigrationSemantics:
    def test_generation_mode_decision_not_carried(self):
        decision = GenerationModeDecision(
            preferred_mode=GenerationMode.IMAGE_TO_VIDEO,
            acceptable_fallback_modes=[GenerationMode.INGREDIENTS_TO_VIDEO],
            reason_code=GenerationModeReasonCode.IDENTITY_REFERENCE_REQUIRED,
            rationale="identity reference mandatory",
        )
        mapped = ProductionIrMigrator.migrate_generation_mode_decision(decision)
        assert mapped["carried"] is False
        assert mapped["generation_mode"] == "NOT_CARRIED_INTO_IR"
        assert mapped["advisory_rationale"] == "identity reference mandatory"

    def test_flow_generation_specification_keeps_prompt_and_drops_mode(self):
        from windagent_core.domain.video_production.prompt_compiler import CompiledPrompt, PromptBlock
        from windagent_core.domain.video_production.enums import PromptBlockType
        from windagent_core.domain.video_production.ids import CompiledPromptId, PromptBlockId

        block = PromptBlock(
            block_id=PromptBlockId("pb_0001"),
            block_type=PromptBlockType.ACTION,
            content="hero walks to the clearing",
            required=True,
            order=1,
        )
        prompt = CompiledPrompt(
            prompt_id=CompiledPromptId("cp_0001"),
            shot_id="sht_010",
            blocks=[block],
            text="hero walks to the clearing",
            prompt_hash="a" * 64,
        )
        spec = FlowGenerationSpecification(
            spec_id="fspec_0001",
            shot_id="sht_010",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            prompt=prompt,
            reference_hashes=["a" * 64],
        )
        mapped = ProductionIrMigrator.migrate_flow_generation_specification(spec)
        assert mapped["generation_mode"] == "NOT_CARRIED_INTO_IR"
        assert mapped["reference_hashes"] == ["a" * 64]
        assert mapped["creative_prompt"] == "hero walks to the clearing"

    def test_generation_request_keeps_identity_and_drops_provider(self):
        request = LegacyGenerationRequest(
            request_id="req_0001",
            project_id="vp_fixture_0001",
            revision_id="rev_0003",
            shot_id="sht_010",
            generation_mode=GenerationMode.TEXT_TO_VIDEO,
            provider="google_flow_browser",
            prompt_hash="a" * 64,
            request_hash="b" * 64,
        )
        mapped = ProductionIrMigrator.migrate_generation_request(request)
        assert mapped["carried"] is True
        assert mapped["request_id"] == "req_0001"
        assert mapped["generation_mode"] == "NOT_CARRIED_INTO_IR"
        assert mapped["provider"] == "NOT_CARRIED_INTO_IR"

    def test_mapping_table_covers_all_legacy_sources(self):
        sources = {row["legacy"].split(".")[0] for row in ProductionIrMigrator.mapping_table()}
        for required in ("VideoProductionPackage", "Shot", "GenerationModeDecision", "FlowGenerationSpecification", "GenerationRequest"):
            assert required in sources, f"mapping table missing source {required}"
