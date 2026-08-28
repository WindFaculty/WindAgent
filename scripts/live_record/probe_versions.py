#!/usr/bin/env python3
"""probe_versions.py - call av*_version() directly, print raw ints."""
import ctypes
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apps/desktop/native/recording-engine/target/release",
)
os.add_dll_directory(D)

for dll, fn in [
    ("avutil-60.dll", "avutil_version"),
    ("avcodec-62.dll", "avcodec_version"),
    ("avformat-62.dll", "avformat_version"),
]:
    lib = ctypes.WinDLL(os.path.join(D, dll))
    f = getattr(lib, fn)
    f.restype = ctypes.c_uint
    v = f()
    print(f"{dll:20s} {fn} = {v} (0x{v:08X}) -> major>>20={v >> 20}, "
          f"minor={(v >> 12) & 0xFF}, micro={v & 0xFFF}")
