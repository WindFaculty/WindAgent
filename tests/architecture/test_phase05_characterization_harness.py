"""Phase 5 - VideoClaw characterization harness isolation tests (plan 02).

Proves the harness isolation requirements of plan 02 Section 12.1/16.5:
- The upstream snapshot is only *launched/imported* via the dedicated probe
  subprocess (scripts/verification/phase5_upstream_probe.py), never from
  canonical code. Merely *mentioning* the upstream in a docstring/comment, or
  referencing the quarantine for enforcement/verification (e.g. the
  check_architecture_imports.py rule, the phase 3/4 verifiers, the negative
  fixtures in test_phase04_videoclaw_quarantine.py) is legitimate and allowed;
- The three golden fixtures are complete (brief / responses / manifest).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Real launch/import mechanisms that would actually execute the quarantined
# upstream code: imports of the vendored package, sys.path manipulation
# pointing at it, importlib loading from it, or subprocess launches of the
# probe. Anything else (keyword mention in prose, reading the manifest for an
# integrity check) does not execute upstream.
LAUNCH_OR_IMPORT_PATTERNS = [
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\([^)]*third_party", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\([^)]*videoclaw", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\([^)]*videoclaw", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call)\s*\([^)]*phase5_upstream_probe", re.MULTILINE),
]

# Directories that are part of the harness/verification zone: the probe, the
# phase 5 verifier, all verifier scripts (which check quarantine integrity), the
# architecture enforcer (which detects quarantine violations) and the test suite.
ALLOWED_LAUNCH_ZONES = (
    "scripts/verification/",
    "tests/",
    "scripts/check_architecture_imports.py",
)

CANONICAL_ROOTS = (
    "apps",
    "core",
    "orchestration",
    "intelligence",
    "providers",
    "tools",
    "workflows",
    "verification",
    "context",
    "memory",
    "execution",
    "storage",
    "observability",
    "evals",
    "plugins",
    "skills",
)


def _launches_upstream(text: str) -> bool:
    return any(pattern.search(text) for pattern in LAUNCH_OR_IMPORT_PATTERNS)


def test_probe_is_the_only_upstream_launcher():
    """No canonical package may import/launch the quarantined upstream tree.

    Docstring/comment mentions of upstream names or `third_party` are allowed;
    actual import statements, sys.path poisoning, importlib loading or
    subprocess launches are not.
    """
    hits = []
    for root in CANONICAL_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            if ".venv" in py.parts or "__pycache__" in py.parts:
                continue
            rel = py.relative_to(ROOT).as_posix()
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _launches_upstream(text):
                hits.append(rel)
    assert hits == [], f"canonical packages import/launch upstream: {hits}"


def test_upstream_references_are_confined_to_harness_zone():
    """Non-harness files (outside scripts/verification + tests) must not launch
    or import the quarantined upstream."""
    offenders = []
    for py in ROOT.rglob("*.py"):
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        if "third_party" in py.parts:
            continue
        rel = py.relative_to(ROOT).as_posix()
        if rel.startswith(ALLOWED_LAUNCH_ZONES):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _launches_upstream(text):
            offenders.append(rel)
    assert offenders == [], f"upstream launched/imported outside harness zone: {offenders}"


def test_probe_blocks_network_and_heavy_deps():
    """The probe must stub config/models providers so no network or heavy SDK
    is ever imported when characterizing upstream pure functions."""
    text = (ROOT / "scripts" / "verification" / "phase5_upstream_probe.py").read_text(
        encoding="utf-8"
    )
    assert "Network/model access is blocked" in text
    assert "sys.modules[name] = stub" in text
    assert "tempfile.mkdtemp" in text


def test_golden_fixtures_are_complete():
    """Each of the three golden fixtures carries brief / responses / manifest."""
    fixtures_dir = (
        ROOT / "tests" / "fixtures" / "video_production"
        / "videoclaw_characterization"
    )
    ids = ("fixture_short_cartoon", "fixture_two_character_dialogue", "fixture_multi_scene_drama")
    for fx_id in ids:
        base = fixtures_dir / fx_id
        for required in ("brief.json", "provider_responses.json", "manifest.json"):
            assert (base / required).is_file(), f"{fx_id}/{required} missing"
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        for field in ("capability_path", "canonicalization_policy",
                      "expected_stable_fields", "allowed_variation",
                      "known_defect_references"):
            assert field in manifest, f"{fx_id} manifest missing {field}"
        responses = json.loads((base / "provider_responses.json").read_text(encoding="utf-8"))
        for key in ("generate_script", "meta_extract", "act_extract"):
            assert key in responses, f"{fx_id} responses missing {key}"


def test_real_repo_architecture_stays_clean():
    """The real workspace's architecture check must report zero violations
    including the Phase 4 videoclaw quarantine rule."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
