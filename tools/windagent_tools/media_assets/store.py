"""
Content-addressed store for validated assets (plan 02 §21.2).

Publish is atomic: the payload is written to a temp path, fsynced, then
atomically renamed to its final content-hash name. A crash/cancel never
leaves a partial artifact visible in the store, and a failed validation
never publishes anything.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional


class ContentAddressedStore:
    """Immutable, content-addressed store keyed by SHA-256 of the payload."""

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
        """Atomically publish payload; returns its content hash.

        Raises on write failure and never leaves a partial file.
        """
        digest = self.content_hash(data)
        target = self.path_for(digest)
        if target.is_file():
            return digest  # content already present (idempotent)

        tmp = self.root / f".{digest}.tmp-{os.getpid()}"
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

    def list_hashes(self) -> list[str]:
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_file() and not p.name.startswith(".")
        )


__all__ = ["ContentAddressedStore"]
