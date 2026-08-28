#!/usr/bin/env python3
"""probe_dll_load.py - try LoadLibrary on each vendored DLL, print real errors."""
import ctypes
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

D = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apps/desktop/native/recording-engine/target/release",
)
print("dir:", D, "exists:", os.path.isdir(D))
for name in ["libwinpthread-1.dll", "avutil-60.dll", "avcodec-62.dll", "avformat-62.dll"]:
    full = os.path.join(D, name)
    if not os.path.isfile(full):
        print(f"{name}: MISSING")
        continue
    try:
        ctypes.WinDLL(full)
        print(f"{name}: LOADED")
    except OSError as e:
        print(f"{name}: FAIL {e}")
