"""
Contract and Intermediate Representation (IR) Tests for Code Video (Phase 1).

Covers all Phase 1 gate requirements from ban_ke_hoach_video_02.md:
- schema roundtrip (dict, JSON, YAML)
- duplicate scene ID rejection
- overlapping scene and gap policy
- action validation and scene boundary containment
- invalid / non-integer durations
- action outside scene bounds
- unknown action rejection
- missing source hash rejection
- semantic action validation (rejection of raw pixel coordinates)
- audio parameter rejection (forbidding audio_path, tts_model, voice_id)
- voice cue sheet CSV generation
- workflow definition DAG and step contracts
"""

from __future__ import annotations

import csv
import io
import pytest

from windagent_core.errors.exceptions import ValidationError
from windagent_workflows.code_video.contracts import (
    Action,
    ActionType,
    Annotation,
    CodeVideoPlan,
    ExpectedState,
    OutputPolicy,
    Resolution,
    Scene,
    VisualMode,
)
from windagent_workflows.code_video.definition import (
    CODE_VIDEO_STEPS,
    all_step_contracts,
    build_code_video_step_nodes,
    step_contract,
)


def _make_valid_sample_plan() -> CodeVideoPlan:
    """Helper to build a valid sample 2-scene CodeVideoPlan."""
    scene_1 = Scene(
        scene_id="S01",
        title="Cold Open",
        start_ms=0,
        end_ms=25000,
        visual_mode=VisualMode.CODE_STUDIO,
        actions=[
            Action(
                action_id="A01_01",
                action_type=ActionType.RUN_TERMINAL,
                start_ms=1000,
                duration_ms=5000,
                params={"command": "python -m src.agent", "expected_exit_code": 0},
            ),
            Action(
                action_id="A01_02",
                action_type=ActionType.HIGHLIGHT,
                start_ms=7000,
                duration_ms=3000,
                params={"symbol": "Agent.run"},
            ),
        ],
        expected_state=ExpectedState(
            active_file="src/agent.py",
            terminal_last_command="python -m src.agent",
            terminal_exit_code=0,
        ),
        annotations=[
            Annotation(
                annotation_id="ANN_01",
                kind="callout",
                text="Simple Agent Demonstration",
                start_ms=2000,
                duration_ms=4000,
            )
        ],
        voice_cue_id="COLD_OPEN",
    )

    scene_2 = Scene(
        scene_id="S02",
        title="Hook",
        start_ms=25000,
        end_ms=50000,
        visual_mode=VisualMode.TITLE_CARD,
        actions=[
            Action(
                action_id="A02_01",
                action_type=ActionType.SHOW_TITLE,
                start_ms=26000,
                duration_ms=4000,
                params={"title": "Viết AI Agent đầu tiên bằng Python"},
            )
        ],
        voice_cue_id="HOOK",
    )

    return CodeVideoPlan(
        video_id="video-02",
        schema_version="1.0.0",
        title="Video 02 — Viết AI Agent đầu tiên bằng Python",
        duration_ms=50000,
        fps=30,
        resolution=Resolution(width=2560, height=1440),
        scenes=[scene_1, scene_2],
        source_hash="b2c9d46fd74cccc5f48de8509ceef41aec2dfb8db63a78c733a3d961ec1bec6c",
        output_policy=OutputPolicy(
            master_resolution="2560x1440",
            delivery_resolutions=["1920x1080"],
            fps=30,
            audio_policy="EXCLUDED",
        ),
        metadata={"tutorial_project": "agentic-studio", "milestone": "v0.1"},
    )


class TestCodeVideoContracts:
    """Test suite for CodeVideoPlan and intermediate representation contracts."""

    def test_resolution_helpers(self) -> None:
        res = Resolution(2560, 1440)
        assert res.aspect_ratio == "2560:1440"
        assert res.to_string() == "2560x1440"
        assert res.to_dict() == {"width": 2560, "height": 1440}

        parsed = Resolution.from_string("1920x1080")
        assert parsed.width == 1920
        assert parsed.height == 1080

        with pytest.raises(ValidationError):
            Resolution.from_string("invalid_res")
        with pytest.raises(ValidationError):
            Resolution.from_string("-100x200")

    def test_schema_roundtrip_dict_json_yaml(self) -> None:
        plan = _make_valid_sample_plan()
        plan.validate()

        # Dict roundtrip
        dict_data = plan.to_dict()
        reconstructed_from_dict = CodeVideoPlan.from_dict(dict_data)
        reconstructed_from_dict.validate()
        assert reconstructed_from_dict.video_id == plan.video_id
        assert reconstructed_from_dict.duration_ms == plan.duration_ms
        assert len(reconstructed_from_dict.scenes) == 2
        assert reconstructed_from_dict.total_actions == 3

        # JSON roundtrip
        json_str = plan.to_json()
        reconstructed_from_json = CodeVideoPlan.from_json(json_str)
        reconstructed_from_json.validate()
        assert reconstructed_from_json.to_dict() == dict_data

        # YAML roundtrip
        yaml_str = plan.to_yaml()
        reconstructed_from_yaml = CodeVideoPlan.from_yaml(yaml_str)
        reconstructed_from_yaml.validate()
        assert reconstructed_from_yaml.to_dict() == dict_data

    def test_reject_duplicate_scene_id(self) -> None:
        plan = _make_valid_sample_plan()
        # Duplicate scene ID S01
        duplicate_scene = Scene(
            scene_id="S01",
            title="Duplicate S01",
            start_ms=50000,
            end_ms=75000,
            visual_mode=VisualMode.TITLE_CARD,
        )
        invalid_plan = CodeVideoPlan(
            video_id="video-02",
            schema_version="1.0.0",
            title="Invalid Plan",
            duration_ms=75000,
            fps=30,
            resolution=Resolution(2560, 1440),
            scenes=[plan.scenes[0], plan.scenes[1], duplicate_scene],
            source_hash="sha256_mock",
        )
        with pytest.raises(ValidationError, match="Duplicate scene_id 'S01'"):
            invalid_plan.validate()

    def test_reject_duplicate_action_id_in_scene(self) -> None:
        scene = Scene(
            scene_id="S01",
            title="Scene with duplicate action",
            start_ms=0,
            end_ms=10000,
            visual_mode=VisualMode.CODE_STUDIO,
            actions=[
                Action(
                    action_id="ACT_01",
                    action_type=ActionType.OPEN_FILE,
                    start_ms=1000,
                    duration_ms=2000,
                    params={"path": "src/agent.py"},
                ),
                Action(
                    action_id="ACT_01",
                    action_type=ActionType.HIGHLIGHT,
                    start_ms=4000,
                    duration_ms=2000,
                    params={"symbol": "Agent"},
                ),
            ],
        )
        errors = scene.validate()
        assert any("Duplicate action_id 'ACT_01'" in e for e in errors)

    def test_reject_overlapping_scenes_and_gaps(self) -> None:
        scene_1 = Scene(
            scene_id="S01",
            title="Scene 1",
            start_ms=0,
            end_ms=10000,
            visual_mode=VisualMode.CODE_STUDIO,
        )
        # Overlapping: starts at 9000 instead of 10000
        scene_2_overlap = Scene(
            scene_id="S02",
            title="Scene 2 Overlap",
            start_ms=9000,
            end_ms=20000,
            visual_mode=VisualMode.CODE_STUDIO,
        )
        plan_overlap = CodeVideoPlan(
            video_id="video-02",
            schema_version="1.0.0",
            title="Overlap Plan",
            duration_ms=20000,
            fps=30,
            resolution=Resolution(2560, 1440),
            scenes=[scene_1, scene_2_overlap],
            source_hash="mock_hash",
        )
        with pytest.raises(ValidationError, match="overlaps previous scene"):
            plan_overlap.validate()

        # Gap: starts at 12000 instead of 10000
        scene_2_gap = Scene(
            scene_id="S02",
            title="Scene 2 Gap",
            start_ms=12000,
            end_ms=20000,
            visual_mode=VisualMode.CODE_STUDIO,
        )
        plan_gap = CodeVideoPlan(
            video_id="video-02",
            schema_version="1.0.0",
            title="Gap Plan",
            duration_ms=20000,
            fps=30,
            resolution=Resolution(2560, 1440),
            scenes=[scene_1, scene_2_gap],
            source_hash="mock_hash",
        )
        with pytest.raises(ValidationError, match="Gap before scene 'S02'"):
            plan_gap.validate()

    def test_action_bounds_validation(self) -> None:
        # Action starts before scene start
        scene_early_action = Scene(
            scene_id="S01",
            title="Scene Early Action",
            start_ms=5000,
            end_ms=10000,
            visual_mode=VisualMode.CODE_STUDIO,
            actions=[
                Action(
                    action_id="ACT_EARLY",
                    action_type=ActionType.OPEN_FILE,
                    start_ms=2000,  # Before scene start 5000
                    duration_ms=1000,
                    params={"path": "src/agent.py"},
                )
            ],
        )
        errors = scene_early_action.validate()
        assert any("is before scene start_ms" in e for e in errors)

        # Action ends after scene end
        scene_late_action = Scene(
            scene_id="S01",
            title="Scene Late Action",
            start_ms=5000,
            end_ms=10000,
            visual_mode=VisualMode.CODE_STUDIO,
            actions=[
                Action(
                    action_id="ACT_LATE",
                    action_type=ActionType.OPEN_FILE,
                    start_ms=8000,
                    duration_ms=4000,  # Ends at 12000 > 10000
                    params={"path": "src/agent.py"},
                )
            ],
        )
        errors = scene_late_action.validate()
        assert any("exceeds scene end_ms" in e for e in errors)

    def test_invalid_and_non_integer_durations(self) -> None:
        # Scene end <= start
        with pytest.raises(ValidationError):
            Scene(
                scene_id="S01",
                title="Invalid scene",
                start_ms=10000,
                end_ms=5000,
                visual_mode=VisualMode.CODE_STUDIO,
            )

        # Action negative start
        with pytest.raises(ValidationError):
            Action(
                action_id="ACT_01",
                action_type=ActionType.WAIT,
                start_ms=-100,
                duration_ms=1000,
            )

        # Plan duration mismatch with scenes sum
        plan = _make_valid_sample_plan()
        mismatched_plan = CodeVideoPlan(
            video_id=plan.video_id,
            schema_version=plan.schema_version,
            title=plan.title,
            duration_ms=99999,  # does not match scene sum 50000
            fps=plan.fps,
            resolution=plan.resolution,
            scenes=plan.scenes,
            source_hash=plan.source_hash,
        )
        with pytest.raises(ValidationError, match="does not match plan duration_ms"):
            mismatched_plan.validate()

    def test_semantic_action_rule_rejects_pixel_coordinates(self) -> None:
        # Action with x, y coordinate should be rejected
        with pytest.raises(ValidationError, match="contains non-semantic coordinate key 'x'"):
            Action(
                action_id="ACT_CLICK",
                action_type=ActionType.HIGHLIGHT,
                start_ms=1000,
                duration_ms=2000,
                params={"x": 712, "y": 418, "symbol": "Message"},
            )

        with pytest.raises(ValidationError, match="contains non-semantic coordinate key 'pixel_x'"):
            Action(
                action_id="ACT_PIXEL",
                action_type=ActionType.SELECT_RANGE,
                start_ms=1000,
                duration_ms=2000,
                params={"pixel_x": 100, "line_start": 5},
            )

    def test_unknown_action_type_rejection(self) -> None:
        with pytest.raises(ValidationError, match="Unknown action_type 'CLICK_COORDINATE'"):
            Action.from_dict({
                "action_id": "ACT_BAD",
                "action_type": "CLICK_COORDINATE",
                "start_ms": 1000,
                "duration_ms": 500,
                "params": {},
            })

    def test_missing_source_hash_rejection(self) -> None:
        plan = _make_valid_sample_plan()
        with pytest.raises(ValidationError, match="source_hash is required"):
            CodeVideoPlan(
                video_id="video-02",
                schema_version="1.0.0",
                title="No Hash Plan",
                duration_ms=50000,
                fps=30,
                resolution=Resolution(2560, 1440),
                scenes=plan.scenes,
                source_hash="",  # Empty
            )

    def test_audio_forbidden_fields_rejection(self) -> None:
        # Forbid audio parameters in metadata
        plan = _make_valid_sample_plan()
        with pytest.raises(ValidationError, match="Forbidden audio parameter 'tts_model'"):
            CodeVideoPlan(
                video_id="video-02",
                schema_version="1.0.0",
                title="Audio Forbidden Plan",
                duration_ms=50000,
                fps=30,
                resolution=Resolution(2560, 1440),
                scenes=plan.scenes,
                source_hash=plan.source_hash,
                metadata={"tts_model": "eleven_labs_v2"},
            )

        # Forbid root audio keys in from_dict
        dict_data = plan.to_dict()
        dict_data["audio_path"] = "audio/voiceover.mp3"
        with pytest.raises(ValidationError, match="Forbidden root audio key 'audio_path'"):
            CodeVideoPlan.from_dict(dict_data)

    def test_voice_cue_sheet_csv_generation(self) -> None:
        plan = _make_valid_sample_plan()
        csv_text = plan.generate_cue_sheet_csv()

        reader = list(csv.reader(io.StringIO(csv_text)))
        assert len(reader) == 3  # Header + 2 scenes
        header = reader[0]
        assert header == ["scene_id", "title", "start_timecode", "end_timecode", "duration_seconds", "voice_reference"]

        row1 = reader[1]
        assert row1[0] == "S01"
        assert row1[1] == "Cold Open"
        assert row1[2] == "00:00.000"
        assert row1[3] == "00:25.000"
        assert row1[4] == "25.000"
        assert row1[5] == "COLD_OPEN"

        row2 = reader[2]
        assert row2[0] == "S02"
        assert row2[1] == "Hook"
        assert row2[2] == "00:25.000"
        assert row2[3] == "00:50.000"
        assert row2[4] == "25.000"
        assert row2[5] == "HOOK"

    def test_plan_helpers_and_lookups(self) -> None:
        plan = _make_valid_sample_plan()
        assert plan.total_scenes == 2
        assert plan.total_actions == 3

        scene_s01 = plan.get_scene("S01")
        assert scene_s01 is not None
        assert scene_s01.title == "Cold Open"

        assert plan.get_scene("NON_EXISTENT") is None

        found_action = plan.get_action("A01_02")
        assert found_action is not None
        parent_scene, action = found_action
        assert parent_scene.scene_id == "S01"
        assert action.action_type == ActionType.HIGHLIGHT


class TestCodeVideoWorkflowDefinition:
    """Test suite for Code Video workflow steps and scheduling DAG."""

    def test_step_constants_and_counts(self) -> None:
        assert len(CODE_VIDEO_STEPS) == 9
        assert CODE_VIDEO_STEPS[0] == "COMPILE_PLAN"
        assert CODE_VIDEO_STEPS[-1] == "FINAL_QC"

    def test_build_code_video_step_nodes(self) -> None:
        nodes = build_code_video_step_nodes()
        assert len(nodes) == 9

        # First step has no dependencies
        assert nodes[0].step_id == "COMPILE_PLAN"
        assert nodes[0].dependencies == ()

        # Second step depends on first
        assert nodes[1].step_id == "BUILD_WORKSPACE"
        assert nodes[1].dependencies == ("COMPILE_PLAN",)

        # All steps have 0 external cost (deterministic offline generation)
        for node in nodes:
            assert node.external_cost is False

    def test_step_contracts(self) -> None:
        contracts = all_step_contracts()
        assert len(contracts) == 9

        c_compile = step_contract("COMPILE_PLAN")
        assert c_compile["step_id"] == "COMPILE_PLAN"
        assert "video_plan" in c_compile["output_artifact_types"]
        assert c_compile["retry_class"] == "fast"

        with pytest.raises(KeyError):
            step_contract("UNKNOWN_STEP")
