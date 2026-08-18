"""
Contract and Unit Test Suite for Deterministic Replay Engine (Phase 6).

Verifies:
- Typing speed simulation across modes (instant, fast, normal, slow, custom cps)
- Preflight verified terminal playback and anti-fake SCRIPT_RUNTIME_MISMATCH detection
- Checkpoint code fragment resolution across checkpoints cp_00 to cp_09
- ReplayStepRecord and ReplayTrace generation with composite hash calculation
- State synchronization and expected_state validation at scene boundaries
- Fast recovery & resumability via resume_from(scene_id, action_id)
- Full 19-scene plan replay execution against Video 02 timeline (975,000 ms)
- Multi-run determinism gate verification (identical action sequence hash, checkpoint hash, terminal hash)
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_workflows.code_video.compiler import CodeVideoScriptCompiler
from windagent_workflows.code_video.contracts import (
    Action,
    ActionType,
    CodeVideoPlan,
    ExpectedState,
    Resolution,
    Scene,
    VisualMode,
)
from windagent_workflows.code_video.replay import (
    CHECKPOINT_CODE_MAP,
    CheckpointCodeResolver,
    DeterministicReplayEngine,
    ReplayStepRecord,
    ReplayTrace,
    SPEED_MODE_CPS_MAP,
    TerminalReplayExecutor,
    TypingSimulator,
    TypingSpeedMode,
    VERIFIED_TERMINAL_RECEIPTS,
)

from windagent_tools.code_video.renderer.studio_renderer import CodeStudioRenderer
from windagent_tools.code_video.renderer.terminal_renderer import TerminalRenderer


class TestTypingSimulator:
    """Test suite for typing speed simulator."""

    def test_instant_typing(self) -> None:
        target = "class SimpleAgent:\n    pass\n"
        text, line, col = TypingSimulator.compute_typed_state(
            target_text=target,
            elapsed_ms=100,
            total_duration_ms=5000,
            mode=TypingSpeedMode.INSTANT,
        )
        assert text == target
        assert line == 3
        assert col == 1

    def test_normal_typing_progression(self) -> None:
        target = "def run(self):\n    return 'done'"
        # At 0ms -> empty
        text0, line0, col0 = TypingSimulator.compute_typed_state(
            target_text=target,
            elapsed_ms=0,
            total_duration_ms=10000,
            mode=TypingSpeedMode.NORMAL,
        )
        assert text0 == ""

        # At mid-point -> partially typed
        text_mid, line_mid, col_mid = TypingSimulator.compute_typed_state(
            target_text=target,
            elapsed_ms=5000,
            total_duration_ms=10000,
            mode=TypingSpeedMode.NORMAL,
        )
        assert len(text_mid) > 0
        assert len(text_mid) <= len(target)
        assert target.startswith(text_mid)

        # At end -> fully typed
        text_end, line_end, col_end = TypingSimulator.compute_typed_state(
            target_text=target,
            elapsed_ms=10000,
            total_duration_ms=10000,
            mode=TypingSpeedMode.NORMAL,
        )
        assert text_end == target

    def test_custom_cps(self) -> None:
        target = "0123456789"
        # 10 chars at 5 chars/sec -> in 1000ms should type 5 chars
        text, line, col = TypingSimulator.compute_typed_state(
            target_text=target,
            elapsed_ms=1000,
            total_duration_ms=2000,
            mode=TypingSpeedMode.CUSTOM,
            chars_per_second=5.0,
        )
        assert len(text) == 5
        assert text == "01234"


class TestTerminalReplayExecutor:
    """Test suite for terminal execution playback and anti-fake verification."""

    def test_verified_command_execution(self) -> None:
        executor = TerminalReplayExecutor()
        renderer = TerminalRenderer()

        action = Action(
            action_id="act_test_pytest",
            action_type=ActionType.RUN_TERMINAL,
            start_ms=0,
            duration_ms=2000,
            params={"command": "pytest", "expected_passes": 2},
        )

        result = executor.execute_terminal_action(action, renderer, strict=True)
        assert result["exit_code"] == 0
        assert "2 passed" in result["stdout"]
        assert renderer.state.last_command == "pytest"

    def test_unverified_command_strict_rejection(self) -> None:
        executor = TerminalReplayExecutor()
        renderer = TerminalRenderer()

        action = Action(
            action_id="act_unknown",
            action_type=ActionType.RUN_TERMINAL,
            start_ms=0,
            duration_ms=1000,
            params={"command": "python -m rm -rf /"},
        )

        with pytest.raises(ValidationError, match="SCRIPT_RUNTIME_MISMATCH"):
            executor.execute_terminal_action(action, renderer, strict=True)

    def test_pass_count_mismatch_rejection(self) -> None:
        executor = TerminalReplayExecutor()
        renderer = TerminalRenderer()

        # pytest output actually contains 2 passed, but action expects 3 passed
        action = Action(
            action_id="act_pytest_mismatch",
            action_type=ActionType.RUN_TERMINAL,
            start_ms=0,
            duration_ms=2000,
            params={"command": "pytest", "expected_passes": 3},
        )

        with pytest.raises(ValidationError, match="SCRIPT_RUNTIME_MISMATCH"):
            executor.execute_terminal_action(action, renderer, strict=True)


class TestCheckpointCodeResolver:
    """Test suite for checkpoint code fragment resolution."""

    def test_resolve_all_milestone_checkpoints(self) -> None:
        resolver = CheckpointCodeResolver()
        checkpoints = [
            "cp_00_init",
            "cp_01_message",
            "cp_02_config",
            "cp_03_llm_protocol",
            "cp_04_fake_llm",
            "cp_05_agent",
            "cp_06_tests",
            "cp_07_provider",
            "cp_09_v0_1",
        ]

        for cp in checkpoints:
            code = resolver.resolve_file_content(cp, "src/agent.py")
            assert len(code) > 0
            assert "Agent" in code or "Message" in code or "Agentic" in code

        test_code = resolver.resolve_file_content("cp_06_tests", "tests/test_agent.py")
        assert "def test_agent_runs_with_fake_llm" in test_code



class TestDeterministicReplayEngine:
    """Test suite for master ReplayEngine execution and determinism gate."""

    @pytest.fixture
    def video_02_plan(self) -> CodeVideoPlan:
        compiler = CodeVideoScriptCompiler()
        return compiler.compile_video_02_plan()

    def test_full_19_scene_replay_execution(self, video_02_plan: CodeVideoPlan) -> None:
        engine = DeterministicReplayEngine(plan=video_02_plan)
        trace = engine.execute_full_plan()

        assert trace.video_id == "video-02"
        assert trace.total_scenes == 19
        assert trace.total_duration_ms == 975_000
        assert trace.status == "VERIFIED"
        assert len(trace.steps) == video_02_plan.total_actions
        assert len(trace.action_sequence_hash) == 64
        assert len(trace.checkpoint_hash) == 64
        assert len(trace.terminal_output_hash) == 64
        assert len(trace.composite_replay_hash) == 64

    def test_timestamp_seeking_and_interpolation(self, video_02_plan: CodeVideoPlan) -> None:
        engine = DeterministicReplayEngine(plan=video_02_plan)

        # 0ms - Scene S01 (Cold Open)
        state_s01 = engine.step_to_timestamp(0)
        assert state_s01.visual_mode == VisualMode.SPLIT

        # 30,000ms - Scene S02 (Title Card)
        state_s02 = engine.step_to_timestamp(30_000)
        assert state_s02.visual_mode == VisualMode.TITLE_CARD

        # 180,000ms - Scene S06 (Message typing)
        state_s06 = engine.step_to_timestamp(180_000)
        assert state_s06.visual_mode == VisualMode.CODE_STUDIO
        assert state_s06.editor.active_file == "src/agent.py"
        assert len(state_s06.editor.content) > 0

        # 780,000ms - Scene S15 (Pytest run)
        state_s15 = engine.step_to_timestamp(780_000)
        assert state_s15.terminal.last_command == "pytest"

        # 975,000ms - End of video
        state_end = engine.step_to_timestamp(975_000)
        assert state_end.visual_mode == VisualMode.OUTRO

    def test_recovery_and_resumability(self, video_02_plan: CodeVideoPlan) -> None:
        engine = DeterministicReplayEngine(plan=video_02_plan)

        # Resume directly from S10 (Agent core class)
        resumed_s10 = engine.resume_from("S10")
        assert resumed_s10.visual_mode == VisualMode.CODE_STUDIO
        assert resumed_s10.editor.active_file == "src/agent.py"

        # Resume from S15 with specific action act_s15_02
        resumed_s15 = engine.resume_from("S15", "act_s15_02")
        assert resumed_s15.visual_mode == VisualMode.CODE_STUDIO
        assert resumed_s15.editor.active_file == "tests/test_agent.py"

        # Non-existent scene raises NotFoundError
        with pytest.raises(NotFoundError):
            engine.resume_from("S99_NON_EXISTENT")

    def test_determinism_gate_multi_run(self, video_02_plan: CodeVideoPlan) -> None:
        """Gate check: 2 runs must produce identical hashes."""
        engine = DeterministicReplayEngine(plan=video_02_plan)
        is_det, msg, hashes = engine.verify_determinism(runs=2)

        assert is_det is True
        assert "Verified 2 consecutive runs" in msg
        assert len(hashes["action_sequence_hash"]) == 64
        assert len(hashes["checkpoint_hash"]) == 64
        assert len(hashes["terminal_output_hash"]) == 64
        assert len(hashes["composite_replay_hash"]) == 64

    def test_expected_state_validation_failure(self, video_02_plan: CodeVideoPlan) -> None:
        engine = DeterministicReplayEngine(plan=video_02_plan)
        studio = CodeStudioRenderer()

        # Artificially mismatch active file
        studio.set_active_file("wrong_file.py")
        scene_with_exp = next(s for s in video_02_plan.scenes if s.expected_state and s.expected_state.active_file)

        is_valid, errors = engine.verify_scene_expected_state(scene_with_exp, studio.layout_state)
        assert is_valid is False
        assert any("active_file mismatch" in e for e in errors)
