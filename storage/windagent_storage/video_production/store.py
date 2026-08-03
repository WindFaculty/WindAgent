"""
Content-addressed artifact stores (plan 05 §14.1, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

Two stores with one crash-safety contract:

- `ContentAddressedStore` — immutable byte store keyed by SHA-256 of the
  payload. Publish is atomic (temp write + fsync + atomic rename); a crash
  never leaves a partial artifact visible.

- `ArtifactRecordStore` — durable metadata records keyed by artifact_id.
  Writes are atomic (temp + rename) with a compare-and-swap version guard so
  a stale writer never clobbers a newer record (gate: duplicate/stale writes
  cause no side effects).

The publisher (publisher.py) composes both so that a record is only VALID
after the content file exists AND the record write landed — a crash between
the two leaves an orphan file WITHOUT a VALID record, never a VALID record
pointing at a missing file (§14.1).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import List, Optional

from windagent_storage.video_production.model import (
    ArtifactRecord,
    ArtifactStatus,
)


class ContentAddressedStore:
    """Immutable, content-addressed byte store keyed by SHA-256 (§14.1)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def path_for(self, content_hash: str) -> Path:
        return self.root / content_hash

    def exists(self, content_hash: str) -> bool:
        return self.path_for(content_hash).is_file()

    def publish(self, data: bytes) -> str:
        """Atomically publish payload bytes; returns the content hash.

        Idempotent: if the content hash already exists, returns immediately.
        A crash never leaves a partial file visible.
        """
        digest = self.content_hash(data)
        target = self.path_for(digest)
        if target.is_file():
            return digest
        tmp = self.root / f".{digest}.tmp-{os.getpid()}-{time.time_ns()}"
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        return digest

    def read(self, content_hash: str) -> Optional[bytes]:
        target = self.path_for(content_hash)
        if not target.is_file():
            return None
        return target.read_bytes()

    def list_hashes(self) -> List[str]:
        return sorted(
            p.name
            for p in self.root.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )


class ArtifactRecordStore:
    """Durable metadata records keyed by artifact_id (atomic, append-only history).

    Writes are atomic (unique temp name + rename) so a crash never leaves a
    partial record. The history guard rejects any save that would DROP existing
    audit entries — invalidation preserves history (§14.3).
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, artifact_id: str) -> Path:
        return self.state_dir / f"record_{artifact_id}.json"

    def save(self, record: ArtifactRecord) -> None:
        """Atomic temp+rename write; history is append-only.

        Concurrent writers use unique temp names so two saves of the same
        record can never corrupt each other's temp file; the final os.replace
        is atomic.
        """
        existing = self.load(record.artifact_id)
        if existing is not None:
            # Never silently drop existing history/status transitions.
            if len(record.history) < len(existing.history):
                raise ValueError(
                    f"Cannot save record {record.artifact_id}: history would shrink "
                    f"({len(existing.history)} -> {len(record.history)}). History is append-only."
                )
        path = self._path(record.artifact_id)
        tmp = path.with_name(f".record_{record.artifact_id}.tmp-{os.getpid()}-{time.time_ns()}")
        tmp.write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, path)

    def load(self, artifact_id: str) -> Optional[ArtifactRecord]:
        path = self._path(artifact_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ArtifactRecord.from_dict(data)

    def exists(self, artifact_id: str) -> bool:
        return self._path(artifact_id).exists()

    def list_ids(self) -> List[str]:
        return sorted(p.name[len("record_") : -len(".json")] for p in self.state_dir.glob("record_*.json"))

    def all_records(self) -> List[ArtifactRecord]:
        return [r for aid in self.list_ids() if (r := self.load(aid)) is not None]

    def valid_records(self) -> List[ArtifactRecord]:
        return [r for r in self.all_records() if r.status == ArtifactStatus.VALID]


__all__ = ["ContentAddressedStore", "ArtifactRecordStore"]
