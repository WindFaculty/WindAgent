"""
Deterministic fakes for the asset job runner (VP3D Phase 7, CI).

Fakes mirror the REAL ``BlenderAssetJobRunner`` contract so the whole
pipeline runs in CI without Blender:

- ``import_validate`` reports structural stats from the invocation config;
- ``generate_lod`` produces deterministic LOD payloads AND writes real bytes
  into the output directory (so bundle immutability is exercised end to end);
- ``render_preview`` writes a tiny PNG thumbnail + turntable frames using a
  minimal PNG encoder (no Pillow dependency here).

Every fake is deterministic: identical inputs -> identical hashes.
"""

from __future__ import annotations

import hashlib
import zlib
from pathlib import Path

from windagent_core.domain.video_production.asset_normalization.models import (
    PreviewProfile,
)

from windagent_tools.media_assets.normalization.job_runner import (
    JobInvocation,
    JobResult,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_png(path: Path, *, width: int = 8, height: int = 8, seed: int = 0) -> str:
    """Minimal RGBA PNG writer (deterministic, stdlib-only)."""
    import struct as _struct

    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            v = (x * 31 + y * 17 + seed * 13) % 256
            raw += bytes((v, (v * 3) % 256, (v * 7) % 256, 255))
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            _struct.pack(">I", len(data))
            + tag
            + data
            + _struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = _struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    return _sha256(png)


class FakeAssetJobRunner:
    """Deterministic engine job runner for CI (no Blender needed)."""

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.calls: list[str] = []

    @property
    def available(self) -> bool:
        return self._available

    async def import_validate(self, invocation: JobInvocation) -> JobResult:
        self.calls.append(f"import_validate:{invocation.job_id}")
        config = invocation.config
        if config.get("fail") == "import":
            return JobResult(
                job_id=invocation.job_id,
                kind=invocation.kind,
                ok=False,
                error="fake import rejected the asset (malformed FBX)",
            )
        report = {
            "objects": int(config.get("objects", 1)),
            "triangles": int(config.get("triangles", 0)),
            "vertices": int(config.get("vertices", 0)),
            "materials": int(config.get("materials", 0)),
            "armatures": list(config.get("armatures", [])),
            "animations": list(config.get("animations", [])),
            "non_manifold_edges": int(config.get("non_manifold_edges", 0)),
            "degenerate_faces": int(config.get("degenerate_faces", 0)),
            "unit": config.get("unit", "METERS"),
            "up_axis": config.get("up_axis", "Z_UP"),
            "generated_by": "fake",
        }
        return JobResult(
            job_id=invocation.job_id,
            kind=invocation.kind,
            ok=True,
            report=report,
        )

    async def generate_lod(self, invocation: JobInvocation) -> JobResult:
        self.calls.append(f"generate_lod:{invocation.job_id}")
        config = invocation.config
        level = int(config.get("level", 1))
        target = int(config.get("target_triangles", 0))
        ratio = float(config.get("ratio", 0.5))
        triangles = max(32, int(target * (1.0 - 0.1 * level)))
        out_dir = Path(invocation.output_dir or invocation.workspace)
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = (
            f"lod{level}::tri={triangles}::ratio={ratio}::src={config.get('content_hash', '')}"
        ).encode("utf-8")
        name = f"lod_{level}.glb"
        (out_dir / name).write_bytes(payload)
        report = {
            "triangle_count": triangles,
            "vertex_count": int(triangles * 0.75),
            "content_hash": _sha256(payload),
            "file_name": name,
            "generated_by": "fake",
            "level": level,
        }
        return JobResult(
            job_id=invocation.job_id,
            kind=invocation.kind,
            ok=True,
            report=report,
            generated_files=[str(out_dir / name)],
        )

    async def render_preview(
        self,
        invocation: JobInvocation,
        profile: PreviewProfile,
    ) -> JobResult:
        self.calls.append(f"render_preview:{invocation.job_id}")
        out_dir = Path(invocation.output_dir or invocation.workspace)
        out_dir.mkdir(parents=True, exist_ok=True)
        seed = int(invocation.config.get("content_hash", "0")[:8], 16)
        thumb_name = "thumbnail.png"
        thumb_hash = _write_png(
            out_dir / thumb_name,
            width=profile.width // 8,
            height=profile.height // 8,
            seed=seed,
        )
        frames: list[str] = []
        frame_files: list[str] = []
        for i in range(profile.frames):
            name = f"turntable_{i:04d}.png"
            _write_png(out_dir / name, width=profile.width // 8, height=profile.height // 8, seed=seed + i)
            frames.append(name)
            frame_files.append(str(out_dir / name))
        report = {
            "thumbnail_file": thumb_name,
            "turntable_files": frames,
            "frames_rendered": profile.frames,
            "content_hash": thumb_hash,
            "engine": profile.engine,
            "device": profile.device,
            "generated_by": "fake",
        }
        return JobResult(
            job_id=invocation.job_id,
            kind=invocation.kind,
            ok=True,
            report=report,
            generated_files=[str(out_dir / thumb_name), *frame_files],
        )


__all__ = ["FakeAssetJobRunner"]
