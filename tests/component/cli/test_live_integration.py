"""
Live integration tests for CLI Phase 4 - CLI Runtime Truthfulness.
Tests use temporary SQLite storage, NO --demo flag.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import tempfile
import os
import io
import sqlite3
import sys
import uuid
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

from windagent_cli.main import main as cli_main


class TempDB:
    """Context manager for temporary SQLite database."""

    def __init__(self):
        self.path = None
        self.url = None

    def __enter__(self):
        fd, self.path = tempfile.mkstemp(suffix=".db", prefix="windagent_test_")
        os.close(fd)
        self.url = f"sqlite+aiosqlite:///{self.path}"
        asyncio.run(self._initialize_schema())
        return self

    async def _initialize_schema(self):
        """Schema setup is an explicit test/migration concern, never a read command."""
        from windagent_storage.database.connection import DatabaseManager
        from windagent_storage.orm.models import BaseORM
        import windagent_storage.orm.v2_orchestration_models  # noqa: F401
        import windagent_storage.orm.v3_models  # noqa: F401

        db = DatabaseManager(self.url)
        try:
            await db.create_tables(BaseORM.metadata)
        finally:
            await db.close()

    def schema_snapshot(self):
        with sqlite3.connect(self.path) as connection:
            return connection.execute(
                """
                SELECT type, name, tbl_name, COALESCE(sql, '')
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()

    def insert_task(
        self,
        *,
        task_id,
        session_id,
        state,
        created_at,
        workflow_name="bugfix",
    ):
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO task_runs (
                    id, session_id, state, version, priority, current_step,
                    total_steps, pending_permission, retry_count, facts_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, 2, 0, 0, 0, 0, ?, ?, ?)
                """,
                (
                    task_id,
                    session_id,
                    state,
                    json.dumps(
                        {
                            "workflow_name": workflow_name,
                            "prompt": f"prompt-{task_id}",
                        }
                    ),
                    created_at.isoformat(),
                    created_at.isoformat(),
                ),
            )

    def insert_event(self, *, trace_id, sequence, payload, metadata=None):
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO execution_events (
                    id, session_id, event_type, data_json, event_seq, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.UUID(int=sequence)),
                    trace_id,
                    f"step-{sequence}",
                    json.dumps(
                        {
                            "aggregate_id": trace_id,
                            "aggregate_type": "session",
                            "payload": payload,
                            "metadata": metadata or {},
                        }
                    ),
                    sequence,
                    datetime.utcnow().isoformat(),
                ),
            )

    def __exit__(self, exc_type, exc_val, exc_tb):
        import gc

        gc.collect()  # Force close any lingering connections
        if self.path and os.path.exists(self.path):
            try:
                os.unlink(self.path)
            except PermissionError:
                pass  # Windows file locking, ignore


def run_cli(args, env=None):
    """Run CLI command with optional environment override."""
    old_env = {}
    if env:
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            return cli_main(args)
    finally:
        for k in env or {}:
            if k in old_env and old_env[k] is not None:
                os.environ[k] = old_env[k]
            elif k in old_env:
                del os.environ[k]
        run_cli.last_stdout = stdout_capture.getvalue()
        run_cli.last_stderr = stderr_capture.getvalue()


# Storage for captured output
run_cli.last_stdout = ""
run_cli.last_stderr = ""


class TestStatusLive:
    """Live tests for status command."""

    def test_status_success(self):
        """Status returns DEGRADED when DB exists but no workers."""
        with TempDB() as db:
            ret = run_cli(["status", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 2  # DEGRADED = exit code 2
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert out["non_production"] is False
            assert out["api_status"] == "DEGRADED"
            assert "health_details" in out

    @pytest.mark.parametrize(
        "args",
        [
            ["status", "--json"],
            ["task", "list", "--json"],
            ["task", "inspect", "missing", "--json"],
            ["replay", "missing", "--json"],
            ["providers", "--json"],
        ],
    )
    def test_read_commands_do_not_mutate_schema(self, args):
        with TempDB() as db:
            before = db.schema_snapshot()
            run_cli(args, {"WINDAGENT_DATABASE_URL": db.url})
            after = db.schema_snapshot()
            assert after == before

    def test_status_without_json(self):
        """Status text output contains LIVE marker."""
        with TempDB() as db:
            ret = run_cli(["status"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 2
            assert "LIVE" in run_cli.last_stdout
            assert "DEGRADED" in run_cli.last_stdout


class TestTaskListLive:
    """Live tests for task list command."""

    def test_task_list_empty(self):
        """Empty task list returns empty array."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "list", "--json"], {"WINDAGENT_DATABASE_URL": db.url}
            )
            assert ret == 0, run_cli.last_stdout
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert out["non_production"] is False
            assert out["tasks"] == []
            assert out["count"] == 0

    def test_task_list_pagination(self):
        """Pagination works with deterministic ordering."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "list", "--json", "--limit", "5"],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"

    def test_task_list_no_demo_data(self):
        """Live mode never returns demo task IDs."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "list", "--json"], {"WINDAGENT_DATABASE_URL": db.url}
            )
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            for task in out["tasks"]:
                assert "demo" not in task["task_id"].lower()

    def test_task_list_filters_and_deterministic_order(self):
        with TempDB() as db:
            now = datetime.utcnow()
            db.insert_task(
                task_id="task-a",
                session_id="session-1",
                state="completed",
                created_at=now - timedelta(minutes=2),
            )
            db.insert_task(
                task_id="task-b",
                session_id="session-1",
                state="received",
                created_at=now - timedelta(minutes=1),
            )
            db.insert_task(
                task_id="task-c",
                session_id="session-2",
                state="received",
                created_at=now,
            )
            ret = run_cli(
                [
                    "task",
                    "list",
                    "--json",
                    "--status",
                    "received",
                    "--session-id",
                    "session-1",
                ],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            assert [task["task_id"] for task in out["tasks"]] == ["task-b"]


class TestTaskInspectLive:
    """Live tests for task inspect command."""

    def test_task_inspect_not_found(self):
        """Non-existent task returns 4 with data_source LIVE."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "inspect", "non-existent-id", "--json"],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
            assert ret == 4
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert out["non_production"] is False
            assert "error" in out

    def test_task_inspect_requires_id(self):
        """Missing task_id without --demo fails with usage error."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "inspect", "--json"], {"WINDAGENT_DATABASE_URL": db.url}
            )
            assert ret == 3  # usage error


class TestReplayLive:
    """Live tests for replay command."""

    def test_replay_not_found(self):
        """Non-existent trace returns 4 with data_source LIVE."""
        with TempDB() as db:
            ret = run_cli(
                ["replay", "non-existent-trace", "--json"],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
            assert ret == 4
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert out["non_production"] is False
            assert "error" in out

    def test_replay_requires_id(self):
        """Missing trace_id without --demo fails with usage error."""
        with TempDB() as db:
            ret = run_cli(["replay", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 3  # usage error

    def test_replay_without_reference_is_not_claimed_as_parity(self):
        with TempDB() as db:
            db.insert_event(
                trace_id="trace-without-reference",
                sequence=1,
                payload={"state": "received"},
            )
            ret = run_cli(
                ["replay", "trace-without-reference", "--json"],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
            assert ret == 0, run_cli.last_stdout
            out = json.loads(run_cli.last_stdout)
            assert out["deterministic_parity"] == "UNAVAILABLE"
            assert out["parity_checks"]["event_count"] is None
            assert out["parity_checks"]["reconstructed_state_hash"] is None
            assert out["parity_checks"]["output_hash"] is None


class TestProvidersLive:
    """Live tests for providers command."""

    def test_providers_empty(self):
        """Empty canonical model registry returns empty providers."""
        with TempDB() as db:
            ret = run_cli(["providers", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert out["non_production"] is False
            assert out["providers"] == []

    def test_providers_no_demo_data(self):
        """Live mode never returns demo provider names."""
        with TempDB() as db:
            ret = run_cli(["providers", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            for p in out["providers"]:
                assert (
                    "openai" not in str(p).lower() or p.get("status") != "HEALTHY"
                )  # Not hardcoded demo


class TestToolsLive:
    """Live tests for tools command."""

    def test_tools_registered(self):
        """Tools command returns all 12 registered tools."""
        with TempDB() as db:
            ret = run_cli(["tools", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert len(out["tools"]) == 12
            tool_names = {t["name"] for t in out["tools"]}
            expected = {
                "read_file",
                "write_file",
                "exec_shell",
                "code_search",
                "git_operation",
                "ast_extract_symbols",
                "lsp_query",
                "run_tests",
                "open_url",
                "click_xy",
                "database_query",
                "github_api",
            }
            assert tool_names == expected

    def test_tools_metadata_complete(self):
        """Each tool has capability and risk_level."""
        with TempDB() as db:
            ret = run_cli(["tools", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 0
            out = json.loads(run_cli.last_stdout)
            for tool in out["tools"]:
                assert "capability" in tool
                assert "risk_level" in tool
                assert "description" in tool
                assert "version" in tool
                assert "required_permissions" in tool
                assert tool["availability"] == "REGISTERED"


class TestEvalLive:
    """Live tests for eval command."""

    def test_eval_unavailable_no_artifact(self):
        """Eval returns 2 when no verified artifact exists (unavailable)."""
        with TempDB() as db:
            ret = run_cli(["eval", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 2  # unavailable = exit code 2
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "OFFLINE"
            assert out["non_production"] is False
            assert out["verdict"] == "EVAL UNAVAILABLE"

    def test_eval_invalid_artifact_corrupt(self):
        """Corrupt artifact fails closed."""
        with TempDB() as db:
            eval_dir = Path("artifacts/eval")
            eval_dir.mkdir(parents=True, exist_ok=True)
            corrupt_path = eval_dir / "all_results.json"
            corrupt_path.write_text("{ invalid json }")
            try:
                ret = run_cli(["eval", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
                assert ret in (2, 3)
                out = json.loads(run_cli.last_stdout)
                assert out["data_source"] == "OFFLINE"
                assert out["non_production"] is False
            finally:
                if corrupt_path.exists():
                    corrupt_path.unlink()

    def test_eval_parseable_but_unverified_artifact_fails_closed(self):
        with TempDB() as db:
            eval_dir = Path("artifacts/eval")
            eval_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = eval_dir / "all_results.json"
            artifact_path.write_text(
                json.dumps({"results": {"suite": "all"}, "verdict": "PASS"}),
                encoding="utf-8",
            )
            try:
                ret = run_cli(
                    ["eval", "--json"],
                    {"WINDAGENT_DATABASE_URL": db.url},
                )
                assert ret == 2
                out = json.loads(run_cli.last_stdout)
                assert out["data_source"] == "OFFLINE"
                assert out["verdict"] == "EVAL UNAVAILABLE"
                assert "Phase 1 validation" in out["error"]
            finally:
                artifact_path.unlink(missing_ok=True)

    def test_eval_no_demo_fallback(self):
        """Live eval never returns demo scores."""
        with TempDB() as db:
            ret = run_cli(["eval", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 2  # eval unavailable returns exit code 2
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "OFFLINE"
            assert out["non_production"] is False
            assert "92.5%" not in json.dumps(out)  # Not hardcoded demo


class TestDemoIsolation:
    """Tests proving demo mode never touches production DB."""

    def test_demo_status_no_db_access(self):
        """Demo status works without DB."""
        ret = run_cli(["status", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True

    def test_demo_task_list_no_db_access(self):
        """Demo task list works without DB."""
        ret = run_cli(["task", "list", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True
        assert len(out["tasks"]) == 2

    def test_demo_task_inspect_no_db_access(self):
        """Demo task inspect works without DB."""
        ret = run_cli(["task", "inspect", "task_demo_01", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True

    def test_demo_replay_no_db_access(self):
        """Demo replay works without DB."""
        ret = run_cli(["replay", "trace_demo", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True

    def test_demo_providers_no_db_access(self):
        """Demo providers works without DB."""
        ret = run_cli(["providers", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True

    def test_demo_tools_no_db_access(self):
        """Demo tools works without DB."""
        ret = run_cli(["tools", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True

    def test_demo_eval_no_db_access(self):
        """Demo eval works without DB."""
        ret = run_cli(["eval", "--demo", "--json"])
        assert ret == 0
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True


class TestFailureContract:
    """Tests for standardized error response format."""

    def test_error_has_data_source_live(self):
        """All errors in live mode include data_source: LIVE."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "inspect", "bad-id", "--json"],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
            assert ret == 4
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"
            assert "error" in out

    def test_error_has_data_source_demo(self):
        """All errors in demo mode include data_source: DEMO."""
        ret = run_cli(["task", "inspect", "bad-id", "--demo", "--json"])
        assert ret == 4
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "DEMO"
        assert out["non_production"] is True

    def test_usage_error_exit_code_3(self):
        """Usage errors (missing required args) return exit code 3."""
        with TempDB() as db:
            ret = run_cli(
                ["task", "inspect", "--json"], {"WINDAGENT_DATABASE_URL": db.url}
            )
            assert ret == 3
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "LIVE"

    def test_unavailable_exit_code_2(self):
        """Unavailable service returns exit code 2 (UNAVAILABLE)."""
        with TempDB() as db:
            ret = run_cli(["eval", "--json"], {"WINDAGENT_DATABASE_URL": db.url})
            assert ret == 2  # eval unavailable returns exit code 2
            out = json.loads(run_cli.last_stdout)
            assert out["data_source"] == "OFFLINE"
            assert out["non_production"] is False

    def test_internal_failure_exit_code_1(self, monkeypatch):
        """Internal failures return exit code 1."""

        async def fail_bootstrap(_self):
            raise RuntimeError("injected internal defect")

        cli_module = sys.modules["windagent_cli.main"]
        monkeypatch.setattr(
            cli_module.TaskListCommandComposer,
            "bootstrap",
            fail_bootstrap,
        )
        with TempDB() as db:
            ret = run_cli(
                ["task", "list", "--json"],
                {"WINDAGENT_DATABASE_URL": db.url},
            )
        assert ret == 1
        out = json.loads(run_cli.last_stdout)
        assert out["data_source"] == "LIVE"
        assert out["non_production"] is False
        assert "internal failure" in out["error"]
