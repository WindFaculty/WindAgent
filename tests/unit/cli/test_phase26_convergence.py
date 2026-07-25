"""
Phase 26 Unit and Convergence Tests: CLI, Web, and Desktop Multi-Interface Convergence.
Verifies CLI subcommands and --json output mode, desktop Rust codebase path portability,
and sidecar manager dynamic port reservation and process lifecycle.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "tools", "apps/cli", "apps/desktop"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from windagent_cli.main import main, doctor, run_task, task_list, list_providers, list_tools, run_eval, architecture_check
from sidecar_manager import SidecarManager, get_free_port


def test_cli_doctor_text_and_json(capsys):
    """Verify CLI doctor command in text and JSON mode."""
    res_text = doctor(json_mode=False)
    assert res_text == 0
    captured_text = capsys.readouterr().out
    assert "WindAgent Doctor" in captured_text

    res_json = doctor(json_mode=True)
    assert res_json == 0
    captured_json = capsys.readouterr().out
    parsed = json.loads(captured_json)
    assert parsed["status"] == "ALL_SYSTEMS_OPERATIONAL"
    assert "checks" in parsed


def test_cli_run_task_and_task_list_json(capsys):
    """Verify CLI run_task and task_list commands with --json flag."""
    res_run = main(["run", "--prompt", "Fix payment timeout", "--json"])
    assert res_run == 0
    run_out = json.loads(capsys.readouterr().out)
    assert "task_id" in run_out
    assert run_out["prompt"] == "Fix payment timeout"

    res_list = main(["task", "list", "--json"])
    assert res_list == 0
    list_out = json.loads(capsys.readouterr().out)
    assert isinstance(list_out, list)
    assert len(list_out) >= 1


def test_cli_providers_tools_and_eval_json(capsys):
    """Verify CLI providers, tools, and eval subcommands in JSON mode."""
    main(["providers", "--json"])
    provs = json.loads(capsys.readouterr().out)
    assert any(p["provider"] == "openai" for p in provs)

    main(["tools", "--json"])
    tools = json.loads(capsys.readouterr().out)
    assert any(t["name"] == "read_file" for t in tools)

    main(["eval", "--suite", "all", "--json"])
    eval_res = json.loads(capsys.readouterr().out)
    assert eval_res["verdict"] in ("EVAL PASSED", "EVAL_PASSED")


def test_cli_architecture_check():
    """Verify CLI architecture-check subcommand returns 0 exit code."""
    res = architecture_check(json_mode=True)
    assert res == 0


def test_desktop_rust_codebase_path_portability():
    """Verify no hardcoded absolute paths exist in desktop Rust codebase."""
    lib_rs = root / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs"
    assert lib_rs.exists()
    content = lib_rs.read_text(encoding="utf-8")
    assert "D:\\" not in content, "Found hardcoded D:\\ path in desktop lib.rs!"
    assert r"D:\antigaravity_code" not in content, "Found hardcoded antigravity path in desktop lib.rs!"


def test_desktop_sidecar_manager_lifecycle():
    """Verify SidecarManager dynamic port allocation, health monitoring, and shutdown."""
    port1 = get_free_port()
    port2 = get_free_port()
    assert port1 != port2
    assert port1 > 1024

    mgr = SidecarManager()
    st_api = mgr.spawn_api_sidecar(mock_spawn=True, port=port1)
    assert st_api.running is True
    assert st_api.port == port1

    st_worker = mgr.spawn_worker_sidecar(mock_spawn=True)
    assert st_worker.running is True

    health = mgr.check_health()
    assert health["api"] is True
    assert health["worker"] is True

    mgr.shutdown()
