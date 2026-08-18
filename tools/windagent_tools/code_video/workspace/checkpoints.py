"""
Incremental Checkpoint Manager for Tutorial Workspaces.

Captures, saves, restores, and verifies file snapshots and SHA-256 integrity
for deterministic replay throughout the Code Video tutorial build passes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple, Union

from windagent_core.errors.exceptions import NotFoundError, ValidationError
from windagent_tools.code_video.workspace.sandbox import TutorialWorkspace


def _compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class CheckpointRecord:
    """Immutable metadata record for a saved workspace checkpoint."""
    checkpoint_id: str
    name: str
    description: str
    timestamp_utc: str
    file_hashes: Dict[str, str]
    state_hash: str
    git_commit_sha: Optional[str] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "name": self.name,
            "description": self.description,
            "timestamp_utc": self.timestamp_utc,
            "file_hashes": dict(self.file_hashes),
            "state_hash": self.state_hash,
            "git_commit_sha": self.git_commit_sha,
            "extra_metadata": dict(self.extra_metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CheckpointRecord:
        return cls(
            checkpoint_id=str(data["checkpoint_id"]),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            timestamp_utc=str(data.get("timestamp_utc", "")),
            file_hashes=dict(data.get("file_hashes", {})),
            state_hash=str(data.get("state_hash", "")),
            git_commit_sha=data.get("git_commit_sha"),
            extra_metadata=dict(data.get("extra_metadata", {})),
        )


class CheckpointManager:
    """
    Manages deterministic checkpoint snapshots and verification.
    """

    def __init__(
        self,
        workspace: TutorialWorkspace,
        store_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.workspace = workspace
        self.store_root = (
            Path(store_root).resolve()
            if store_root
            else (workspace.workspace_root / ".checkpoints").resolve()
        )
        self.store_root.mkdir(parents=True, exist_ok=True)

    def _compute_workspace_state(self) -> Tuple[Dict[str, str], str]:
        """Compute SHA256 hashes of all files and composite state hash."""
        files = self.workspace.list_files()
        file_hashes: Dict[str, str] = {}
        hasher = hashlib.sha256()

        for rel_path in sorted(files):
            file_path = self.workspace.resolve_safe_path(rel_path)
            content_bytes = file_path.read_bytes()
            f_hash = _compute_sha256(content_bytes)
            file_hashes[rel_path] = f_hash
            hasher.update(f"{rel_path}:{f_hash}".encode("utf-8"))

        return file_hashes, hasher.hexdigest()

    def create_checkpoint(
        self,
        checkpoint_id: str,
        name: str,
        description: str = "",
        git_commit_sha: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord:
        """
        Capture current workspace state as an immutable snapshot.
        """
        if not checkpoint_id:
            raise ValidationError("checkpoint_id cannot be empty")

        file_hashes, state_hash = self._compute_workspace_state()
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            name=name,
            description=description,
            timestamp_utc=timestamp_utc,
            file_hashes=file_hashes,
            state_hash=state_hash,
            git_commit_sha=git_commit_sha,
            extra_metadata=extra_metadata or {},
        )

        cp_dir = self.store_root / checkpoint_id
        files_dir = cp_dir / "files"
        cp_dir.mkdir(parents=True, exist_ok=True)
        if files_dir.exists():
            shutil.rmtree(files_dir)
        files_dir.mkdir(parents=True, exist_ok=True)

        # Copy workspace files to checkpoint storage
        for rel_path in file_hashes:
            src_path = self.workspace.resolve_safe_path(rel_path)
            dest_path = files_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)

        # Save metadata record
        meta_file = cp_dir / "metadata.json"
        meta_file.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")

        return record

    def get_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointRecord]:
        """Retrieve checkpoint metadata if it exists."""
        meta_file = self.store_root / checkpoint_id / "metadata.json"
        if not meta_file.exists():
            return None
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            return CheckpointRecord.from_dict(data)
        except Exception:
            return None

    def list_checkpoints(self) -> List[CheckpointRecord]:
        """List all available checkpoints ordered by ID."""
        records: List[CheckpointRecord] = []
        if not self.store_root.exists():
            return []
        for cp_dir in sorted(self.store_root.iterdir()):
            if cp_dir.is_dir():
                record = self.get_checkpoint(cp_dir.name)
                if record:
                    records.append(record)
        return records

    def restore_checkpoint(self, checkpoint_id: str) -> CheckpointRecord:
        """
        Restore workspace files to the exact state of the specified checkpoint.
        """
        record = self.get_checkpoint(checkpoint_id)
        if not record:
            raise NotFoundError(f"Checkpoint '{checkpoint_id}' not found in store.")

        files_dir = self.store_root / checkpoint_id / "files"
        if not files_dir.exists():
            raise ValidationError(f"Corrupt checkpoint '{checkpoint_id}': files directory missing.")

        # Clean current non-hidden workspace files
        for rel_file in self.workspace.list_files():
            f_path = self.workspace.resolve_safe_path(rel_file)
            if f_path.exists():
                f_path.unlink()

        # Copy snapshot files back
        for rel_file in record.file_hashes:
            src_file = files_dir / rel_file
            if src_file.exists():
                dest_file = self.workspace.resolve_safe_path(rel_file)
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)

        return record

    def verify_checkpoint(self, checkpoint_id: str) -> Tuple[bool, List[str]]:
        """
        Verify that current workspace files match the checkpoint hashes.
        Returns (is_match, list_of_discrepancies).
        """
        record = self.get_checkpoint(checkpoint_id)
        if not record:
            raise NotFoundError(f"Checkpoint '{checkpoint_id}' not found.")

        current_hashes, current_state = self._compute_workspace_state()
        discrepancies: List[str] = []

        # Check missing or changed files
        for rel_path, exp_hash in record.file_hashes.items():
            if rel_path not in current_hashes:
                discrepancies.append(f"Missing file: '{rel_path}'")
            elif current_hashes[rel_path] != exp_hash:
                discrepancies.append(
                    f"Hash mismatch in '{rel_path}': expected {exp_hash[:8]}..., got {current_hashes[rel_path][:8]}..."
                )

        # Check unexpected extra files
        for rel_path in current_hashes:
            if rel_path not in record.file_hashes:
                discrepancies.append(f"Extra untracked file: '{rel_path}'")

        return len(discrepancies) == 0, discrepancies


__all__ = ["CheckpointRecord", "CheckpointManager"]
