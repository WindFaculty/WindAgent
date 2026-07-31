#!/usr/bin/env python3
"""
Tests for the verify-only (--no-write / --verify-only) mode of the Phase 0-5
verifiers: `verify_phase3_protocol.py`, `verify_phase03_handoff.py`,
`verify_phase4_intake.py` and `verify_phase5_characterization.py`.

Contract under test (plan 01, section 26 process note; plan 02 Phase 4/5):
- The verifiers run ALL real checks and compute the verdict, but must NOT
  write/rewrite any evidence artifact, so re-running verification never dirties
  the working tree (no more "refresh regenerated timestamps" churn).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]

VERIFIERS = (
    "scripts/verification/verify_phase3_protocol.py",
    "scripts/verification/verify_phase03_handoff.py",
    "scripts/verification/verify_phase4_intake.py",
    "scripts/verification/verify_phase5_characterization.py",
    "scripts/verification/verify_phase6_kernel.py",
)

KNOWN_EVIDENCE_FILES = (
    "handoff/phase_verdict.json",
    "phase_00/phase_verdict.json",
    "phase_03/phase_verdict.json",
    "phase_04/phase_verdict.json",
    "phase_05/phase_verdict.json",
    "phase_06/phase_verdict.json",
)


def _snapshot_evidence(root: Path) -> dict[str, bytes]:
    """Byte-hash every file under artifacts/video_production/."""
    base = root / "artifacts" / "video_production"
    snapshot: dict[str, bytes] = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            # as_posix() keeps keys platform-independent so KNOWN_EVIDENCE_FILES
            # (forward-slash relative paths) match on Windows too.
            snapshot[path.relative_to(base).as_posix()] = path.read_bytes()
    return snapshot


def _git_porcelain(root: Path) -> list[str]:
    """Working-tree mutation set from git (covers every tracked/untracked path)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(root),
        check=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line.strip())


def _run_verifier(script: str, flag: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, script, flag],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROOT),
    )


def _assert_no_mutation(before: dict[str, bytes], git_before: list[str]) -> None:
    """Verify evidence bytes and the whole working tree are unchanged."""
    assert all(key in before for key in KNOWN_EVIDENCE_FILES), (
        f"evidence snapshot missing required files: "
        f"{sorted(set(KNOWN_EVIDENCE_FILES) - set(before))}"
    )
    assert _snapshot_evidence(ROOT) == before, "verifiers mutated evidence bytes"
    assert _git_porcelain(ROOT) == git_before, (
        "verifiers changed files outside artifacts/video_production/ "
        "(e.g. docs/video_production/protocol/*.schema.json)"
    )


def test_no_write_exits_zero_and_leaves_evidence_untouched():
    """`--no-write` runs real checks, exits 0, and mutates no evidence bytes."""
    before = _snapshot_evidence(ROOT)
    assert before, "evidence snapshot is empty; nothing to verify against"
    git_before = _git_porcelain(ROOT)
    for script in VERIFIERS:
        result = _run_verifier(script, "--no-write")
        assert result.returncode == 0, f"{script} --no-write failed: {result.stdout + result.stderr}"
        assert "PASSED" in result.stdout, f"{script} did not report a PASSED verdict"
    _assert_no_mutation(before, git_before)


def test_verify_only_alias_exits_zero_and_leaves_evidence_untouched():
    """`--verify-only` is an alias for `--no-write` with the same contract."""
    before = _snapshot_evidence(ROOT)
    assert before, "evidence snapshot is empty; nothing to verify against"
    git_before = _git_porcelain(ROOT)
    for script in VERIFIERS:
        result = _run_verifier(script, "--verify-only")
        assert result.returncode == 0, f"{script} --verify-only failed: {result.stdout + result.stderr}"
    _assert_no_mutation(before, git_before)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
