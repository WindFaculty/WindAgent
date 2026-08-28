#!/usr/bin/env python3
"""vendor_libav.py - Phase 20: vendor the libav runtime DLLs into the Tauri bundle.

Downloads the pinned FFmpeg shared build (BtbN ffmpeg-n8.1 win64 gpl-shared,
family avformat-62 / avcodec-62 / avutil-60 - FAMILIES[0] in muxer/libav_loader.rs),
extracts the five required DLLs, copies them into:

    apps/desktop/src-tauri/resources/libav/          (bundled beside WindAgent.exe)
    apps/desktop/native/recording-engine/target/release/   (dev sidecar runs)

and writes VENDORED.txt (source tag + per-file SHA-256) next to them so the
provenance is auditable without re-downloading.

Idempotent: re-running re-downloads and overwrites.
"""

from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip"
)
SOURCE_TAG = "BtbN/FFmpeg-Builds latest :: ffmpeg-n8.1-latest-win64-gpl-shared-8.1.zip"

DLLS = [
    "avformat-62.dll",
    "avcodec-62.dll",
    "avutil-60.dll",
    "swresample-6.dll",  # transitive loader dependency of avcodec
    "swscale-9.dll",     # transitive loader dependency of avformat
]

REPO = Path(__file__).resolve().parents[2]
DESTS = [
    REPO / "apps/desktop/src-tauri/resources/libav",
    REPO / "apps/desktop/native/recording-engine/target/release",
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    print(f"downloading {URL} ...")
    with urlopen(URL, timeout=600) as resp:
        blob = resp.read()
    print(f"  downloaded {len(blob) / 1048576:.1f} MB")

    extracted: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        members = [n for n in zf.namelist() if n.startswith("bin/") and n.endswith(".dll")]
        wanted = {f"bin/{d}": d for d in DLLS}
        missing = [n for n in wanted if n not in zf.namelist()]
        if missing:
            print(f"error: archive lacks {missing}; has {sorted(members)}", file=sys.stderr)
            return 1
        for arcname, dll in wanted.items():
            extracted[dll] = zf.read(arcname)

    for dest in DESTS:
        dest.mkdir(parents=True, exist_ok=True)
        for dll, data in extracted.items():
            (dest / dll).write_bytes(data)
            print(f"  {dest.name}/{dll}: {len(data) / 1048576:.2f} MB sha256={sha256(data)[:16]}…")

    # Provenance record beside the bundled copies.
    lines = [f"source: {SOURCE_TAG}", ""]
    lines += [f"{dll}  sha256={sha256(data)}" for dll, data in sorted(extracted.items())]
    vendored = DESTS[0] / "VENDORED.txt"
    vendored.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {vendored}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
