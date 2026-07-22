"""Phase 6 — Per-agent Git worktree lifecycle (ban_ke_hoach §9 + §7.3).

One isolated worktree per coding agent instance:

  <repo-root>/.windagent/worktrees/<conversation-id>/<agent-instance-id>/

Branch naming:

  windagent/<conversation-id>/<task-id>/<agent-instance-id>

The coding agent runs with its cwd set to the worktree path, so it can
never write into the user's primary workspace. On task completion the
worktree is unlinked but the branch is preserved for audit/recovery
(ADR 0004 retention policy). Failed/cancelled worktrees are quarantined,
not deleted, for the retention window.

Research/Browser/Orchestrator agents get NO worktree — they read the
repo root or a browser context instead (ban_ke_hoach §2.3 / §7.3).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, update

from db.database import Database
from db.models import WorktreeORM

log = logging.getLogger(__name__)

# Agent types that get an isolated writable worktree.
CODING_AGENT_TYPES = frozenset({
    "coder", "coding", "backend", "frontend", "test", "reviewer",
})

METADATA_DIR = ".windagent"
WORKTREES_DIR = "worktrees"
# ponytail: quarantine instead of delete; retention window is admin-held
# outside this service. Loader just flips status -> quarantined.
QUARANTINE_STATUSES = frozenset({"quarantined", "active", "merged"})


class WorktreeService:
    def __init__(self, db: Database, repo_root: str) -> None:
        self.db = db
        self.repo_root = os.path.abspath(repo_root)

    def safe_workspace_root(self, raw: str) -> str:
        """Resolve `raw` under `repo_root` and reject traversal.

        Raises ValueError if resolved path escapes repo_root.
        Returns absolute path when safe.
        """
        candidate = os.path.abspath(os.path.join(self.repo_root, raw))
        try:
            os.path.relpath(candidate, self.repo_root)
        except ValueError:
            raise ValueError(f"workspace_root escapes repo_root: {raw}")

        # relpath can still yield '..' segments on case-insensitive/
        # symlinked filesystems; verify prefix.
        repo_prefix = os.path.abspath(self.repo_root)
        if not candidate.startswith(repo_prefix + os.sep) and candidate != repo_prefix:
            raise ValueError(f"workspace_root escapes repo_root: {raw}")
        return candidate

    # ---------- helpers ----------

    def _assert_git_repo(self) -> None:
        if not os.path.isdir(os.path.join(self.repo_root, ".git")):
            raise NotAGitRepositoryError(self.repo_root)

    def _worktree_dir(self, conversation_id: str, instance_id: str) -> str:
        return os.path.join(
            self.repo_root, METADATA_DIR, WORKTREES_DIR,
            conversation_id, instance_id,
        )

    def _branch_name(self, conversation_id: str, task_id: str | None,
                     instance_id: str) -> str:
        # ponytail: task_id optional (orchestrator-spawns without task)
        task_seg = task_id or "task"
        return f"windagent/{conversation_id}/{task_seg}/{instance_id}"

    # ---------- lifecycle ----------

    async def create(
        self,
        *,
        conversation_id: str,
        agent_instance_id: str,
        agent_type: str,
        task_id: Optional[str] = None,
    ) -> Optional[WorktreeORM]:
        """Create an isolated worktree for a coding agent.

        Returns None for non-coding agents (no worktree by design).
        """
        if agent_type.lower() not in CODING_AGENT_TYPES:
            return None

        self._assert_git_repo()

        path = self._worktree_dir(conversation_id, agent_instance_id)
        branch = self._branch_name(conversation_id, task_id, agent_instance_id)

        # Idempotent: reuse an existing live worktree for this instance.
        async with self.db.session() as s:
            stmt = select(WorktreeORM).where(
                WorktreeORM.agent_instance_id == agent_instance_id,
                WorktreeORM.status.in_(QUARANTINE_STATUSES),
            )
            existing = (await s.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return existing

        if os.path.exists(path):
            # stale path from a previous run; remove before recreate
            shutil.rmtree(path, ignore_errors=True)

        cmd = [
            "git", "worktree", "add", path, "-b", branch,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise WorktreeError(
                f"git worktree add failed ({proc.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )

        wt = WorktreeORM(
            id=f"wt_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            agent_instance_id=agent_instance_id,
            task_id=task_id,
            branch_name=branch,
            path=path,
            repo_root=self.repo_root,
            status="active",
        )
        async with self.db.session() as s:
            s.add(wt)
        log.info("worktree created path=%s branch=%s", path, branch)
        return wt

    async def remove(self, agent_instance_id: str, *, quarantine: bool = False) -> None:
        """Unlink a worktree. Branch history is preserved unless wiped.

        Quarantined worktrees stay on disk for the retention window so a
        developer can inspect local edits/logs (ADR 0004 §5).
        """
        async with self.db.session() as s:
            stmt = select(WorktreeORM).where(
                WorktreeORM.agent_instance_id == agent_instance_id,
                WorktreeORM.status.in_(QUARANTINE_STATUSES),
            )
            wt = (await s.execute(stmt)).scalar_one_or_none()
            if wt is None:
                return
            path = wt.path

            # `git worktree remove` cleans the checkout; keep the branch.
            proc = await asyncio.create_subprocess_exec(
                "git", "worktree", "remove", path, "--force",
                cwd=self.repo_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                # path may already be gone; only hard-fail on unexpected err
                err = stderr.decode(errors="replace").strip()
                if "not a working tree" not in err:
                    log.warning("worktree remove issue: %s", err)

            if os.path.exists(path):
                shutil.rmtree(path, ignore_errors=True)

            new_status = "quarantined" if quarantine else "removed"
            stmt_up = (
                update(WorktreeORM)
                .where(WorktreeORM.id == wt.id)
                .values(status=new_status, removed_at=datetime.now(timezone.utc))
            )
            await s.execute(stmt_up)
        log.info("worktree %s for instance %s", new_status, agent_instance_id)

    async def capture_diff(self, agent_instance_id: str) -> Optional[str]:
        """Return a diff summary for an active worktree.

        Includes untracked files (coding agents create new files that are
        never staged before the inspector views them), plus the standard
        `git diff --stat` for tracked edits.
        """
        async with self.db.session() as s:
            stmt = select(WorktreeORM).where(
                WorktreeORM.agent_instance_id == agent_instance_id,
                WorktreeORM.status.in_(QUARANTINE_STATUSES),
            )
            wt = (await s.execute(stmt)).scalar_one_or_none()
            if wt is None or not os.path.isdir(wt.path):
                return None

        untracked = await self._run_git(
            ["status", "--porcelain"], cwd=wt.path
        )
        tracked = await self._run_git(
            ["diff", "--stat"], cwd=wt.path
        )
        combined = f"status:\n{untracked.strip()}"
        if tracked.strip():
            combined += "\n\ndiff --stat:\n" + tracked.strip()
        async with self.db.session() as s:
            stmt_up = (
                update(WorktreeORM)
                .where(WorktreeORM.id == wt.id)
                .values(last_diff_summary=combined)
            )
            await s.execute(stmt_up)
        return combined

    async def list_for_conversation(self, conversation_id: str) -> List[WorktreeORM]:
        async with self.db.session() as s:
            stmt = select(WorktreeORM).where(
                WorktreeORM.conversation_id == conversation_id
            )
            return list((await s.execute(stmt)).scalars().all())

    # ---------- integration (merge into main workspace) ----------

    async def integrate(
        self,
        *,
        agent_instance_id: str,
        target_branch: str = "main",
        strategy: str = "merge",
    ) -> Dict[str, object]:
        """Merge/cherry-pick a coding agent's branch into the target branch.

        Runs on the repo root (main workspace), NOT inside the worktree, so
        integration-agent never edits worktrees directly. Returns a dict
        with `ok`, `method`, and either `merged` or `conflict` info.
        """
        async with self.db.session() as s:
            stmt = select(WorktreeORM).where(
                WorktreeORM.agent_instance_id == agent_instance_id,
                WorktreeORM.status.in_(QUARANTINE_STATUSES),
            )
            wt = (await s.execute(stmt)).scalar_one_or_none()
            if wt is None:
                raise WorktreeError(f"no worktree for instance {agent_instance_id}")
            branch = wt.branch_name

        # ponytail: prefer merge; cherry-pick added only when strategy says so
        if strategy == "cherry-pick":
            # integrate only the tip commit of the branch
            tip = (await self._run_git(
                ["rev-parse", branch], cwd=self.repo_root
            )).strip()
            args: List[str] = ["cherry-pick", tip]
        else:
            args = ["merge", "--no-ff", branch]

        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=self.repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        out_s = out.decode(errors="replace").strip()
        err_s = err.decode(errors="replace").strip()

        if proc.returncode != 0:
            # Abort a half-open merge so the main workspace stays clean.
            await self._run_git(["merge", "--abort"], cwd=self.repo_root)
            async with self.db.session() as s:
                stmt_up = (
                    update(WorktreeORM)
                    .where(WorktreeORM.id == wt.id)
                    .values(status="conflict")
                )
                await s.execute(stmt_up)
            return {
                "ok": False,
                "method": strategy,
                "conflict": True,
                "detail": err_s or out_s,
            }

        async with self.db.session() as s:
            stmt_up = (
                update(WorktreeORM)
                .where(WorktreeORM.id == wt.id)
                .values(status="merged")
            )
            await s.execute(stmt_up)
        return {
            "ok": True,
            "method": strategy,
            "merged": True,
            "detail": out_s,
        }

    # ---------- git exec ----------

    async def _run_git(self, args: List[str], *, cwd: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
        return out.decode(errors="replace")


class WorktreeError(RuntimeError):
    pass


class NotAGitRepositoryError(WorktreeError):
    pass
