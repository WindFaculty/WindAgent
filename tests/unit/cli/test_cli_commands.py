"""
Unit and E2E tests for WindAgent Production CLI subcommands (Phase 12).
"""

from windagent_cli.main import main


def test_cli_doctor_command(capsys):
    ret = main(["doctor"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "WindAgent Doctor" in captured.out
    assert "ALL SYSTEMS OPERATIONAL" in captured.out


def test_cli_run_command(capsys):
    ret = main(["run", "--prompt", "Fix bug in calc", "--workflow", "bugfix"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "WindAgent Run Task" in captured.out
    assert "Fix bug in calc" in captured.out


def test_cli_status_command(capsys):
    ret = main(["status"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "WindAgent System Status" in captured.out


def test_cli_task_list_and_inspect_commands(capsys):
    ret1 = main(["task", "list"])
    assert ret1 == 0
    captured1 = capsys.readouterr()
    assert "WindAgent Task List" in captured1.out

    ret2 = main(["task", "inspect", "task_demo_01"])
    assert ret2 == 0
    captured2 = capsys.readouterr()
    assert "Inspecting Task [task_demo_01]" in captured2.out


def test_cli_replay_command(capsys):
    ret = main(["replay", "trace_100"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Replaying Trace [trace_100]" in captured.out


def test_cli_providers_and_tools_commands(capsys):
    ret1 = main(["providers"])
    assert ret1 == 0
    captured1 = capsys.readouterr()
    assert "Configured Model Providers" in captured1.out

    ret2 = main(["tools"])
    assert ret2 == 0
    captured2 = capsys.readouterr()
    assert "Registered System Tools" in captured2.out


def test_cli_eval_command(capsys):
    ret = main(["eval", "--suite", "bugfix"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Running Evaluation Suite [bugfix]" in captured.out
    assert "EVAL PASSED" in captured.out


def test_cli_architecture_check_command(capsys):
    ret = main(["architecture-check"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Architecture Checker" in captured.out
    assert "ALL CHECKS PASSED" in captured.out
