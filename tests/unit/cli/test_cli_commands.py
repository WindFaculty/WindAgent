"""
Unit and E2E tests for WindAgent Production CLI subcommands (Phase 12).
"""

from windagent_cli.main import main


def test_cli_help_returns_success(capsys):
    assert main(["--help"]) == 0
    assert "usage: windagent" in capsys.readouterr().out


def test_cli_version_returns_success(capsys):
    assert main(["--version", "--json"]) == 0
    assert '"product_version"' in capsys.readouterr().out


def test_cli_parse_error_returns_usage_code(capsys):
    assert main(["doctor", "--unknown-option"]) == 3
    assert "unrecognized arguments" in capsys.readouterr().err


def test_cli_unknown_command_returns_usage_code(capsys):
    assert main(["not-a-command"]) == 3
    assert "invalid choice" in capsys.readouterr().err


def test_cli_doctor_command(capsys):
    ret = main(["doctor"])
    assert ret == 2
    captured = capsys.readouterr()
    assert "WindAgent Doctor" in captured.out
    assert "System health status: DOWN" in captured.out


def test_cli_run_command(capsys):
    ret = main(["run", "--prompt", "Fix bug in calc", "--workflow", "bugfix"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "WindAgent Run Task" in captured.out
    assert "Fix bug in calc" in captured.out


def test_cli_status_command(capsys):
    ret = main(["status", "--demo"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "WindAgent System Status (DEMO)" in captured.out


def test_cli_task_list_and_inspect_commands(capsys):
    ret1 = main(["task", "list", "--demo"])
    assert ret1 == 0
    captured1 = capsys.readouterr()
    assert "WindAgent Task List (DEMO)" in captured1.out

    ret2 = main(["task", "inspect", "task_demo_01", "--demo"])
    assert ret2 == 0
    captured2 = capsys.readouterr()
    assert "Inspecting Task [task_demo_01] (DEMO)" in captured2.out


def test_cli_replay_command(capsys):
    ret = main(["replay", "trace_100", "--demo"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Replaying Trace [trace_100] (DEMO)" in captured.out


def test_cli_providers_and_tools_commands(capsys):
    ret1 = main(["providers", "--demo"])
    assert ret1 == 0
    captured1 = capsys.readouterr()
    assert "Configured Model Providers (DEMO)" in captured1.out

    ret2 = main(["tools", "--demo"])
    assert ret2 == 0
    captured2 = capsys.readouterr()
    assert "Registered System Tools (DEMO)" in captured2.out


def test_cli_eval_command(capsys):
    ret = main(["eval", "--suite", "bugfix", "--demo"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Running Evaluation Suite [bugfix] (DEMO)" in captured.out
    assert "EVAL PASSED" in captured.out


def test_cli_architecture_check_command(capsys):
    ret = main(["architecture-check"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Architecture Checker" in captured.out
    assert "ALL CHECKS PASSED" in captured.out
