"""
Tests for Golden Tutorial Builder and Video 02 Checkpoints (Phase 3).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import pytest

from windagent_core.errors.exceptions import ValidationError
from windagent_tools.code_video.workspace.golden_builder import (
    CheckpointDefinition,
    GoldenTutorialBuilder,
    STEP_00_INIT_TEST_CODE,
    STEP_01_MESSAGE_CODE,
    STEP_02_CONFIG_CODE,
    STEP_03_PROTOCOL_CODE,
    STEP_04_FAKE_LLM_CODE,
    STEP_05_AGENT_CODE,
    STEP_06_TESTS_CODE,
    STEP_07_FINAL_AGENT_CODE,
)
from windagent_tools.code_video.workspace.sandbox import TutorialWorkspace


class TestGoldenTutorialStepCodeContracts:
    """Validate python AST and execution of incremental code snippets."""

    def test_step_01_message_contract(self) -> None:
        namespace = {}
        exec(STEP_01_MESSAGE_CODE, namespace)
        Message = namespace["Message"]

        # Valid instances
        msg_user = Message(role="user", content="Hello world")
        assert msg_user.role == "user"
        assert msg_user.content == "Hello world"

        msg_sys = Message(role="system", content="You are an assistant")
        assert msg_sys.role == "system"

        msg_asst = Message(role="assistant", content="How can I help?")
        assert msg_asst.role == "assistant"

        # Immutability
        with pytest.raises((FrozenInstanceError, Exception)):
            msg_user.content = "New content"

        # Role validation
        with pytest.raises(ValueError, match="Invalid role"):
            Message(role="invalid_role", content="Hello")

        # Type validation
        with pytest.raises(TypeError, match="Message content must be a string"):
            Message(role="user", content=12345)

    def test_step_02_config_contract(self) -> None:
        namespace = {}
        exec(STEP_02_CONFIG_CODE, namespace)
        AgentConfig = namespace["AgentConfig"]

        config = AgentConfig(name="SimpleAgent", system_prompt="Be concise.")
        assert config.name == "SimpleAgent"
        assert config.system_prompt == "Be concise."
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.7

        # Name validation
        with pytest.raises(ValueError, match="cannot be empty"):
            AgentConfig(name="", system_prompt="test")

        # Temperature validation
        with pytest.raises(ValueError, match="Temperature must be between"):
            AgentConfig(name="Agent", system_prompt="test", temperature=3.5)

    def test_step_03_protocol_contract(self) -> None:
        namespace = {}
        exec(STEP_03_PROTOCOL_CODE, namespace)
        LLMClient = namespace["LLMClient"]
        Message = namespace["Message"]

        # Dummy implementation
        class DummyClient:
            def generate(self, messages: list[Message]) -> str:
                return "dummy reply"

        assert isinstance(DummyClient(), LLMClient)

    def test_step_04_fake_llm_contract(self) -> None:
        namespace = {}
        exec(STEP_04_FAKE_LLM_CODE, namespace)
        Message = namespace["Message"]
        FakeLLMClient = namespace["FakeLLMClient"]

        client = FakeLLMClient(
            responses=["First answer", "Second answer"],
            default_response="Default answer",
        )
        msg = Message(role="user", content="Question 1")

        r1 = client.generate([msg])
        assert r1 == "First answer"

        r2 = client.generate([msg])
        assert r2 == "Second answer"

        r3 = client.generate([msg])
        assert r3 == "Default answer"

        assert len(client.call_history) == 3

    def test_step_05_agent_contract(self) -> None:
        namespace = {}
        exec(STEP_05_AGENT_CODE, namespace)
        Agent = namespace["Agent"]
        AgentConfig = namespace["AgentConfig"]
        FakeLLMClient = namespace["FakeLLMClient"]

        config = AgentConfig(
            name="Assistant",
            system_prompt="You are a helpful assistant.",
        )
        fake_llm = FakeLLMClient(default_response="Hanoi is the capital of Vietnam.")
        agent = Agent(config=config, llm_client=fake_llm)

        reply = agent.run("What is the capital of Vietnam?")
        assert reply == "Hanoi is the capital of Vietnam."

        assert len(fake_llm.call_history) == 1
        history = fake_llm.call_history[0]
        assert len(history) == 2
        assert history[0].role == "system"
        assert history[0].content == "You are a helpful assistant."
        assert history[1].role == "user"
        assert history[1].content == "What is the capital of Vietnam?"

    def test_step_07_provider_adapter_contract(self) -> None:
        namespace = {}
        exec(STEP_07_FINAL_AGENT_CODE, namespace)
        OpenAICompatibleProvider = namespace["OpenAICompatibleProvider"]
        Message = namespace["Message"]

        provider = OpenAICompatibleProvider(api_key=None)
        with pytest.raises(ValueError, match="API key not found"):
            provider.generate([Message(role="user", content="hi")])


class TestGoldenTutorialBuilderLifecycle:
    """Validate end-to-end building and verification of Golden Tutorial in sandbox."""

    @pytest.mark.anyio
    async def test_full_golden_tutorial_build_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_host, tempfile.TemporaryDirectory() as tmp_ws:
            host_path = Path(tmp_host)
            ws_path = Path(tmp_ws) / ".tmp" / "code_video" / "video_02" / "agentic-studio"

            workspace = TutorialWorkspace(workspace_root=ws_path, host_repo_root=host_path)
            builder = GoldenTutorialBuilder(workspace=workspace)

            # Build all checkpoints
            records = await builder.build_all_checkpoints()

            # Verify all checkpoints exist
            expected_checkpoints = [
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
            for cp_id in expected_checkpoints:
                assert cp_id in records
                record = records[cp_id]
                assert record.checkpoint_id == cp_id
                assert len(record.file_hashes) > 0
                assert record.state_hash

            # Verify pytest inside sandbox
            passed, output = await builder.run_pytest_in_sandbox()
            assert passed == 2
            assert "2 passed" in output

            # Verify cold open demo execution
            demo_out = await builder.run_cold_open_demo()
            assert "User: Hello, what can you do?" in demo_out
            assert "Agent: Hello! I am your simple AI Agent running on Agentic Studio v0.1." in demo_out

            # Verify git tags in sandbox repository
            git_info = await builder.create_git_milestones()
            assert "video-02" in git_info["tags"]
            assert "v0.1" in git_info["tags"]
            assert git_info["commit_sha"]

            # Freeze preflight receipt
            receipt_dir = Path(tmp_host) / "preflight"
            receipt_file, output_file = builder.freeze_provider_preflight_receipt(receipt_dir)
            assert receipt_file.exists()
            assert output_file.exists()
            assert "CERTIFIED_FROZEN" in receipt_file.read_text(encoding="utf-8")

    @pytest.mark.anyio
    async def test_runtime_mismatch_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_host, tempfile.TemporaryDirectory() as tmp_ws:
            host_path = Path(tmp_host)
            ws_path = Path(tmp_ws) / ".tmp" / "code_video" / "video_02" / "agentic-studio"

            workspace = TutorialWorkspace(workspace_root=ws_path, host_repo_root=host_path)
            builder = GoldenTutorialBuilder(workspace=workspace)

            # Define a step expecting 3 passed when test only has 2
            mismatch_step = CheckpointDefinition(
                checkpoint_id="cp_test_mismatch",
                name="Mismatch Test",
                description="Test mismatch handling",
                agent_code=STEP_05_AGENT_CODE,
                test_code=STEP_06_TESTS_CODE,
                expected_pytest_passes=3,  # actual is 2
            )

            workspace.clean()
            builder.scaffolder.build_initial_scaffold()
            await builder._init_git_in_sandbox()

            with pytest.raises(ValidationError, match="SCRIPT_RUNTIME_MISMATCH"):
                await builder.build_checkpoint_step(mismatch_step)

    @pytest.mark.anyio
    async def test_secret_leak_prevention_in_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_host, tempfile.TemporaryDirectory() as tmp_ws:
            host_path = Path(tmp_host)
            ws_path = Path(tmp_ws) / ".tmp" / "code_video" / "video_02" / "agentic-studio"

            workspace = TutorialWorkspace(workspace_root=ws_path, host_repo_root=host_path)
            builder = GoldenTutorialBuilder(workspace=workspace)

            leaky_step = CheckpointDefinition(
                checkpoint_id="cp_leaky",
                name="Leaky Step",
                description="Contains leaked token",
                agent_code='PROVIDER_KEY = "sk-proj-1234567890abcdef1234567890abcdef12"\n',
                test_code=STEP_00_INIT_TEST_CODE,
            )

            workspace.clean()
            builder.scaffolder.build_initial_scaffold()
            await builder._init_git_in_sandbox()

            with pytest.raises(ValidationError, match="Secret scanner detected potential leak"):
                await builder.build_checkpoint_step(leaky_step)
