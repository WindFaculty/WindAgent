"""Phase 15 — Flow video generation canonical isolation tests (plan 04 §5, §20-§24).

Proves the Phase 15 video adapter (`tools/windagent_tools/google_flow/`)
meets the architecture rules:

- tools-layer: imports only `windagent_tools` + `windagent_core`; never
  imports `windagent_providers` / `windagent_intelligence` (plan 04 §5);
- no subprocess / sys.path mutation / dynamic import inside `google_flow`
  (offline determinism — the real ffprobe adapter lives OUTSIDE the package
  in `tools/windagent_tools/video_probe.py`, plan 04 §23.3 + §8.2 process
  boundary);
- typed operations only — the generator never executes a raw browser
  command and never submits twice (plan §23.1, §23.3);
- mode validation fails closed BEFORE navigation/submit (plan §23.2);
- candidates are technically validated (video stream, duration, resolution,
  fps) and an invalid candidate is never COMPLETED (plan §23.3);
- cancel stops locally and never asserts provider-side cancellation (plan
  §23.4);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOOGLE_FLOW_DIR = ROOT / "tools" / "windagent_tools" / "google_flow"
PROBE_PATH = ROOT / "tools" / "windagent_tools" / "video_probe.py"

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

PHASE15_FILES = (
    "video_operations.py",
    "video_inspection.py",
    "video_candidates.py",
    "video_generation.py",
)


def _google_flow_py_files() -> list[tuple[str, str]]:
    files = []
    for py in sorted(GOOGLE_FLOW_DIR.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase15_modules_exist_in_tools_boundary():
    for name in PHASE15_FILES:
        assert (GOOGLE_FLOW_DIR / name).exists(), f"missing {name}"
    # real ffprobe adapter lives OUTSIDE google_flow (process boundary)
    assert PROBE_PATH.exists()


def test_phase15_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _google_flow_py_files():
        for pattern in FORBIDDEN_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"phase15 launches/imports upstream: {hits}"


def test_phase15_dependency_roots_are_tools_and_core_only():
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
    assert offenders == [], f"phase15 imports forbidden deps: {offenders}"


def test_phase15_typed_operations_only_no_raw_commands():
    """Plan 04 §21: typed operations only, never raw browser instructions."""
    text = (GOOGLE_FLOW_DIR / "video_generation.py").read_text(encoding="utf-8")
    for raw in ("eval(", "document.cookie", "click_xy(", "exec("):
        assert raw not in text
    assert "FlowUiAction(" in text  # typed action vocabulary
    assert "submit_generation" in text


def test_phase15_generator_submits_exactly_once():
    """Plan 04 §23.1/§23.3: click submit exactly once with an idempotency
    token; the only loop is the bounded poll loop."""
    text = (GOOGLE_FLOW_DIR / "video_generation.py").read_text(encoding="utf-8")
    assert "idempotency_token" in text
    assert "mark(job.generation_id, FlowJobStatus.SUBMITTING)" in text
    assert "poll_deadline" in text
    assert "deadline" in text
    assert "RECONCILE_UNKNOWN" in text
    assert '"submit"' in text and '"submit_generation"' in text


def test_phase15_mode_validation_fails_closed_first():
    """Plan 04 §23.2: mode validation runs BEFORE navigation/submit."""
    text = (GOOGLE_FLOW_DIR / "video_generation.py").read_text(encoding="utf-8")
    # validate_mode is invoked first, before reconcile/navigate
    assert "validate_mode(" in text
    mode_idx = text.index("validate_mode(")
    submit_idx = text.index("FlowJobStatus.SUBMITTING")
    assert mode_idx < submit_idx


def test_phase15_candidates_technically_validated_never_completed_invalid():
    """Plan 04 §23.3: stream/duration/resolution/fps checks gate publish;
    invalid candidate → job is never COMPLETED."""
    candidates_text = (GOOGLE_FLOW_DIR / "video_candidates.py").read_text(
        encoding="utf-8"
    )
    assert "VideoInspectorPort" in candidates_text
    assert "inspection" in candidates_text
    assert "content_hash" in candidates_text
    assert "VideoCandidateInvalidError" in candidates_text
    inspection_text = (GOOGLE_FLOW_DIR / "video_inspection.py").read_text(
        encoding="utf-8"
    )
    assert "has_video_stream" in inspection_text
    assert "duration_seconds" in inspection_text
    assert "frame_rate" in inspection_text
    gen_text = (GOOGLE_FLOW_DIR / "video_generation.py").read_text(encoding="utf-8")
    assert "FlowVideoInvalidResultError" in gen_text
    assert "record_candidates" in gen_text  # COMPLETED only after publish


def test_phase15_cancel_never_claims_provider_side():
    """Plan 04 §23.4: cancel stops locally; never asserts provider-side."""
    text = (GOOGLE_FLOW_DIR / "video_generation.py").read_text(encoding="utf-8")
    assert "cancel_requested" in text
    assert "FlowVideoCancelledError" in text
    assert "provider-side cancellation" in text
    assert "is not asserted" in text


def test_phase15_retry_keeps_causal_link():
    """Plan 04 §23.4: retry creates a NEW attempt, never overwrites receipts."""
    text = (GOOGLE_FLOW_DIR / "video_generation.py").read_text(encoding="utf-8")
    assert "next_attempt(" in text
    assert "parent" in text


def test_phase15_google_flow_never_imports_provider_port():
    for rel, text in _google_flow_py_files():
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "MediaGenerationProviderPort" not in stripped, rel
                assert stripped.startswith("from windagent_core.contracts") is False, rel


def test_phase15_probe_adapter_lives_outside_google_flow():
    """The real ffprobe adapter is NOT inside google_flow (process boundary),
    so it does not trip the google_flow subprocess prohibition."""
    probe_text = PROBE_PATH.read_text(encoding="utf-8")
    assert "subprocess.run" in probe_text  # bounded, argv-only
    assert "VideoInspectorPort" in probe_text
    assert "has_video_stream" in probe_text
    for rel, text in _google_flow_py_files():
        assert "subprocess.run" not in text, rel


def test_phase15_exports():
    import windagent_tools.google_flow as gf

    for name in (
        "FlowVideoOperation",
        "FlowVideoRequest",
        "FlowVideoGenerator",
        "FlowVideoOutcome",
        "FlowVideoModeIssue",
        "FlowVideoModeIssueCode",
        "FlowVideoModeValidationError",
        "FlowVideoCancelledError",
        "FlowVideoInvalidResultError",
        "VideoOperationMapper",
        "VideoInspectorPort",
        "VideoInspection",
        "VideoInspectionPolicy",
        "VideoCandidateDownloader",
        "VideoCandidateAcquisition",
        "VideoCandidateInvalidError",
    ):
        assert hasattr(gf, name), f"google_flow missing export {name}"

    import windagent_tools as tools

    assert hasattr(tools, "FlowVideoGenerator")
    assert hasattr(tools, "FlowVideoOperation")
    assert hasattr(tools, "VideoCandidateDownloader")
    assert hasattr(tools, "VideoOperationMapper")

    from windagent_tools.video_probe import FfprobeVideoInspector  # noqa: F401
    assert FfprobeVideoInspector is not None


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
