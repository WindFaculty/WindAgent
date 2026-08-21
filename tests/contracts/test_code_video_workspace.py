"""
Contract and Unit Tests for Isolated Tutorial Workspace (Phase 2).

Covers all Phase 2 gate requirements from ban_ke_hoach_video_02.md:
- Sandbox isolation strictly outside WindAgent source tree
- PathSandbox boundary enforcement and traversal rejection
- Deterministic tutorial repository scaffolding (agentic-studio layout)
- Incremental checkpoint manager (create, list, restore, verify SHA256)
- Preflight security scanner (zero secrets, API key leak detection, .env protection)
"""

from __future__ import annotations

from pathlib import Path
import pytest

from windagent_core.errors.exceptions import PermissionDeniedError, ValidationError
from windagent_tools.code_video.workspace.checkpoints import CheckpointManager
from windagent_tools.code_video.workspace.repository_builder import (
    TutorialRepositoryBuilder,
)
from windagent_tools.code_video.workspace.sandbox import TutorialWorkspace
from windagent_tools.code_video.workspace.security_scanner import WorkspaceSecretScanner


@pytest.fixture
def temp_workspace(tmp_path: Path) -> TutorialWorkspace:
    """Fixture providing an isolated tutorial workspace in a clean temporary directory."""
    ws_dir = tmp_path / ".tmp" / "code_video" / "video_02" / "agentic-studio"
    ws = TutorialWorkspace(workspace_root=ws_dir, host_repo_root=tmp_path / "host_repo")
    ws.create()
    return ws


class TestTutorialWorkspace:
    """Tests for TutorialWorkspace sandbox boundaries and operations."""

    def test_workspace_creation_and_cleaning(self, temp_workspace: TutorialWorkspace) -> None:
        assert temp_workspace.exists()
        temp_workspace.write_file("test.txt", "hello world")
        assert temp_workspace.file_exists("test.txt")
        assert temp_workspace.read_file("test.txt") == "hello world"

        temp_workspace.clean()
        assert not temp_workspace.file_exists("test.txt")

    def test_isolation_boundary_rejection(self, tmp_path: Path) -> None:
        host_root = tmp_path / "host_repo"
        host_root.mkdir(parents=True, exist_ok=True)
        host_src = host_root / "src"
        host_src.mkdir(parents=True, exist_ok=True)

        # Attempt to create tutorial workspace inside host_repo/src/sub
        nested_inside_host = host_src / "agentic-studio"
        with pytest.raises(PermissionDeniedError, match="cannot be placed inside protected host directory"):
            TutorialWorkspace(workspace_root=nested_inside_host, host_repo_root=host_root)

    def test_path_traversal_rejection(self, temp_workspace: TutorialWorkspace) -> None:
        # Relative traversal outside workspace
        with pytest.raises(PermissionDeniedError):
            temp_workspace.resolve_safe_path("../outside.txt")

        with pytest.raises(PermissionDeniedError):
            temp_workspace.write_file("../../evil.py", "malicious_code")

    @pytest.mark.asyncio
    async def test_safe_shell_execution(self, temp_workspace: TutorialWorkspace) -> None:
        temp_workspace.write_file("hello.py", "print('hello from sandbox')\n")
        exit_code, stdout, stderr = await temp_workspace.run_command("python hello.py")
        assert exit_code == 0
        assert "hello from sandbox" in stdout


class TestTutorialRepositoryBuilder:
    """Tests for TutorialRepositoryBuilder scaffold generation."""

    def test_scaffold_creation_and_validation(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        for req_file in TutorialRepositoryBuilder.REQUIRED_TUTORIAL_FILES:
            assert temp_workspace.file_exists(req_file)

        # Validate complete scaffold without errors
        builder.validate_scaffold()

    def test_validate_scaffold_missing_file(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        # Delete pyproject.toml
        pyproject = temp_workspace.resolve_safe_path("pyproject.toml")
        pyproject.unlink()

        with pytest.raises(ValidationError, match="missing required files"):
            builder.validate_scaffold()

    def test_validate_gitignore_contains_env(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        # Overwrite .gitignore without .env
        temp_workspace.write_file(".gitignore", "__pycache__/\n")
        with pytest.raises(ValidationError, match=".gitignore must explicitly contain '.env'"):
            builder.validate_scaffold()

    def test_validate_env_example_has_no_secrets(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        # Overwrite .env.example with actual sk- token
        temp_workspace.write_file(".env.example", "PROVIDER_API_KEY=sk-1234567890abcdef1234567890\n")
        with pytest.raises(ValidationError, match="found potential secret token"):
            builder.validate_scaffold()


class TestCheckpointManager:
    """Tests for incremental snapshot capture, restoration, and verification."""

    def test_checkpoint_capture_and_restore(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        mgr = CheckpointManager(temp_workspace)
        rec1 = mgr.create_checkpoint("cp_01_scaffold", "Initial Scaffold", "Complete base repo")

        assert rec1.checkpoint_id == "cp_01_scaffold"
        assert len(rec1.file_hashes) >= 8
        assert rec1.state_hash is not None

        # Verify checkpoint matches current state
        is_match, discrepancies = mgr.verify_checkpoint("cp_01_scaffold")
        assert is_match is True
        assert len(discrepancies) == 0

        # Modify a file
        temp_workspace.write_file("src/agent.py", "# Modified agent code\nclass Message:\n    pass\n")
        is_match_after_mod, disc_after_mod = mgr.verify_checkpoint("cp_01_scaffold")
        assert is_match_after_mod is False
        assert any("Hash mismatch in 'src/agent.py'" in d for d in disc_after_mod)

        # Restore checkpoint and verify state matches original
        mgr.restore_checkpoint("cp_01_scaffold")
        is_match_restored, disc_restored = mgr.verify_checkpoint("cp_01_scaffold")
        assert is_match_restored is True
        assert len(disc_restored) == 0
        assert temp_workspace.read_file("src/agent.py") == '"""Agent implementation."""\n'

    def test_list_and_get_checkpoints(self, temp_workspace: TutorialWorkspace) -> None:
        mgr = CheckpointManager(temp_workspace)
        temp_workspace.write_file("a.txt", "1")
        mgr.create_checkpoint("cp_01", "CP 1")

        temp_workspace.write_file("b.txt", "2")
        mgr.create_checkpoint("cp_02", "CP 2")

        checkpoints = mgr.list_checkpoints()
        assert len(checkpoints) == 2
        assert [c.checkpoint_id for c in checkpoints] == ["cp_01", "cp_02"]

        retrieved = mgr.get_checkpoint("cp_01")
        assert retrieved is not None
        assert retrieved.name == "CP 1"


class TestWorkspaceSecretScanner:
    """Tests for secret detection in files and environment configurations."""

    def test_clean_workspace_passes(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        scanner = WorkspaceSecretScanner(temp_workspace)
        report = scanner.scan_workspace()
        assert report.is_clean is True
        assert len(report.violations) == 0

        # enforce should not raise
        scanner.enforce_clean_workspace()

    def test_detect_openai_secret_leak(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        # Leak OpenAI key into src/agent.py
        temp_workspace.write_file("src/agent.py", 'API_KEY = "sk-abcdef1234567890abcdef123456"\n')

        scanner = WorkspaceSecretScanner(temp_workspace)
        report = scanner.scan_workspace()
        assert report.is_clean is False
        assert any(v.pattern_type == "OPENAI_API_KEY" for v in report.violations)

        with pytest.raises(PermissionDeniedError, match="Workspace security preflight failed"):
            scanner.enforce_clean_workspace()

    def test_detect_google_api_key_leak(self, temp_workspace: TutorialWorkspace) -> None:
        builder = TutorialRepositoryBuilder(temp_workspace)
        builder.build_initial_scaffold()

        temp_workspace.write_file(".env", "GOOGLE_KEY=AIzaSyA1234567890abcdef1234567890\n")

        scanner = WorkspaceSecretScanner(temp_workspace)
        report = scanner.scan_workspace()
        assert report.is_clean is False
        assert any(v.pattern_type == "GOOGLE_API_KEY" for v in report.violations)

    def test_detect_bearer_and_groq_keys(self, temp_workspace: TutorialWorkspace) -> None:
        scanner = WorkspaceSecretScanner(temp_workspace)
        violations = scanner.scan_text("auth: Bearer my_super_secret_jwt_token_123456")
        assert len(violations) >= 1
        assert any(v.pattern_type == "BEARER_TOKEN" for v in violations)

        violations_groq = scanner.scan_text("key = 'gsk_12345678901234567890'")
        assert len(violations_groq) >= 1
        assert any(v.pattern_type == "GROQ_API_KEY" for v in violations_groq)
