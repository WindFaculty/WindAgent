"""
Tests for CodeVideoScriptCompiler and Phase 4 Plan Artifacts.
"""

from __future__ import annotations

import csv
from pathlib import Path
import tempfile

from windagent_tools.code_video.compiler import CodeVideoScriptCompiler
from windagent_workflows.code_video.contracts import CodeVideoPlan


class TestCodeVideoCompiler:
    """Test suite verifying compilation of Video 02 script into IR plan."""

    def test_compile_video_02_plan_duration_and_scene_count(self) -> None:
        compiler = CodeVideoScriptCompiler()
        plan = compiler.compile_video_02_plan()

        assert plan.video_id == "video-02"
        assert plan.duration_ms == 975_000  # 16:15.000
        assert len(plan.scenes) == 19
        assert plan.fps == 30
        assert plan.resolution.width == 2560
        assert plan.resolution.height == 1440

        expected_scene_ids = [f"S{i:02d}" for i in range(1, 20)]
        actual_scene_ids = [s.scene_id for s in plan.scenes]
        assert actual_scene_ids == expected_scene_ids

    def test_contiguous_timeline_without_overlaps_or_gaps(self) -> None:
        compiler = CodeVideoScriptCompiler()
        plan = compiler.compile_video_02_plan()

        current_ms = 0
        for scene in plan.scenes:
            assert scene.start_ms == current_ms, f"Scene {scene.scene_id} gap or overlap at {scene.start_ms}ms"
            assert scene.end_ms > scene.start_ms
            assert scene.duration_ms == scene.end_ms - scene.start_ms
            current_ms = scene.end_ms

        assert current_ms == 975_000

    def test_semantic_actions_and_bounds_validation(self) -> None:
        compiler = CodeVideoScriptCompiler()
        plan = compiler.compile_video_02_plan()

        total_actions = 0
        for scene in plan.scenes:
            validation_errors = scene.validate()
            assert not validation_errors, f"Validation errors in scene {scene.scene_id}: {validation_errors}"

            for action in scene.actions:
                total_actions += 1
                assert action.start_ms >= scene.start_ms
                assert action.end_ms <= scene.end_ms
                assert action.duration_ms >= 0

        assert total_actions > 20

    def test_export_plan_artifacts_and_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            compiler = CodeVideoScriptCompiler()
            plan = compiler.compile_video_02_plan()

            artifacts = compiler.export_plan_artifacts(plan=plan, output_dir=out_path)

            yaml_file = artifacts["yaml"]
            json_file = artifacts["json"]
            csv_file = artifacts["csv"]

            assert yaml_file.exists()
            assert json_file.exists()
            assert csv_file.exists()

            # YAML roundtrip
            loaded_from_yaml = CodeVideoPlan.from_yaml(yaml_file.read_text(encoding="utf-8"))
            assert loaded_from_yaml.video_id == plan.video_id
            assert loaded_from_yaml.duration_ms == plan.duration_ms
            assert len(loaded_from_yaml.scenes) == 19

            # JSON roundtrip
            loaded_from_json = CodeVideoPlan.from_json(json_file.read_text(encoding="utf-8"))
            assert loaded_from_json.video_id == plan.video_id
            assert loaded_from_json.duration_ms == plan.duration_ms
            assert len(loaded_from_json.scenes) == 19

            # CSV Cue Sheet verification
            with csv_file.open(mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 19
                assert rows[0]["scene_id"] == "S01"
                assert rows[0]["start_timecode"] == "00:00.000"
                assert rows[-1]["scene_id"] == "S19"
                assert rows[-1]["end_timecode"] == "16:15.000"

    def test_source_hash_detection_from_script(self) -> None:
        script_file = Path("artifacts/code_video/video_02/source/script.md")
        if script_file.exists():
            compiler = CodeVideoScriptCompiler(script_path=script_file)
            plan = compiler.compile_video_02_plan()
            assert plan.source_hash == "b2c9d46fd74cccc5f48de8509ceef41aec2dfb8db63a78c733a3d961ec1bec6c"
