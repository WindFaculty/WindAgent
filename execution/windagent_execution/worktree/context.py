"""Git-backed worktree lifecycle for coding-agent isolation.

The old implementation created ordinary directories below ``.worktrees``.
That does not isolate Git state and lets a coding runtime modify the primary
checkout.  This module is deliberately infrastructure-only: it receives a
repository root from the composition/service layer and uses Git's worktree
porcelain to create, inspect, quarantine, and remove linked worktrees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable


class WorktreeLifecycleError(RuntimeError):
    """Raised when Git cannot safely perform a requested worktree operation."""


@dataclass(frozen=True)
class WorktreeAllocation:
    """The durable identity of one coding agent's linked checkout."""

    worktree_id: str
    agent_instance_id: str
    path: Path
    branch: str
    repo_root: Path


@dataclass(frozen=True)
class WorktreeCleanupResult:
    """Outcome of cleanup; dirty output is retained in ``quarantine_path``."""

    status: str
    quarantine_path: Path | None = None
    cleanup_error: str | None = None


class WorktreeContextManager:
    """Own Git worktrees below a service-configured repository root.

    ``repo_root`` is never supplied by a client request.  The default
    worktree/quarantine locations are siblings of the primary checkout, so a
    linked checkout cannot show up as an untracked directory in that checkout.
    """

    _SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")
    _MANAGED_BRANCH_PREFIX = "windagent/agent/"

    def __init__(
        self,
        repo_root: str | Path,
        *,
        worktree_root: str | Path | None = None,
        quarantine_root: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        if not self.repo_root.is_dir():
            raise WorktreeLifecycleError(f"repository root does not exist: {self.repo_root}")
        self._assert_git_repository()

        default_base = self.repo_root.parent / ".windagent-worktrees" / self.repo_root.name
        self.worktree_root = Path(worktree_root or default_base).resolve()
        self.quarantine_root = Path(
            quarantine_root or self.worktree_root.parent / "quarantine"
        ).resolve()
        if self.worktree_root.is_relative_to(self.repo_root):
            raise WorktreeLifecycleError(
                "worktree root must not be inside the primary repository checkout"
            )

    def get_isolated_path(self, relative_path: str) -> Path:
        """Resolve a path inside the service-owned primary checkout."""
        target = (self.repo_root / relative_path).resolve()
        if not target.is_relative_to(self.repo_root):
            raise ValueError(f"Path traversal detected outside workspace root: {relative_path}")
        return target

    def ensure_worktree_dir(self, worktree_id: str) -> Path:
        """Compatibility wrapper that now creates a real linked checkout.

        New callers should use :meth:`create_worktree` so ownership/branch data
        are persisted by the orchestration layer.
        """
        return self.create_worktree(worktree_id, agent_instance_id=worktree_id).path

    def create_worktree(
        self,
        worktree_id: str,
        *,
        agent_instance_id: str,
        branch: str | None = None,
    ) -> WorktreeAllocation:
        """Create or recover one linked checkout and its dedicated branch."""
        safe_id = self._safe_id(worktree_id)
        path = (self.worktree_root / safe_id).resolve()
        branch_name = branch or f"{self._MANAGED_BRANCH_PREFIX}{safe_id}"
        existing = {entry.path: entry for entry in self.list_worktrees()}
        if path in existing:
            entry = existing[path]
            if entry.branch != branch_name:
                raise WorktreeLifecycleError(
                    f"worktree path is already owned by branch {entry.branch!r}: {path}"
                )
            return WorktreeAllocation(
                worktree_id=worktree_id,
                agent_instance_id=agent_instance_id,
                path=path,
                branch=branch_name,
                repo_root=self.repo_root,
            )
        if path.exists():
            raise WorktreeLifecycleError(
                f"refusing to reuse non-worktree directory: {path}"
            )

        self.worktree_root.mkdir(parents=True, exist_ok=True)
        if self._branch_exists(branch_name):
            self._run_git("worktree", "add", str(path), branch_name)
        else:
            self._run_git("worktree", "add", "-b", branch_name, str(path), "HEAD")
        return WorktreeAllocation(
            worktree_id=worktree_id,
            agent_instance_id=agent_instance_id,
            path=path,
            branch=branch_name,
            repo_root=self.repo_root,
        )

    def list_worktrees(self) -> tuple[WorktreeAllocation, ...]:
        """Return managed linked worktrees reported by Git, not filesystem guesses."""
        output = self._run_git("worktree", "list", "--porcelain")
        entries: list[WorktreeAllocation] = []
        block: dict[str, str] = {}
        for line in (*output.splitlines(), ""):
            if line:
                key, _, value = line.partition(" ")
                block[key] = value
                continue
            if not block:
                continue
            raw_path = block.get("worktree")
            raw_branch = block.get("branch")
            block = {}
            if not raw_path or not raw_branch:
                continue
            path = Path(raw_path).resolve()
            branch = raw_branch.removeprefix("refs/heads/")
            if not path.is_relative_to(self.worktree_root):
                continue
            if not branch.startswith(self._MANAGED_BRANCH_PREFIX):
                continue
            worktree_id = path.name
            entries.append(
                WorktreeAllocation(
                    worktree_id=worktree_id,
                    agent_instance_id=worktree_id,
                    path=path,
                    branch=branch,
                    repo_root=self.repo_root,
                )
            )
        return tuple(entries)

    def is_registered(self, path: str | Path) -> bool:
        resolved = Path(path).resolve()
        return any(entry.path == resolved for entry in self.list_worktrees())

    def cleanup_worktree(
        self,
        allocation: WorktreeAllocation,
        *,
        quarantine_dirty: bool = True,
        delete_branch: bool = True,
    ) -> WorktreeCleanupResult:
        """Quarantine uncommitted output, remove the checkout, then delete its branch."""
        try:
            dirty = self._is_dirty(allocation.path) if self.is_registered(allocation.path) else False
            quarantine_path = (
                self._quarantine(allocation) if dirty and quarantine_dirty else None
            )
            if self.is_registered(allocation.path):
                self._run_git("worktree", "remove", "--force", str(allocation.path))
            if delete_branch and self._branch_exists(allocation.branch):
                self._run_git("branch", "-D", allocation.branch)
            return WorktreeCleanupResult(
                status="quarantined" if quarantine_path else "removed",
                quarantine_path=quarantine_path,
            )
        except WorktreeLifecycleError as exc:
            return WorktreeCleanupResult(status="cleanup_failed", cleanup_error=str(exc))

    def cleanup_orphans(
        self, managed_paths: Iterable[str | Path]
    ) -> tuple[WorktreeCleanupResult, ...]:
        """Remove managed Git worktrees absent from the durable database set."""
        known = {Path(path).resolve() for path in managed_paths}
        return tuple(
            self.cleanup_worktree(entry)
            for entry in self.list_worktrees()
            if entry.path not in known
        )

    def _quarantine(self, allocation: WorktreeAllocation) -> Path:
        destination = self.quarantine_root / self._safe_id(allocation.worktree_id)
        if destination.exists():
            suffix = 1
            while (self.quarantine_root / f"{destination.name}-{suffix}").exists():
                suffix += 1
            destination = self.quarantine_root / f"{destination.name}-{suffix}"
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "branch.txt").write_text(allocation.branch + "\n", encoding="utf-8")
        (destination / "status.txt").write_text(
            self._run_git_at(allocation.path, "status", "--porcelain=v1"), encoding="utf-8"
        )
        patch = self._run_git_at(allocation.path, "diff", "--binary")
        staged_patch = self._run_git_at(allocation.path, "diff", "--cached", "--binary")
        (destination / "uncommitted.patch").write_text(patch + staged_patch, encoding="utf-8")
        untracked = self._run_git_at(allocation.path, "ls-files", "--others", "--exclude-standard", "-z")
        for raw_path in filter(None, untracked.split("\0")):
            source = (allocation.path / raw_path).resolve()
            if not source.is_relative_to(allocation.path) or not source.is_file():
                continue
            target = destination / "untracked" / raw_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return destination

    def _is_dirty(self, path: Path) -> bool:
        return bool(self._run_git_at(path, "status", "--porcelain=v1").strip())

    def _assert_git_repository(self) -> None:
        top_level = Path(self._run_git("rev-parse", "--show-toplevel").strip()).resolve()
        if top_level != self.repo_root:
            raise WorktreeLifecycleError(
                f"configured repository root is not Git's top-level: {self.repo_root}"
            )

    def _branch_exists(self, branch: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode in (0, 1):
            return result.returncode == 0
        raise WorktreeLifecycleError(self._format_git_error(result, "show-ref"))

    def _run_git_at(self, path: Path, *args: str) -> str:
        return self._run_git(*args, cwd=path)

    def _run_git(self, *args: str, cwd: Path | None = None) -> str:
        location = (cwd or self.repo_root).resolve()
        result = subprocess.run(
            ["git", "-C", str(location), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorktreeLifecycleError(self._format_git_error(result, " ".join(args)))
        return result.stdout

    @staticmethod
    def _format_git_error(result: subprocess.CompletedProcess[str], command: str) -> str:
        detail = (result.stderr or result.stdout or "Git command failed").strip()
        return f"git {command} failed (exit {result.returncode}): {detail[:500]}"

    @classmethod
    def _safe_id(cls, value: str) -> str:
        sanitized = cls._SAFE_ID.sub("-", str(value)).strip(".-")
        if not sanitized:
            raise WorktreeLifecycleError("worktree id must contain a safe filename character")
        return sanitized[:96]
