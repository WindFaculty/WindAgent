from __future__ import annotations

from pathlib import Path

from scripts.verification.run_negative_injections import build_cases


def test_negative_injection_matrix_covers_all_required_fail_closed_cases(tmp_path):
    root = Path(__file__).parents[2]
    cases = build_cases(root, tmp_path / "output")

    assert {case.name for case in cases} == {
        "version_mismatch",
        "invalid_artifact_schema",
        "broken_artifact_hash",
        "missing_architecture_checker",
        "dirty_worktree",
        "api_worker_version_mismatch",
        "postgresql_unavailable",
        "desktop_lockfile_mismatch",
        "demo_fallback_in_production",
    }
    assert all(
        all(code != 0 for code in case.expected_exit_codes) for case in cases
    )
