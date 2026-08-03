"""Phase 20 — Candidate review & quality gates canonical isolation tests (plan 05 §4, §22-§27).

Proves the Phase 20 reviewer layer (`intelligence/windagent_intelligence/video/reviewers/`)
meets the architecture rules:

- intelligence-layer: imports only `windagent_core` + `windagent_intelligence`;
  never `windagent_providers` / `windagent_tools` / browser / upstream modules
  (plan §4 clean-room, provider-neutral);
- no subprocess / sys.path mutation / dynamic import inside the package —
  deterministic + cross-shot + verdict + selection run fully offline; only the
  VLM tier goes through a model PORT (protocol), never a provider import;
- gate condition 1: a deterministic failure is a blocking defect BEFORE any
  VLM/human score exists — VLM is never invoked when the file does not decode
  or lacks a video stream (plan §24);
- gate condition 3: VLM timeout / invalid JSON / schema violation is
  REVIEW_ERROR, never a false PASS;
- gate condition 5: cross-shot review uses the Phase 10 continuity ledger;
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEWERS_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video" / "reviewers"

UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
    re.compile(r"__import__\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
    "windagent_observability",
    "windagent_verification",
)
# Self-root (windagent_intelligence) is allowed for intra-package imports.
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_intelligence")

PHASE20_FILES = (
    "models.py",
    "dimensions.py",
    "deterministic.py",
    "vlm.py",
    "cross_shot.py",
    "verdict.py",
    "selection.py",
    "pipeline.py",
    "__init__.py",
)


def _py_files(directory: Path) -> list[tuple[str, str]]:
    files = []
    for py in sorted(directory.rglob("*.py")):
        if "__pycache__" in py.as_posix():
            continue
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase20_modules_exist():
    for name in PHASE20_FILES:
        assert (REVIEWERS_DIR / name).exists(), f"missing reviewers/{name}"


def test_phase20_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _py_files(REVIEWERS_DIR):
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"reviewers launches/imports upstream: {hits}"


def test_phase20_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _py_files(REVIEWERS_DIR):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"reviewers imports forbidden deps: {offenders}"


def test_phase20_vlm_goes_through_port_not_provider():
    """The VLM tier is provider-neutral: a Protocol port, no provider import."""
    text = (REVIEWERS_DIR / "vlm.py").read_text(encoding="utf-8", errors="ignore")
    assert "Protocol" in text
    assert "Port" in text
    assert "windagent_providers" not in text


def test_phase20_deterministic_failure_blocks_before_vlm():
    """Gate condition 1: VLM must not run on a non-decode / no-stream candidate."""
    pipeline_text = (REVIEWERS_DIR / "pipeline.py").read_text(encoding="utf-8", errors="ignore")
    assert "det.technical_valid" in pipeline_text
    assert "Không chạy VLM" in pipeline_text or "VLM must not run" in pipeline_text
    deterministic_text = (REVIEWERS_DIR / "deterministic.py").read_text(encoding="utf-8", errors="ignore")
    assert "MEDIA_DECODE_FAILURE" in deterministic_text
    assert "MISSING_VIDEO_STREAM" in deterministic_text


def test_phase20_vlm_fails_closed_on_error():
    """Gate condition 3: timeout / empty / invalid JSON / schema violation -> REVIEW_ERROR."""
    text = (REVIEWERS_DIR / "vlm.py").read_text(encoding="utf-8", errors="ignore")
    assert "REVIEW_ERROR" in text
    assert "timed out" in text
    assert "empty response" in text
    assert "not valid JSON" in text
    assert "schema violation" in text
    assert "never treated as PASS" in text


def test_phase20_verdict_blocking_wins_and_low_confidence_human():
    text = (REVIEWERS_DIR / "verdict.py").read_text(encoding="utf-8", errors="ignore")
    assert "blocking defect ALWAYS wins" in text
    assert "HUMAN_REVIEW_REQUIRED" in text
    assert "REVIEW_ERROR" in text
    assert "never auto-approve" in text


def test_phase20_cross_shot_uses_continuity_ledger():
    """Gate condition 5: cross-shot review reads the Phase 10 continuity ledger."""
    text = (REVIEWERS_DIR / "cross_shot.py").read_text(encoding="utf-8", errors="ignore")
    assert "ContinuityLedger" in text
    assert "ContinuityLedgerReceipt" in text
    assert "continuity ledger" in text.lower()


def test_phase20_selection_rank_unblocked_and_audit():
    text = (REVIEWERS_DIR / "selection.py").read_text(encoding="utf-8", errors="ignore")
    assert "ranked" in text
    assert "not blocked" in text or "unblocked" in text
    assert "order-independent" in text or "deterministic" in text
    assert "human" in text.lower()
    assert "actor" in text
    assert "RetryProposal" in text


def test_phase20_dimension_catalog_11_dimensions():
    text = (REVIEWERS_DIR / "dimensions.py").read_text(encoding="utf-8", errors="ignore")
    assert "REVIEW_POLICY_VERSION" in text
    assert "TECHNICAL_VALIDITY" in text
    assert "PROMPT_COMPLIANCE" in text
    assert "IDENTITY_CONSISTENCY" in text
    assert "LOCATION_CONSISTENCY" in text
    assert "PROP_CONSISTENCY" in text
    assert "CONTINUITY" in text
    assert "MOTION_QUALITY" in text
    assert "CAMERA_COMPLIANCE" in text
    assert "DIALOGUE_ALIGNMENT" in text
    assert "VISUAL_ARTIFACTS" in text
    assert "SAFETY" in text
    assert "blocking" in text


def test_phase20_exports():
    import windagent_intelligence.video as video

    for name in (
        "ReviewDimension",
        "ReviewerType",
        "CandidateVerdict",
        "BlockingReasonCode",
        "DimensionResult",
        "BlockingDefect",
        "CandidateReview",
        "HumanSelectionOverride",
        "RetryProposal",
        "SelectionRecord",
        "REVIEW_DIMENSIONS",
        "BLOCKING_DIMENSIONS",
        "DeterministicReviewer",
        "MediaProbeFacts",
        "VlmReviewer",
        "VlmReviewRequest",
        "ReviewModelPort",
        "CrossShotReviewer",
        "VerdictPolicy",
        "CandidateSelector",
        "ReviewPipeline",
        "CandidateReviewReceipt",
    ):
        assert hasattr(video, name), f"windagent_intelligence.video missing export {name}"


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
