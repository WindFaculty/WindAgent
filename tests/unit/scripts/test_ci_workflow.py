from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yaml"
REQUIRED_JOBS = {
    "artifact-protocol",
    "version-consistency",
    "architecture-boundaries",
    "architecture-suite",
    "lint",
    "unit-pure",
    "component-sqlite",
    "contracts",
    "integration-sqlite",
    "postgres-production-semantics",
    "verification-tier",
    "windows-portability",
    "e2e-multiprocess",
    "web-test",
    "web-test-windows",
    "desktop-test",
    "desktop-test-windows",
    "studio-roadmap-gates",
    "p1-e2e-postgres",
    "runtime-smoke",
    "cli-contract",
    "coverage-gate",
    "live-record-client-gate",
    "live-record-native-gate",
}


def _workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _run_text(job: dict) -> str:
    return "\n".join(
        str(step.get("run", ""))
        for step in job.get("steps", [])
        if isinstance(step, dict)
    )


def test_required_jobs_are_direct_children():
    jobs = _workflow()["jobs"]
    assert set(jobs) == REQUIRED_JOBS | {"final-evidence"}
    assert all(isinstance(job, dict) for job in jobs.values())
    assert all(isinstance(job.get("steps"), list) for job in jobs.values())


def test_finalizer_needs_each_required_job_once():
    finalizer = _workflow()["jobs"]["final-evidence"]
    assert len(finalizer["needs"]) == len(set(finalizer["needs"]))
    assert set(finalizer["needs"]) == REQUIRED_JOBS
    assert finalizer["if"] == "always()"


def test_mandatory_gates_do_not_mask_failures():
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "continue-on-error" not in workflow_text
    assert "|| true" not in workflow_text


def test_each_required_job_uploads_evidence():
    jobs = _workflow()["jobs"]
    for name in REQUIRED_JOBS:
        uploads = [
            step
            for step in jobs[name]["steps"]
            if step.get("uses", "").startswith("actions/upload-artifact@")
            and step.get("with", {}).get("name") == f"{name}-evidence"
        ]
        assert len(uploads) == 1, name


def test_artifact_gate_validates_candidate_and_hashes():
    run_text = _run_text(_workflow()["jobs"]["artifact-protocol"])
    assert "generate_phase7_evidence.py" in run_text
    assert "validate_evidence_bundle.py" in run_text
    assert "validate_artifact_schema.py" in run_text
    # The recursive validation is scoped to the CURRENT run's directory
    # (RUN_DIR pins it to ci-<run_id>-<attempt>); committed final/ evidence of
    # other lineages must not block this candidate.
    assert (
        'RUN_DIR="artifacts/architecture_v2_production_hardening/phase_07/runs/ci-'
        in run_text
    )
    assert '--directory "$RUN_DIR"' in run_text
    assert "--recursive" in run_text
    assert "--verify-hashes" in run_text
    assert "--fail-on-warning" in run_text
    assert "--candidate-sha" in run_text
    assert "github.sha" in run_text


def test_postgres_job_has_real_service_without_sqlite_fallback():
    # Check both postgres jobs have real service
    for job_name in ("postgres-production-semantics", "p1-e2e-postgres"):
        job = _workflow()["jobs"][job_name]
        postgres = job["services"]["postgres"]
        assert postgres["image"] == "postgres:16-alpine"
        assert "pg_isready" in postgres["options"]
        assert job["env"]["WINDAGENT_DATABASE_URL"].startswith(
            "postgresql+asyncpg://"
        )
        # Only postgres-production-semantics has the preflight check
        if job_name == "postgres-production-semantics":
            assert "--require-dialect postgresql" in _run_text(job) or "postgres" in _run_text(job).lower()
        assert "sqlite" not in job["env"]["WINDAGENT_DATABASE_URL"].lower()


def test_windows_jobs_use_powershell_only():
    jobs = _workflow()["jobs"]
    for name in (
        "windows-portability",
        "web-test-windows",
        "desktop-test-windows",
    ):
        job = jobs[name]
        # windows-portability and web/desktop windows jobs use pwsh
        assert job.get("defaults", {}).get("run", {}).get("shell") == "pwsh" or job.get("runs-on") == "windows-latest"
        run_text = _run_text(job)
        assert "$(" not in run_text or "pwsh" in str(job.get("defaults", {}))
        assert "&&" not in run_text


def test_frontend_jobs_install_test_typecheck_and_build():
    jobs = _workflow()["jobs"]
    for name in (
        "web-test",
        "web-test-windows",
        "desktop-test",
        "desktop-test-windows",
    ):
        run_text = _run_text(jobs[name])
        assert "npm ci" in run_text or "npm.cmd ci" in run_text
        assert "npm test" in run_text or "npm.cmd test" in run_text or "test:coverage" in run_text
        assert "typecheck" in run_text or "tsc --noEmit" in run_text
        assert "npm run build" in run_text or "npm.cmd run build" in run_text


def test_finalizer_downloads_and_validates_job_receipts():
    finalizer = _workflow()["jobs"]["final-evidence"]
    uses = [step.get("uses", "") for step in finalizer["steps"]]
    run_text = _run_text(finalizer)
    assert any(
        value.startswith("actions/download-artifact@") for value in uses
    )
    assert "validate_ci_evidence.py" in run_text
    assert "github.sha" in run_text
    assert "github.run_id" in run_text
    assert "github.run_attempt" in run_text
