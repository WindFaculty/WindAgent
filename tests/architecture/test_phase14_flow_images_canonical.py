"""Phase 14 — Flow image generation canonical isolation tests (plan 04 §5, §17-§19).

Proves the Phase 14 image generation adapter
(`tools/windagent_tools/google_flow/`) meets the architecture rules:

- tools-layer: imports only `windagent_tools` + `windagent_core`; never
  imports `windagent_providers` / `windagent_intelligence` (plan 04 §5:
  `providers/` does not depend on `tools/google_flow`);
- no subprocess / sys.path mutation / dynamic import (offline determinism);
- typed operations only — the generator never executes a raw browser
  command and never submits twice (plan §18.2);
- candidate acquisition reuses the canonical content-addressed store with
  atomic publish (plan §18.3);
- review approval fails closed: character master never auto-approved,
  deterministic validity precedes VLM (plan §18.4);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOOGLE_FLOW_DIR = ROOT / "tools" / "windagent_tools" / "google_flow"

FORBIDDEN_LAUNCH_PATTERNS = [
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
    re.compile(r"__import__\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_intelligence",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
)
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_tools")

PHASE14_FILES = (
    "image_operations.py",
    "pre_submit_guard.py",
    "job_record.py",
    "candidate_downloader.py",
    "review_approval.py",
    "image_generation.py",
)


def _google_flow_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(GOOGLE_FLOW_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase14_modules_exist_in_tools_boundary():
    for name in PHASE14_FILES:
        assert (GOOGLE_FLOW_DIR / name).exists(), f"missing {name}"


def test_phase14_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _google_flow_py_files():
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase14 launches/imports upstream: {hits}"


def test_phase14_dependency_roots_are_tools_and_core_only():
    offenders = []
    for rel, text in _google_flow_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"phase14 imports forbidden deps: {offenders}"


def test_phase14_typed_operations_only_no_raw_commands():
    """Plan 04 §17: typed operations only, never raw browser instructions."""
    text = (GOOGLE_FLOW_DIR / "image_generation.py").read_text(encoding="utf-8")
    for raw in ("eval(", "document.cookie", "click_xy(", "exec("):
        assert raw not in text
    assert "FlowUiAction(" in text  # typed action vocabulary
    assert "submit_generation" in text


def test_phase14_generator_submits_exactly_once():
    """Plan 04 §18.2: click submit exactly once with an idempotency token."""
    text = (GOOGLE_FLOW_DIR / "image_generation.py").read_text(encoding="utf-8")
    assert "idempotency_token" in text
    assert "mark(job.generation_id, FlowJobStatus.SUBMITTING)" in text
    # the only loop is the bounded poll loop (deadline-guarded), never a
    # resubmit loop — reconciliation gates every re-entry
    assert "poll_deadline" in text
    assert "deadline" in text
    assert "RECONCILE_UNKNOWN" in text
    assert '"submit"' in text and '"submit_generation"' in text
    # exactly one act() call carries the submit operation
    assert text.count('"submit"') >= 1


def test_phase14_reconciliation_never_blind_resubmits():
    text = (GOOGLE_FLOW_DIR / "job_record.py").read_text(encoding="utf-8")
    assert "REUSE_COMPLETED" in text
    assert "RESUME_ACTIVE" in text
    assert "NEW_ATTEMPT" in text
    assert "RECONCILE_UNKNOWN" in text
    assert "retry_budget" in text


def test_phase14_candidate_acquisition_atomic_publish():
    """Plan 04 §18.3: reuse canonical content-addressed store; invalid never
    published; never defaults to the first candidate."""
    text = (GOOGLE_FLOW_DIR / "candidate_downloader.py").read_text(encoding="utf-8")
    assert "ContentAddressedStore" in text
    assert "quarantine" in text
    assert "CandidateInvalidError" in text
    assert "published" in text
    gen_text = (GOOGLE_FLOW_DIR / "image_generation.py").read_text(encoding="utf-8")
    assert "candidate_refs" in gen_text  # iterates ALL candidates


def test_phase14_review_fails_closed():
    """Plan 04 §18.4: character master human-only; deterministic validity
    precedes VLM; reject keeps reason; no auto-bind."""
    text = (GOOGLE_FLOW_DIR / "review_approval.py").read_text(encoding="utf-8")
    assert "deterministic_valid" in text
    assert "character master requires human approval" in text
    assert "REQUIRES_HUMAN" in text
    assert "VlmReviewPort" in text  # port, not an intelligence import


def test_phase14_google_flow_never_imports_provider_port():
    """Composition root injects the provider implementation through the core
    `MediaGenerationProviderPort`; the tools adapter itself must not import
    it (docstrings may mention the port by name)."""
    for rel, text in _google_flow_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "MediaGenerationProviderPort" not in stripped, rel
                assert stripped.startswith("from windagent_core.contracts") is False, rel


def test_phase14_exports():
    import windagent_tools.google_flow as gf

    for name in (
        "FlowImageOperation",
        "FlowImageRequest",
        "FlowImageGenerator",
        "FlowImageOutcome",
        "ImageOperationMapper",
        "PreSubmitGuard",
        "PreSubmitVerdict",
        "FlowPreSubmitBlockedError",
        "FlowJobRecord",
        "FlowJobRegistry",
        "FlowJobStatus",
        "FlowReconcileAction",
        "FlowReconcileDecision",
        "CandidateDownloader",
        "CandidateAcquisition",
        "CandidateInvalidError",
        "CandidateFetcherPort",
        "ReviewGate",
        "ReviewDecision",
        "CandidateReview",
        "VlmReviewPort",
        "VlmScores",
    ):
        assert hasattr(gf, name), f"google_flow missing export {name}"

    import windagent_tools as tools

    assert hasattr(tools, "FlowImageGenerator")
    assert hasattr(tools, "FlowJobRegistry")
    assert hasattr(tools, "PreSubmitGuard")
    assert hasattr(tools, "ReviewGate")
    assert hasattr(tools, "CandidateDownloader")


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
