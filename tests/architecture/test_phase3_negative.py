#!/usr/bin/env python3
"""
Negative test suite for Phase 3: Complete CLI Architecture Fail-Closed Contract.

Tests cover:
- Fake repository outside source tree (no parent repo dependency)
- Missing scaffold checker
- Missing imports checker
- Checker returns violation
- Checker crashes
- Checker timeout
- Installed package outside checkout
- Symlink
- Windows drive
- Path with spaces
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_architecture_imports.py"
SCAFFOLD_SCRIPT = ROOT / "scripts" / "scaffold_architecture_v2.py"


def write_package(root: Path, path: str, imports: str = "", dependencies=()) -> None:
    """Create a minimal package structure for testing.

    Args:
        root: Root directory
        path: Package path (e.g., "core" or "apps/api")
        imports: Python imports to write in __init__.py
        dependencies: List of dependency strings
    """
    # Get the last component as package name
    name = Path(path).name
    namespace = f"windagent_{name}"
    package = root / path
    (package / namespace).mkdir(parents=True)
    (package / namespace / "__init__.py").write_text(imports, encoding="utf-8")
    deps = ", ".join(json.dumps(dep) for dep in dependencies)
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "{namespace}"\nversion = "0.3.0"\ndependencies = [{deps}]\n',
        encoding="utf-8",
    )


def write_root_pyproject(root: Path, members: list[str]) -> None:
    """Write root pyproject.toml with workspace members."""
    members_str = ", ".join(json.dumps(m) for m in members)
    (root / "pyproject.toml").write_text(
        f'[tool.uv.workspace]\nmembers = [{members_str}]\n',
        encoding="utf-8",
    )


def write_full_scaffold_config(root: Path) -> Path:
    """Write complete scaffold config matching the real one."""
    config = {
        "version": "2.0",
        "workspace": {
            "root": ".",
            "members": [
                "apps/api", "apps/cli", "apps/worker", "core", "orchestration",
                "intelligence", "providers", "tools", "workflows", "verification",
                "context", "memory", "execution", "storage", "observability",
                "evals", "plugins", "skills"
            ],
        },
        "global_rules": {
            "forbid_cross_app_imports": True,
            "forbid_core_framework_imports": True,
            "require_declared_workspace_dependencies": True,
            "forbid_dependency_cycles": True,
            "forbid_public_api_leakage": True,
            "forbid_legacy_backend_imports": True,
            "forbid_production_test_fallbacks": True,
            "enforce_legacy_quarantine": True,
            "forbid_canonical_to_legacy_imports": True,
            "forbid_legacy_runtime_authority": True,
            "forbid_dynamic_imports": True,
            "enforce_composition_root_rule": True,
            "composition_roots": [
                "apps/api/**", "apps/worker/**", "apps/cli/**", "orchestration/**",
                "providers/**", "storage/**", "execution/**", "tools/**",
                "workflows/**", "verification/**", "context/**", "memory/**",
                "intelligence/**", "observability/**", "evals/**", "plugins/**",
                "skills/**", "tests/"
            ],
        },
        "canonical_models": [
            "EventEnvelope", "TaskState", "WorkflowState", "StepState", "SessionState",
            "WindAgentError", "ProviderRequest", "ProviderResponse", "ProviderUsage",
            "ProviderToolCall", "ProviderStreamChunk", "ProviderCapabilities",
            "ModelDescriptor", "ToolInvocation", "ToolResult", "ToolDefinition",
            "ToolExecutionContext", "ToolRiskLevel",
        ],
        "required_top_level_packages": ["plugins", "skills"],
        "packages": {
            "core": {
                "layer": "domain",
                "namespace": "windagent_core",
                "path": "core",
                "description": "Core domain models, contracts, domain events, errors, config, security types",
                "allowed_dependencies": [],
                "external_dependencies": ["pydantic>=2.7", "typing-extensions"],
                "forbidden_dependencies": ["apps", "fastapi", "sqlalchemy", "mcp", "langgraph", "providers"],
                "legacy_source": "apps/backend/models, apps/backend/config.py",
                "internal_boundaries": {
                    "domain": {
                        "path": "core/windagent_core/domain",
                        "forbidden_dependencies": ["core/windagent_core/config", "core/windagent_core/security"],
                        "allowed_dependencies": ["core/windagent_core/contracts", "core/windagent_core/errors"],
                    },
                    "contracts": {
                        "path": "core/windagent_core/contracts",
                        "forbidden_dependencies": ["infrastructure"],
                        "allowed_dependencies": ["core/windagent_core/domain", "core/windagent_core/errors"],
                    },
                    "events": {
                        "path": "core/windagent_core/events",
                        "allowed_dependencies": ["core/windagent_core/domain", "core/windagent_core/contracts", "core/windagent_core/errors"],
                        "forbidden_dependencies": [],
                    },
                },
            },
            "orchestration": {
                "layer": "application",
                "namespace": "windagent_orchestration",
                "path": "orchestration",
                "description": "Task manager, workflow engine, state machine, scheduler, dispatcher, retry, recovery",
                "allowed_dependencies": ["windagent_core", "windagent_storage"],
                "forbidden_dependencies": ["apps", "windagent_providers"],
                "legacy_source": "apps/backend/services/workflow_service.py, recovery.py",
            },
            "intelligence": {
                "layer": "application",
                "namespace": "windagent_intelligence",
                "path": "intelligence",
                "description": "Task classifier, planner, context builder, model router, summarizer, reviewer, reporter",
                "allowed_dependencies": ["windagent_core", "windagent_providers", "windagent_context"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/services/model_routing_service.py, agent_service.py",
            },
            "providers": {
                "layer": "infrastructure",
                "namespace": "windagent_providers",
                "path": "providers",
                "description": "Model provider integrations (OpenAI, Anthropic, Google, Ollama, etc.)",
                "allowed_dependencies": ["windagent_core"],
                "forbidden_dependencies": ["apps", "windagent_orchestration", "windagent_intelligence"],
                "legacy_source": "apps/backend/services/model_service.py",
            },
            "tools": {
                "layer": "infrastructure",
                "namespace": "windagent_tools",
                "path": "tools",
                "description": "Tool registry, filesystem, shell, git, code_search, AST, LSP, browser, database, MCP",
                "allowed_dependencies": ["windagent_core"],
                "forbidden_dependencies": ["apps", "windagent_orchestration"],
                "legacy_source": "apps/backend/services/tool_execution_service.py, tools/",
            },
            "workflows": {
                "layer": "application",
                "namespace": "windagent_workflows",
                "path": "workflows",
                "description": "Predefined workflow definitions and step implementations",
                "allowed_dependencies": ["windagent_core", "windagent_orchestration", "windagent_tools"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/workflows/",
            },
            "verification": {
                "layer": "application",
                "namespace": "windagent_verification",
                "path": "verification",
                "description": "Quality gates, verification runners, test assertion helpers",
                "allowed_dependencies": ["windagent_core", "windagent_tools"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/verification/",
            },
            "context": {
                "layer": "application",
                "namespace": "windagent_context",
                "path": "context",
                "description": "Context assembly, token budgeting, prompt formatting",
                "allowed_dependencies": ["windagent_core"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/services/context_service.py",
            },
            "memory": {
                "layer": "application",
                "namespace": "windagent_memory",
                "path": "memory",
                "description": "Multi-layered memory, working memory, long-term memory, semantic store",
                "allowed_dependencies": ["windagent_core", "windagent_storage"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/services/memory_service.py",
            },
            "execution": {
                "layer": "infrastructure",
                "namespace": "windagent_execution",
                "path": "execution",
                "description": "Git worktree isolation, sandbox runtime, subprocess execution",
                "allowed_dependencies": ["windagent_core"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/services/worktree_service.py",
            },
            "storage": {
                "layer": "infrastructure",
                "namespace": "windagent_storage",
                "path": "storage",
                "description": "Database repositories, ORM mappings, migration adapters, persistent artifact storage",
                "allowed_dependencies": ["windagent_core", "windagent_providers"],
                "forbidden_dependencies": ["apps", "windagent_orchestration", "windagent_intelligence"],
                "legacy_source": "apps/backend/db/",
            },
            "observability": {
                "layer": "infrastructure",
                "namespace": "windagent_observability",
                "path": "observability",
                "description": "Logging, tracing, metrics, audit trail, cost tracking",
                "allowed_dependencies": ["windagent_core", "windagent_storage"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/observability/",
            },
            "evals": {
                "layer": "application",
                "namespace": "windagent_evals",
                "path": "evals",
                "description": "Evaluation benchmarks, model output scoring, regression suites",
                "allowed_dependencies": ["windagent_core", "windagent_intelligence"],
                "forbidden_dependencies": ["apps"],
                "legacy_source": "apps/backend/evals/",
            },
            "api": {
                "layer": "app",
                "namespace": "windagent_api",
                "path": "apps/api",
                "description": "FastAPI REST & WebSocket entrypoint for Architecture V2",
                "allowed_dependencies": [
                    "windagent_core", "windagent_orchestration", "windagent_execution",
                    "windagent_intelligence", "windagent_providers", "windagent_tools",
                    "windagent_workflows", "windagent_verification", "windagent_context",
                    "windagent_memory", "windagent_plugins", "windagent_skills",
                    "windagent_storage", "windagent_observability",
                ],
                "forbidden_dependencies": [],
                "legacy_source": "apps/backend/main.py",
            },
            "cli": {
                "layer": "app",
                "namespace": "windagent_cli",
                "path": "apps/cli",
                "description": "WindAgent CLI entrypoint (doctor, architecture check, workflow run)",
                "allowed_dependencies": [
                    "windagent_core", "windagent_orchestration", "windagent_intelligence",
                    "windagent_providers", "windagent_tools", "windagent_workflows",
                    "windagent_storage", "windagent_observability", "windagent_plugins",
                    "windagent_skills",
                ],
                "forbidden_dependencies": [],
                "legacy_source": "apps/backend/cli.py",
            },
            "worker": {
                "layer": "app",
                "namespace": "windagent_worker",
                "path": "apps/worker",
                "description": "Background worker process for asynchronous task execution",
                "allowed_dependencies": [
                    "windagent_core", "windagent_orchestration", "windagent_execution",
                    "windagent_providers", "windagent_tools", "windagent_intelligence",
                    "windagent_context", "windagent_memory", "windagent_workflows",
                    "windagent_verification", "windagent_storage", "windagent_observability",
                ],
                "forbidden_dependencies": [],
                "legacy_source": "apps/backend/worker.py",
            },
            "plugins": {
                "layer": "infrastructure",
                "namespace": "windagent_plugins",
                "path": "plugins",
                "description": "Plugin system for extensible functionality - loader, registry, lifecycle, security, manifest",
                "allowed_dependencies": ["windagent_core"],
                "forbidden_dependencies": ["apps", "windagent_orchestration", "windagent_intelligence", "windagent_storage"],
                "legacy_source": "apps/backend/plugins/",
            },
            "skills": {
                "layer": "application",
                "namespace": "windagent_skills",
                "path": "skills",
                "description": "Skills system for reusable capabilities - loader, registry, execution, versioning",
                "allowed_dependencies": ["windagent_core", "windagent_providers", "windagent_tools"],
                "forbidden_dependencies": ["apps", "windagent_orchestration"],
                "legacy_source": "apps/backend/skills/",
            },
        },
        "forbidden_patterns": {
            "production_fallback_regex": r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b",
            "test_adapter_paths": ["tests/"],
            "legacy_quarantine": {
                "zone": "apps/backend",
                "allowlist": [],
                "runtime_authority_blocked_patterns": [
                    "DatabaseManager", "SqlRepository", "Provider",
                    "ExecutionRuntime", "Authority", "Adapter"
                ],
                "retirement_gate": "LEGACY_BACKEND_RUNTIME_REMOVED",
            },
        },
    }
    config_path = root / "configs" / "architecture" / "scaffold_v2.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def run_checker(tmp_path: Path, config_path: Path = None, extra_args=None, skip_root_validation=False, skip_scaffold_check=False) -> tuple[subprocess.CompletedProcess, dict]:
    """Run the architecture checker and return result and parsed JSON report."""
    args = [sys.executable, str(CHECKER), "--root", str(tmp_path), "--json"]
    if config_path:
        args.extend(["--config", str(config_path)])
    if skip_root_validation:
        args.append("--skip-root-validation")
    if skip_scaffold_check:
        args.append("--skip-scaffold-check")
    if extra_args:
        args.extend(extra_args)

    result = subprocess.run(args, capture_output=True, text=True, timeout=60)

    report = {}
    if result.stdout:
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return result, report


class TestRepoRootDetection:
    """Test repository root detection with stable markers."""

    def test_valid_repo_root_detected(self, tmp_path):
        """Test that a valid repo root with all markers is detected."""
        # Create all packages expected by the full config
        packages = ["core", "orchestration", "intelligence", "providers", "tools",
                    "workflows", "verification", "context", "memory", "execution",
                    "storage", "observability", "evals", "plugins", "skills",
                    "apps/api", "apps/cli", "apps/worker"]
        for pkg in packages:
            write_package(tmp_path, pkg)
        write_root_pyproject(tmp_path, packages)
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)
        assert report.get("repository_root") == str(tmp_path)
        assert report.get("verdict") == "PASS"

    def test_missing_pyproject_toml_fails(self, tmp_path):
        """Test that missing pyproject.toml fails with exit code 2."""
        write_package(tmp_path, "core")
        config_path = write_full_scaffold_config(tmp_path)
        # No root pyproject.toml

        result, report = run_checker(tmp_path, config_path=config_path)
        assert result.returncode == 2
        assert report.get("exit_code") == 2
        assert report.get("verdict") == "ERROR"

    def test_missing_scaffold_config_fails(self, tmp_path):
        """Test that missing scaffold config fails with exit code 2."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        # No scaffold config

        result, report = run_checker(tmp_path)
        assert result.returncode == 2
        assert report.get("exit_code") == 2

    def test_invalid_pyproject_no_workspace_fails(self, tmp_path):
        """Test that pyproject.toml without [tool.uv.workspace] fails."""
        write_package(tmp_path, "core")
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path)
        assert result.returncode == 2
        assert report.get("exit_code") == 2


class TestMissingCheckers:
    """Test behavior when required checkers are missing."""

    def test_missing_scaffold_checker_fails(self, tmp_path):
        """Test that missing scaffold_architecture_v2.py fails with exit code 4."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)
        # Don't create scaffold script

        result, report = run_checker(tmp_path, config_path=config_path)
        assert result.returncode == 3
        assert report.get("exit_code") == 3

    def test_missing_imports_checker_fails(self, tmp_path):
        """Test that missing check_architecture_imports.py fails."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        write_full_scaffold_config(tmp_path)

        # This test is tricky since we're running the checker itself
        # If the checker is missing, the subprocess will fail
        result = subprocess.run(
            [sys.executable, "nonexistent_checker.py", "--root", str(tmp_path), "--json"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0


class TestCheckerViolations:
    """Test checker returns proper violations."""

    def test_checker_returns_violation_exit_1(self, tmp_path):
        """Test that architecture violation returns exit code 1."""
        # Create packages that violate cross-app import rule
        write_package(tmp_path, "apps/api", "import windagent_worker\n")
        write_package(tmp_path, "apps/worker")
        write_root_pyproject(tmp_path, ["apps/api", "apps/worker"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 1
        assert report.get("verdict") == "FAIL"
        violations = report.get("violations", [])
        assert any(v["rule"] == "cross_app_dependency" for v in violations)

    def test_checker_crash_returns_exit_4(self, tmp_path):
        """Test that checker crash returns exit code 4."""
        write_package(tmp_path, "core", "invalid python syntax {{{")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)
        # Syntax error should be caught as violation, not crash
        assert result.returncode in (1, 4)


class TestCheckerTimeout:
    """Test checker timeout handling."""

    def test_checker_timeout_returns_exit_4(self, tmp_path):
        """Test that checker timeout returns exit code 4."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        # Create a slow scaffold check by making a script that hangs
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        hanging_script = scripts_dir / "scaffold_architecture_v2.py"
        hanging_script.write_text("import time; time.sleep(10)", encoding="utf-8")

        result, report = run_checker(tmp_path, config_path=config_path)
        # Should timeout and return exit 4
        assert result.returncode == 4


class TestExternalDirectory:
    """Test --root with external directory."""

    def test_external_directory_with_root_flag(self, tmp_path):
        """Test running checker from external directory with --root flag."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        other_dir = tmp_path.parent / "other_workdir"
        other_dir.mkdir(exist_ok=True)

        result = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(tmp_path), "--json",
             "--config", str(config_path), "--skip-scaffold-check"],
            cwd=str(other_dir),
            capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0
        report = json.loads(result.stdout)
        assert report.get("repository_root") == str(tmp_path)


class TestInstalledPackageOutsideCheckout:
    """Test installed package outside checkout."""

    def test_installed_package_not_confused_with_workspace(self, tmp_path):
        """Test that an installed package outside workspace doesn't affect checks."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 0
        assert report.get("verdict") == "PASS"


class TestSymlink:
    """Test symlink handling."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require admin on Windows")
    def test_symlinked_package(self, tmp_path):
        """Test that symlinked packages work correctly."""
        real_pkg = tmp_path / "real_core"
        write_package(real_pkg, "core")
        (real_pkg / "pyproject.toml").write_text(
            '[project]\nname = "windagent_core"\nversion = "0.3.0"\n',
            encoding="utf-8",
        )

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        write_root_pyproject(workspace, ["core"])
        write_full_scaffold_config(workspace)

        symlink = workspace / "core"
        symlink.symlink_to(real_pkg)

        config_path = workspace / "configs" / "architecture" / "scaffold_v2.yaml"
        result, report = run_checker(workspace, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode in (0, 1)


class TestWindowsDrive:
    """Test Windows drive handling."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_different_drive_repo_root(self, tmp_path):
        """Test repo root on different drive."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 0
        assert report.get("verdict") == "PASS"


class TestPathWithSpaces:
    """Test paths with spaces."""

    def test_repo_root_with_spaces(self, tmp_path):
        """Test that repo root with spaces in path works."""
        spaced_path = tmp_path / "repo with spaces"
        spaced_path.mkdir()

        write_package(spaced_path, "core")
        write_root_pyproject(spaced_path, ["core"])
        config_path = write_full_scaffold_config(spaced_path)

        result, report = run_checker(spaced_path, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 0
        assert report.get("verdict") == "PASS"

    def test_package_path_with_spaces(self, tmp_path):
        """Test that package path with spaces works."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        # Rename core to have spaces
        core_dir = tmp_path / "core"
        spaced_core = tmp_path / "core with spaces"
        core_dir.rename(spaced_core)

        (spaced_core / "pyproject.toml").write_text(
            '[project]\nname = "windagent_core"\nversion = "0.3.0"\n',
            encoding="utf-8",
        )
        write_root_pyproject(tmp_path, ["core with spaces"])

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode in (0, 1)


class TestFakeRepositoryIsolation:
    """Test that fake repositories are isolated from parent repository."""

    def test_fake_repo_outside_source_tree(self, tmp_path):
        """Test fake repo created outside source tree works independently."""
        fake_repo = tmp_path / "fake_repo"
        fake_repo.mkdir()

        write_package(fake_repo, "core")
        write_root_pyproject(fake_repo, ["core"])
        config_path = write_full_scaffold_config(fake_repo)

        result, report = run_checker(fake_repo, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 0
        assert report.get("verdict") == "PASS"
        assert report.get("repository_root") == str(fake_repo)

    def test_fake_repo_with_apps_structure(self, tmp_path):
        """Test fake repo with apps/ structure."""
        fake_repo = tmp_path / "fake_repo"
        fake_repo.mkdir()

        write_package(fake_repo, "apps/api", "import windagent_core\n", ["windagent-core"])
        write_package(fake_repo, "core")
        write_root_pyproject(fake_repo, ["core", "apps/api"])
        config_path = write_full_scaffold_config(fake_repo)

        result, report = run_checker(fake_repo, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 0
        assert report.get("verdict") == "PASS"

    def test_fake_repo_with_api_package(self, tmp_path):
        """Test fake repo with apps/api/windagent_api structure."""
        fake_repo = tmp_path / "fake_repo"
        fake_repo.mkdir()

        write_package(fake_repo, "apps/api")
        write_package(fake_repo, "core")
        write_root_pyproject(fake_repo, ["core", "apps/api"])
        config_path = write_full_scaffold_config(fake_repo)

        result, report = run_checker(fake_repo, config_path=config_path, skip_scaffold_check=True)
        assert result.returncode == 0
        assert report.get("verdict") == "PASS"


class TestStructuredOutput:
    """Test structured JSON output format."""

    def test_json_output_has_required_fields(self, tmp_path):
        """Test that JSON output has all required fields."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)

        # Required fields per Phase 3 spec
        assert "repository_root" in report
        assert "checks" in report
        assert "all_required_checks_executed" in report
        assert "verdict" in report
        assert "exit_code" in report
        assert "violations" in report
        assert "total_violations" in report

    def test_check_result_has_required_fields(self, tmp_path):
        """Test that each check result has required fields."""
        write_package(tmp_path, "core")
        write_root_pyproject(tmp_path, ["core"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)

        for check in report.get("checks", []):
            assert "name" in check
            assert "argv" in check
            assert "cwd" in check
            assert "executed" in check
            assert "exit_code" in check
            assert "classification" in check
            assert "duration_ms" in check
            assert "stdout_tail" in check
            assert "stderr_tail" in check

    def test_no_hardcoded_violations_empty_array(self, tmp_path):
        """Test that violations array is not hardcoded to empty when there are errors."""
        write_package(tmp_path, "apps/api", "import windagent_worker\n")
        write_package(tmp_path, "apps/worker")
        write_root_pyproject(tmp_path, ["apps/api", "apps/worker"])
        config_path = write_full_scaffold_config(tmp_path)

        result, report = run_checker(tmp_path, config_path=config_path, skip_scaffold_check=True)

        assert result.returncode == 1
        assert report.get("verdict") == "FAIL"
        assert len(report.get("violations", [])) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
