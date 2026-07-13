"""Phase 6 gate (ban_ke_hoach §9 / Giai đoạn 6):

  - Two coding agents spawn into SEPARATE worktrees and edit files there
    without touching the main workspace (repo root).
  - Non-coding agents (researcher) get NO worktree.
  - Worktree diff capture reflects isolated edits.
  - Permission profile classifier: Standard needs approval for
    push/install/destructive; Autonomous allows; Safe blocks.
"""
from __future__ import annotations

import asyncio
import os
import subprocess

import pytest

from db.database import Database
from services.worktree_service import WorktreeService, NotAGitRepositoryError
from services.permission_profile import classify_command


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def repo(tmp_path):
    """A real git repo with an initial commit on `main`."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t.io")
    _git(r, "config", "user.name", "t")
    (r / "README.md").write_text("# root\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "init")
    return str(r)


async def _make_agent(db, agent_id, agent_type):
    from sqlalchemy import select
    from db.models import AgentORM
    async with db.session() as s:
        existing = (await s.execute(
            select(AgentORM).where(AgentORM.id == agent_id)
        )).scalar_one_or_none()
        if existing is None:
            s.add(AgentORM(
                id=agent_id, name=agent_id, runtime_type="hermes",
                router_role=agent_type.capitalize(),
                toolsets_json="[]", skills_json="[]",
            ))


async def test_two_coding_agents_isolated(repo):
    """Gate: two coding agents edit two worktrees, root stays clean."""
    db = Database(f"sqlite+aiosqlite:///{repo}/phase6.db")
    await db.init_models()
    await _make_agent(db, "c1", "coder")
    await _make_agent(db, "c2", "coder")

    svc = WorktreeService(db, repo_root=repo)

    wt1 = await svc.create(
        conversation_id="c1", agent_instance_id="inst_a",
        agent_type="coder", task_id="t1",
    )
    wt2 = await svc.create(
        conversation_id="c1", agent_instance_id="inst_b",
        agent_type="coder", task_id="t2",
    )
    assert wt1 is not None and wt2 is not None
    assert wt1.path != wt2.path
    assert os.path.isdir(wt1.path) and os.path.isdir(wt2.path)
    # branch naming per ADR 0004
    assert wt1.branch_name == "windagent/c1/t1/inst_a"
    assert wt2.branch_name == "windagent/c1/t2/inst_b"

    # Each agent edits its own worktree only.
    from pathlib import Path
    (Path(wt1.path) / "a.py").write_text("print('a')\n")
    (Path(wt2.path) / "b.py").write_text("print('b')\n")

    # Main workspace untouched.
    assert not os.path.exists(os.path.join(repo, "a.py"))
    assert not os.path.exists(os.path.join(repo, "b.py"))
    # Worktree edits isolated from each other.
    assert not os.path.exists(os.path.join(wt1.path, "b.py"))
    assert not os.path.exists(os.path.join(wt2.path, "a.py"))

    # Diff capture reflects only the owning worktree.
    d1 = await svc.capture_diff("inst_a")
    assert "a.py" in (d1 or "")
    assert "b.py" not in (d1 or "")

    # Stop -> quarantine, branch preserved, path removed.
    await svc.remove("inst_a", quarantine=True)
    async with db.session() as s:
        from sqlalchemy import select
        from db.models import WorktreeORM
        w = (await s.execute(
            select(WorktreeORM).where(WorktreeORM.id == wt1.id)
        )).scalar_one_or_none()
        assert w.status == "quarantined"
    assert not os.path.exists(wt1.path)
    # branch still exists in the repo
    branches = subprocess.run(
        ["git", "branch", "--list", wt1.branch_name],
        cwd=repo, capture_output=True, text=True,
    ).stdout
    assert wt1.branch_name in branches
    await db.dispose()


async def test_non_coding_agent_no_worktree(repo):
    db = Database(f"sqlite+aiosqlite:///{repo}/phase6b.db")
    await db.init_models()
    svc = WorktreeService(db, repo_root=repo)
    wt = await svc.create(
        conversation_id="c2", agent_instance_id="inst_r",
        agent_type="researcher", task_id=None,
    )
    assert wt is None  # no worktree for read-only agents
    await db.dispose()


async def test_not_a_git_repo(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/x.db")
    await db.init_models()
    svc = WorktreeService(db, repo_root=str(tmp_path))
    with pytest.raises(NotAGitRepositoryError):
        await svc.create(
            conversation_id="c", agent_instance_id="i",
            agent_type="coder", task_id="t",
        )
    await db.dispose()


def test_permission_standard_needs_approval():
    assert classify_command("Standard", "npm install").action == "needs_approval"
    assert classify_command("Standard", "git push origin main").action == "needs_approval"
    assert classify_command("Standard", "rm -rf old_dir").action == "needs_approval"
    # benign edits auto-allowed
    assert classify_command("Standard", "git commit -am wip").action == "allow"


def test_permission_autonomous_allows():
    assert classify_command("Autonomous", "npm install").action == "allow"
    assert classify_command("Autonomous", "git push").action == "allow"


def test_permission_safe_blocks_risky():
    assert classify_command("Safe", "npm install").action == "blocked"
    assert classify_command("Safe", "git push").action == "blocked"
    # safe local edit allowed
    assert classify_command("Safe", "git commit -am wip").action == "allow"


def test_permission_force_push_always_blocked():
    for p in ("Standard", "Autonomous", "Safe"):
        assert classify_command(p, "git push -f origin main").action == "blocked"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
