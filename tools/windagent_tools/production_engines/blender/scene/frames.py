"""
VP3D Phase 4 — Frame manifest & atomic frame pipeline (plan Stage B §4 items 3-4).

`FrameManifest` is the durable record of which frames are VALIDATED. Rules:

- a rendered frame is written to a TEMP path first (``frame_XXXX.png.tmp``);
  only after validation (non-empty, dimension check) is it atomically renamed
  to its FINAL name and registered in the manifest;
- cancel mid-chunk NEVER publishes a half-written frame — the temp file is
  discarded and the frame stays absent from the manifest;
- `next_frame()` computes the FIRST unvalidated frame in the range, so resume
  starts exactly at the next valid frame (item 4);
- the manifest stores per-frame SHA-256 + dimensions so `VERIFY` can check
  every frame and so reuse decisions have exact content identity.

This module is pure Python (no bpy) so it is fully contract-tested in CI with
fake executables.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

FRAME_MANIFEST_FILENAME = "frame_manifest.json"
TEMP_SUFFIX = ".tmp"
FRAME_NAME_TEMPLATE = "frame_{frame:04d}.{ext}"


def sha256_file(path: Path) -> str:
    """SHA-256 of a file; empty string when unreadable (fail closed)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""


def probe_dimensions(path: Path) -> Dict[str, int]:
    """Best-effort PNG/EXR dimension probe (pure Python, no external deps).

    Parses the PNG IHDR or the EXR header; returns {} when unknown. Used by
    `validate_frame` so frames are verified before they become final.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return {"width": width, "height": height}
    if data[:4] == b"\x76\x2f\x31\x01":  # EXR magic
        # EXR header: magic(4) + version(4); scan for resolution in attributes.
        try:
            width = int.from_bytes(data[8:12], "little")
            return {"width": width, "height": 0}
        except Exception:  # pragma: no cover - defensive
            return {}
    return {}


@dataclass(frozen=True)
class FrameEntry:
    """One validated frame."""

    frame: int
    filename: str
    sha256: str
    width: int = 0
    height: int = 0
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "frame": self.frame,
            "filename": self.filename,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FrameEntry":
        return cls(
            frame=int(data["frame"]),
            filename=str(data.get("filename", "")),
            sha256=str(data.get("sha256", "")),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
            size_bytes=int(data.get("size_bytes", 0)),
        )


class FrameManifest:
    """Durable record of validated frames for one render job."""

    def __init__(
        self,
        *,
        workspace: Path,
        frame_range: tuple[int, int],
        extension: str = "png",
        expected_dimensions: Optional[Dict[str, int]] = None,
        content_hash: str = "",
    ) -> None:
        self._workspace = Path(workspace)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._start, self._end = frame_range
        self._extension = extension
        self._expected_dimensions = dict(expected_dimensions or {})
        self._content_hash = content_hash
        self._frames: Dict[int, FrameEntry] = {}
        self.load()

    # ------------------------------------------------------------------
    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def frames(self) -> List[FrameEntry]:
        return [self._frames[k] for k in sorted(self._frames)]

    @property
    def content_hash(self) -> str:
        """Input hash the manifest was pinned to (Phase 21 recovery gate)."""
        return self._content_hash

    @property
    def validated_frames(self) -> List[int]:
        return sorted(self._frames)

    @property
    def manifest_path(self) -> Path:
        return self._workspace / FRAME_MANIFEST_FILENAME

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.manifest_path.is_file():
            return
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for entry in data.get("frames", []) or []:
            try:
                fe = FrameEntry.from_dict(entry)
            except (KeyError, TypeError, ValueError):
                continue
            if fe.frame < self._start or fe.frame > self._end:
                continue
            if not (self._workspace / fe.filename).is_file():
                continue  # a manifest entry whose file vanished is NOT valid
            self._frames[fe.frame] = fe

    def save(self) -> None:
        payload = {
            "frame_range": [self._start, self._end],
            "extension": self._extension,
            "expected_dimensions": self._expected_dimensions,
            "content_hash": self._content_hash,
            "frames": [fe.to_dict() for fe in self.frames],
        }
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    def has_frame(self, frame: int) -> bool:
        return frame in self._frames

    def next_frame(self) -> Optional[int]:
        """First unvalidated frame in the range, or None when the range is full."""
        for frame in range(self._start, self._end + 1):
            if frame not in self._frames:
                return frame
        return None

    def temp_path(self, frame: int) -> Path:
        return self._workspace / (FRAME_NAME_TEMPLATE.format(frame=frame, ext=self._extension) + TEMP_SUFFIX)

    def final_path(self, frame: int) -> Path:
        return self._workspace / FRAME_NAME_TEMPLATE.format(frame=frame, ext=self._extension)

    # ------------------------------------------------------------------
    def validate_frame(self, path: Path) -> Dict[str, int]:
        """Dimension check for a candidate frame file (empty dims = unknown).

        When expected dimensions are locked, a mismatch FAILS validation.
        """
        dims = probe_dimensions(path)
        if self._expected_dimensions and dims.get("width") and dims.get("height"):
            if (
                dims["width"] != self._expected_dimensions["width"]
                or dims["height"] != self._expected_dimensions["height"]
            ):
                return {}
        return dims

    def finalize_frame(self, frame: int) -> Optional[FrameEntry]:
        """Atomically move the temp frame to its final name + register it.

        Returns None when the temp file is missing, empty, or fails dimension
        validation — in which case NOTHING is published (cancel-safe, item 4).
        """
        temp = self.temp_path(frame)
        if not temp.is_file():
            return None
        if temp.stat().st_size == 0:
            temp.unlink(missing_ok=True)
            return None
        dims = self.validate_frame(temp)
        if self._expected_dimensions and not dims:
            temp.unlink(missing_ok=True)
            return None
        final = self.final_path(frame)
        os.replace(str(temp), str(final))  # atomic on same filesystem
        entry = FrameEntry(
            frame=frame,
            filename=final.name,
            sha256=sha256_file(final),
            width=dims.get("width", 0),
            height=dims.get("height", 0),
            size_bytes=final.stat().st_size if final.is_file() else 0,
        )
        self._frames[frame] = entry
        self.save()
        return entry

    def discard_temp(self, frame: int) -> None:
        """Remove a half-written temp frame (cancel mid-chunk, item 4)."""
        self.temp_path(frame).unlink(missing_ok=True)

    def manifest_hash(self) -> str:
        """Structural hash of the manifest (determinism item 7)."""
        canonical = json.dumps(
            {
                "frame_range": [self._start, self._end],
                "extension": self._extension,
                "expected_dimensions": self._expected_dimensions,
                "content_hash": self._content_hash,
                "frames": [fe.to_dict() for fe in self.frames],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cancel token (shared with execute_job.py and the supervisor)
# ---------------------------------------------------------------------------
CANCEL_TOKEN_FILENAME = "cancel.token"


def cancel_requested(workspace: Path) -> bool:
    return (workspace / CANCEL_TOKEN_FILENAME).is_file()


__all__ = [
    "FRAME_MANIFEST_FILENAME",
    "TEMP_SUFFIX",
    "FRAME_NAME_TEMPLATE",
    "CANCEL_TOKEN_FILENAME",
    "sha256_file",
    "probe_dimensions",
    "FrameEntry",
    "FrameManifest",
    "cancel_requested",
]
