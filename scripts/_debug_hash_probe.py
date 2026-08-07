"""One-off: determine why handoff checksum for contracts/__init__.py changed."""
import hashlib
from pathlib import Path

b = Path("core/windagent_core/contracts/video_production/__init__.py").read_bytes()


def h(x):
    return hashlib.sha256(x).hexdigest()


print("current on-disk:", h(b))
print("target 179ab2dce...:", "179ab2dce8e56793b33c07767c0b8c1286680d39fc193325d1863aea12f0d4f5")
print("current 55f09864...:", "55f09864e4f87e0ca7097a6e7ae95d7d3e246d5ddd2f0c180e5767e2d019a491")
print()
print("CRLF version:", h(b.replace(b"\n", b"\r\n")))
print("current strip trailing:", h(b.rstrip(b"\n") + b"\n"))
print("current no trailing nl:", h(b.rstrip(b"\n")))
print()

# What's in the manifest for this file?
import json

m = json.load(open("artifacts/video_production/handoff/handoff_manifest.json"))
rel = "core/windagent_core/contracts/video_production/__init__.py"
mh = m.get("component_hashes", {}).get(rel)
print("manifest hash:", mh)
# and checksums file
cs = {}
for line in open("artifacts/video_production/handoff/handoff_checksums.sha256", encoding="utf-8").read().splitlines():
    if line.strip():
        digest, _, p = line.strip().partition("  ")
        cs[p] = digest
print("checksums file hash:", cs.get(rel))
