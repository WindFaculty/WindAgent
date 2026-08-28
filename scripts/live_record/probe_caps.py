#!/usr/bin/env python3
"""probe_caps.py - one capabilities call, blockers printed verbatim."""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BIN = Path(__file__).resolve().parents[2] / (
    "apps/desktop/native/recording-engine/target/release/windagent-recorder.exe"
)

p = subprocess.Popen(
    [str(BIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
)
p.stdin.write(b'{"op":"capabilities"}\n')
p.stdin.flush()
time.sleep(3)
p.stdin.close()
try:
    p.wait(timeout=15)
except subprocess.TimeoutExpired:
    p.kill()

for line in p.stdout.read().decode("utf-8", "replace").splitlines():
    v = json.loads(line)
    if "resp" not in v:
        continue
    pl = v.get("payload", {})
    for k in sorted(pl):
        print(f"{k:22s} = {pl[k]}")
