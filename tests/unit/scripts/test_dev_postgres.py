"""Unit tests for scripts/dev_postgres.py pure helpers (no Docker required)."""
from __future__ import annotations

from pathlib import Path

import pytest

import dev_postgres


class TestEffectiveHostPort:
    def test_explicit_override_wins(self):
        assert dev_postgres.effective_host_port(55444, {"WINDAGENT_POSTGRES_PORT": "9"}) == 55444

    def test_env_var_used_when_no_override(self):
        assert dev_postgres.effective_host_port(None, {"WINDAGENT_POSTGRES_PORT": "55433"}) == 55433

    def test_default_when_env_missing(self):
        assert dev_postgres.effective_host_port(None, {}) == 55432

    def test_default_when_env_blank(self):
        assert dev_postgres.effective_host_port(None, {"WINDAGENT_POSTGRES_PORT": "  "}) == 55432

    def test_invalid_env_fails_closed(self):
        with pytest.raises(SystemExit, match="invalid WINDAGENT_POSTGRES_PORT"):
            dev_postgres.effective_host_port(None, {"WINDAGENT_POSTGRES_PORT": "abc"})

    def test_dotenv_used_when_shell_env_missing(self):
        # .env route must reach the wrapper too (compose reads it as well).
        assert (
            dev_postgres.effective_host_port(None, {}, {"WINDAGENT_POSTGRES_PORT": "55435"})
            == 55435
        )

    def test_process_env_beats_dotenv(self):
        assert (
            dev_postgres.effective_host_port(
                None,
                {"WINDAGENT_POSTGRES_PORT": "55433"},
                {"WINDAGENT_POSTGRES_PORT": "55435"},
            )
            == 55433
        )


class TestLoadDotEnv:
    def test_missing_file_yields_empty(self, tmp_path):
        assert dev_postgres.load_dot_env(tmp_path / "nope.env") == {}

    def test_parses_keys_strips_quotes_and_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# comment line\n"
            "\n"
            "WINDAGENT_POSTGRES_PORT=55435\n"
            'QUOTED="55436"\n'
            "SINGLE='x y'\n",
            encoding="utf-8",
        )
        values = dev_postgres.load_dot_env(env_file)
        assert values["WINDAGENT_POSTGRES_PORT"] == "55435"
        assert values["QUOTED"] == "55436"
        assert values["SINGLE"] == "x y"


class TestAttestationCommand:
    def test_passes_required_output_flag(self):
        # Regression lock: check_postgres_backend.py declares --output
        # required=True; without it every `test` run died before pytest.
        cmd = dev_postgres._attestation_command("python", Path("s.py"), Path("o.json"))
        assert cmd[:2] == ["python", "s.py"]
        assert "--output" in cmd
        assert cmd[-1] == "o.json"


class TestBuildAsyncUrl:
    def test_url_shape_mirrors_ci(self):
        url = dev_postgres.build_async_url(55432, "windagent")
        # CI service containers use exactly this credential triple.
        assert url == "postgresql+asyncpg://test:test@localhost:55432/windagent"

    def test_url_starts_with_asyncpg_driver(self):
        # Real-PG contract tests require the asyncpg driver prefix.
        assert dev_postgres.build_async_url(1234, "x").startswith(
            "postgresql+asyncpg://"
        )


class TestValidateDbName:
    @pytest.mark.parametrize("name", ["windagent", "_leading", "Abc_123", "a1_b2"])
    def test_accepts_safe_names(self, name):
        assert dev_postgres.validate_db_name(name) == name

    @pytest.mark.parametrize(
        "name", ["", "9startsdigit", "has space", "has-dash", 'quote"']
    )
    def test_rejects_unsafe_names(self, name):
        with pytest.raises(SystemExit):
            dev_postgres.validate_db_name(name)


class TestNewDisposableDbName:
    def test_name_is_valid_and_prefixed(self):
        name = dev_postgres.new_disposable_db_name()
        assert name.startswith("windagent_test_")
        # Must itself pass the validator (safe as a PG identifier).
        assert dev_postgres.validate_db_name(name) == name

    def test_names_differ_across_pids(self, monkeypatch):
        monkeypatch.setattr(dev_postgres.os, "getpid", lambda: 111)
        first = dev_postgres.new_disposable_db_name()
        monkeypatch.setattr(dev_postgres.os, "getpid", lambda: 222)
        second = dev_postgres.new_disposable_db_name()
        assert first != second


class TestSummarizePytest:
    def test_pass_summary(self):
        text = "============================= 113 passed in 45.67s =============================\n"
        assert dev_postgres.summarize_pytest(text) == "113 passed"

    def test_mixed_summary(self):
        text = "= 10 failed, 100 passed, 3 skipped in 12.00s =\n"
        match = dev_postgres.summarize_pytest(text)
        assert "10 failed" in match and "100 passed" in match and "3 skipped" in match

    def test_no_summary_is_honest(self):
        assert dev_postgres.summarize_pytest("nothing here") == "no summary line found"

    def test_q_mode_borderless_summary(self):
        # `pytest -q` passthrough emits an unbordered final line.
        text = "113 passed in 45.67s\n"
        assert dev_postgres.summarize_pytest(text) == "113 passed"


class TestCli:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            dev_postgres.main(["--help"])
        assert excinfo.value.code == 0
        captured = capsys.readouterr().out
        for subcommand in ("up", "status", "url", "migrate", "test", "down"):
            assert subcommand in captured

    def test_missing_subcommand_errors(self):
        with pytest.raises(SystemExit) as excinfo:
            dev_postgres.main([])
        assert excinfo.value.code != 0

    def test_test_subcommand_collects_pytest_args(self):
        parser = dev_postgres.build_parser()
        args = parser.parse_args(
            ["test", "--", "-q", "tests/contracts/test_x.py::test_y"]
        )
        assert args.command == "test"
        assert args.db is None
        assert args.skip_drop is False
        assert args.pytest_args == ["-q", "tests/contracts/test_x.py::test_y"]

    def test_bare_positional_pytest_args_need_no_separator(self):
        args = dev_postgres.build_parser().parse_args(
            ["test", "tests/unit/scripts/test_dev_postgres.py"]
        )
        assert args.pytest_args == ["tests/unit/scripts/test_dev_postgres.py"]

    def test_down_clean_flag(self):
        args = dev_postgres.build_parser().parse_args(["down", "--clean"])
        assert args.clean is True
