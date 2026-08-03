#!/usr/bin/env python3
"""
Phase 15 verification — VP15_FLOW_VIDEO_GENERATION_VERIFIED (plan 04 §20-§24).

Verifies the video generation adapter (`tools/windagent_tools/google_flow/`)
against the ratified contracts in `docs/video_production/flow_video/`:

  artifacts/video_production/phase_15/
  ├── video_operations_receipt.json     (5 typed operations, plan §21)
  ├── video_mode_validation_receipt.json (mode matrix fail closed, §23.2)
  ├── video_idempotency_receipt.json    (failure matrix, no dup submit, §23.1)
  ├── video_technical_validation_receipt.json (stream/duration/res/fps, §23.3)
  ├── video_cancel_retry_receipt.json   (local cancel, causal retry, §23.4)
  └── phase_verdict.json

Gate conditions (plan 04 §24):
  1. no duplicate submit across the failure matrix (crash before/during/
     after submit intent, repeated command, existing job);
  2. job/artifact trace complete — COMPLETED only after atomic publish;
  3. video candidates pass technical validation (stream, duration,
     resolution, frame rate).

Every check is offline and deterministic — the real ffprobe adapter
(`windagent_tools.video_probe`) is NOT required; a fake `VideoInspectorPort`
is injected. Supports --no-write / --verify-only.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_15"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_tools.google_flow import (  # noqa: E402
    FlowJobRegistry,
    FlowJobStatus,
    FlowNavigationReceipt,
    FlowProjectManager,
    FlowReconcileAction,
    FlowUiAction,
    FlowUiObservation,
    FlowUiState,
    FlowVideoCancelledError,
    FlowVideoGenerator,
    FlowVideoInvalidResultError,
    FlowVideoModeIssueCode,
    FlowVideoModeValidationError,
    FlowVideoOperation,
    FlowVideoRequest,
    PreSubmitGuard,
    VideoCandidateDownloader,
    VideoInspection,
    VideoInspectionPolicy,
    VideoInspectorPort,
    VideoOperationMapper,
)
from windagent_tools.media_assets.store import ContentAddressedStore  # noqa: E402

HASH_OK = "b" * 64
HASH_OK2 = "c" * 64
HASH_OK3 = "d" * 64
HASH_OK4 = "e" * 64


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(checks: list[dict], check: str, ok: bool, detail: str) -> None:
    checks.append({"check": check, "ok": bool(ok), "detail": detail})


def _request(**overrides) -> FlowVideoRequest:
    base = dict(
        operation=FlowVideoOperation.TEXT_TO_VIDEO,
        request_hash=HASH_OK,
        project_id="vp_1",
        revision_id="rev_1",
        shot_id="shot_1",
        prompt="a slow pan across a valley",
        duration_seconds=4.0,
        aspect_ratio="16:9",
        model="video_model_0.1",
        candidate_limit=1,
    )
    base.update(overrides)
    return FlowVideoRequest(**base)


# ---------------------------------------------------------------------------
# Fakes (deterministic, offline — no ffprobe required)
# ---------------------------------------------------------------------------
class FakeUi:
    def __init__(self, script: list[FlowUiObservation]) -> None:
        self.script = script
        self.index = 0
        self.pending_advance = False
        self.actions: list[str] = []

    async def observe(self) -> FlowUiObservation:
        if self.pending_advance:
            self.pending_advance = False
            self.index = min(self.index + 1, len(self.script) - 1)
        return self.script[self.index]

    async def act(self, action: FlowUiAction) -> str:
        self.actions.append(action.operation)
        self.pending_advance = True
        return "ev_" + action.operation


class FakeNavigator:
    async def navigate_to_submit_ready(self) -> FlowNavigationReceipt:
        return FlowNavigationReceipt(
            session_id="sess_15",
            project_id="vp_1",
            target_state=FlowUiState.SUBMIT_READY,
            reached_state=FlowUiState.SUBMIT_READY,
            pre_submit_evidence_hash="pre-evidence-15",
        )


class FakeFetcher:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    async def fetch(self, uri: str) -> bytes:
        return self.payloads[uri]


class FakeInspector(VideoInspectorPort):
    """Deterministic inspector: mp4-magic prefix → valid stream, else none."""

    def __init__(self, valid: bool = True) -> None:
        self.valid = valid

    def inspect(self, data: bytes) -> VideoInspection:
        if not self.valid or not data.startswith(b"\x00\x00\x00\x18ftyp"):
            return VideoInspection(has_video_stream=False)
        return VideoInspection(
            has_video_stream=True,
            duration_seconds=4.0,
            width=1280,
            height=720,
            frame_rate=24.0,
            container="mp4",
            codec="h264",
        )


class ShortInspector(FakeInspector):
    def inspect(self, data: bytes) -> VideoInspection:
        base = super().inspect(data)
        if not base.has_video_stream:
            return base
        return VideoInspection(
            has_video_stream=True, duration_seconds=0.01,
            width=1280, height=720, frame_rate=24.0,
            container="mp4", codec="h264",
        )


def _video_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _video_bytes_variant(seed: int) -> bytes:
    # distinct payload so the content-addressed store keeps two artifacts
    return b"\x00\x00\x00\x18ftypmp42" + bytes([seed & 0xFF]) * 64


def _happy_script(refs: tuple[str, ...] = ("candidate:res://clip.mp4",)):
    return [
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Result", *refs), controls=("button:Download",),
        ),
    ]


def _workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="phase15_"))


def _generator(workspace: Path, *, ui=None, fetcher=None, inspector=None,
               mapper=None, cancel_requested=None,
               approved_hashes=frozenset({HASH_OK})):
    store = ContentAddressedStore(workspace / "store")
    downloader = VideoCandidateDownloader(
        quarantine_dir=str(workspace / "quarantine"),
        store=store, inspector=inspector or FakeInspector(),
    )
    pm = FlowProjectManager(state_dir=str(workspace), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1", production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    return FlowVideoGenerator(
        session_id="sess_15", project_id="vp_1",
        ui=ui or FakeUi(_happy_script()),
        navigator=FakeNavigator(), project_manager=pm,
        project_mapping=mapping,
        guard=PreSubmitGuard(mapper=mapper or VideoOperationMapper()),
        job_registry=registry, downloader=downloader,
        fetcher=fetcher or FakeFetcher({"res://clip.mp4": _video_bytes()}),
        mapper=mapper, approved_hashes=approved_hashes,
        cancel_requested=cancel_requested,
    )


# ---------------------------------------------------------------------------
# 1. Video operations receipt (plan §21)
# ---------------------------------------------------------------------------
def build_video_operations_receipt() -> dict:
    checks: list[dict] = []
    mapper = VideoOperationMapper()

    ops = {op.value for op in FlowVideoOperation}
    _record(checks, "exactly_five_video_operations", len(ops) == 5,
            f"operations={sorted(ops)}")

    actions = mapper.configuration_actions(_request())
    _record(checks, "typed_actions_only",
            all(isinstance(a, FlowUiAction) for a in actions)
            and all(a.operation in ("select", "fill", "upload") for a in actions),
            f"config_steps={len(actions)}")

    _record(checks, "reference_policy",
            mapper.requires_reference(FlowVideoOperation.FRAMES_TO_VIDEO)
            and mapper.requires_reference(FlowVideoOperation.VIDEO_TO_VIDEO)
            and not mapper.requires_reference(FlowVideoOperation.TEXT_TO_VIDEO),
            "reference-required ops per §23.2")

    _record(checks, "source_clip_policy",
            mapper.requires_source_image(FlowVideoOperation.VIDEO_EXTENSION)
            and mapper.requires_source_image(FlowVideoOperation.VIDEO_TO_VIDEO)
            and not mapper.requires_source_image(FlowVideoOperation.TEXT_TO_VIDEO),
            "extension/v2v consume an approved source clip")

    _record(checks, "capability_fails_closed",
            not VideoOperationMapper(
                capability=(FlowVideoOperation.TEXT_TO_VIDEO,)
            ).supported(FlowVideoOperation.VIDEO_TO_VIDEO),
            "unsupported operation denied")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_video/video_operations_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 2. Mode validation receipt (plan §23.2)
# ---------------------------------------------------------------------------
def build_video_mode_validation_receipt() -> dict:
    checks: list[dict] = []
    mapper = VideoOperationMapper()
    approved = frozenset({HASH_OK})

    def codes(request) -> list[FlowVideoModeIssueCode]:
        return sorted(i.code for i in mapper.validate_mode(
            request, approved_hashes=approved
        ))

    _record(checks, "text_to_video_clean",
            codes(_request()) == [],
            "TEXT_TO_VIDEO requires no bindings")

    frames_bad = codes(_request(
        operation=FlowVideoOperation.FRAMES_TO_VIDEO,
        reference_bindings=(("FIRST_FRAME", HASH_OK2),),
    ))
    _record(checks, "frames_requires_last_frame",
            FlowVideoModeIssueCode.MISSING_LAST_FRAME in frames_bad,
            f"codes={[c.value for c in frames_bad]}")

    frames_ok = codes(_request(
        operation=FlowVideoOperation.FRAMES_TO_VIDEO,
        reference_bindings=(("FIRST_FRAME", HASH_OK), ("LAST_FRAME", HASH_OK)),
    ))
    _record(checks, "frames_approved_clean",
            frames_ok == [],
            f"codes={[c.value for c in frames_ok]}")

    ingr_bad = codes(_request(
        operation=FlowVideoOperation.INGREDIENTS_TO_VIDEO,
        reference_bindings=(("INGREDIENT", HASH_OK3),),
    ))
    _record(checks, "ingredients_unapproved_blocked",
            FlowVideoModeIssueCode.INGREDIENT_NOT_APPROVED in ingr_bad,
            f"codes={[c.value for c in ingr_bad]}")

    ext_bad = codes(_request(
        operation=FlowVideoOperation.VIDEO_EXTENSION,
        reference_bindings=(("PREDECESSOR_CLIP", HASH_OK),),
        continuity_state="",
    ))
    _record(checks, "extension_continuity_required",
            FlowVideoModeIssueCode.CONTINUITY_NOT_READY in ext_bad,
            f"codes={[c.value for c in ext_bad]}")

    v2v_bad = codes(_request(
        operation=FlowVideoOperation.VIDEO_TO_VIDEO,
        reference_bindings=(("SOURCE_CLIP", HASH_OK),),
        transformation_intent="",
    ))
    _record(checks, "v2v_transformation_intent_required",
            FlowVideoModeIssueCode.TRANSFORMATION_INTENT_MISSING in v2v_bad,
            f"codes={[c.value for c in v2v_bad]}")

    _record(checks, "duration_policy",
            FlowVideoModeIssueCode.DURATION_OUT_OF_POLICY
            in codes(_request(duration_seconds=0.2)),
            "duration outside policy blocked")

    _record(checks, "aspect_policy",
            FlowVideoModeIssueCode.ASPECT_RATIO_UNSUPPORTED
            in codes(_request(aspect_ratio="2:3")),
            "unsupported aspect ratio blocked")

    _record(checks, "model_policy",
            FlowVideoModeIssueCode.MODEL_UNSUPPORTED
            in codes(_request(model="unknown-model")),
            "unsupported model blocked")

    # end-to-end: generator blocks BEFORE submit on mode failure
    workspace = _workspace()
    ui = FakeUi(_happy_script())
    gen = _generator(workspace, ui=ui)
    blocked = False
    try:
        asyncio.run(gen.generate_video(_request(
            operation=FlowVideoOperation.FRAMES_TO_VIDEO,
            reference_bindings=(),
        )))
    except FlowVideoModeValidationError:
        blocked = True
    _record(checks, "generator_blocks_before_submit",
            blocked and ui.actions == [],
            f"actions={ui.actions} (must be empty)")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_video/video_mode_validation.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Idempotency receipt (plan §23.1)
# ---------------------------------------------------------------------------
def build_video_idempotency_receipt() -> dict:
    checks: list[dict] = []
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    key = dict(request_hash=HASH_OK, project_id="vp_1",
               provider="google_flow_browser")

    _record(checks, "missing_job_creates_prepared",
            registry.reconcile(**key).action
            == FlowReconcileAction.CREATE_PREPARED,
            "no prior job → CREATE_PREPARED")

    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK,
    )
    registry.record_candidates("gen_1", ["gen_1c0"])
    decision = registry.reconcile(**key)
    _record(checks, "completed_job_reused",
            decision.action == FlowReconcileAction.REUSE_COMPLETED,
            "COMPLETED → reuse candidate set (no resubmit)")

    registry.mark("gen_1", FlowJobStatus.GENERATING)
    decision = registry.reconcile(**key)
    _record(checks, "active_job_resumed",
            decision.action == FlowReconcileAction.RESUME_ACTIVE,
            "active job → inspect/resume")

    registry.mark("gen_1", FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION)
    decision = registry.reconcile(**key)
    _record(checks, "unknown_job_reconciles",
            decision.action == FlowReconcileAction.RECONCILE_UNKNOWN,
            "UNKNOWN → reconcile (never blind resubmit)")

    registry.mark("gen_1", FlowJobStatus.FAILED_RETRYABLE)
    decision = registry.reconcile(**key)
    _record(checks, "retryable_failure_new_attempt",
            decision.action == FlowReconcileAction.NEW_ATTEMPT,
            f"attempt={decision.record.attempt if decision.record else '?'}")

    attempt = registry.next_attempt("gen_1")
    _record(checks, "next_attempt_keeps_causal_link",
            attempt.attempt == 2 and attempt.parent_generation_id == "gen_1",
            f"attempt={attempt.attempt} parent={attempt.parent_generation_id}")

    # end-to-end: repeated command with same request hash → no duplicate
    # submit. Uses a DISTINCT request hash (HASH_OK3) so the registry matrix
    # above (which left a PREPARED gen_1a2 record for HASH_OK) cannot make the
    # end-to-end run reconcile to RECONCILE_UNKNOWN.
    gen = _generator(workspace, fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out1 = asyncio.run(gen.generate_video(_request(request_hash=HASH_OK3)))
    _record(checks, "first_command_submits_once",
            out1.submit_clicked and len(out1.candidates) == 1,
            f"candidates={len(out1.candidates)}")

    ui2 = FakeUi(_happy_script())
    gen2 = _generator(workspace, ui=ui2,
                      fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out2 = asyncio.run(gen2.generate_video(_request(request_hash=HASH_OK3)))
    _record(checks, "duplicate_command_no_resubmit",
            out2.submit_clicked is False and ui2.actions == [],
            "completed job reused — no duplicate submit")

    # browser close after submit → re-inspection of the SAME project
    workspace3 = _workspace()
    reg3 = FlowJobRegistry(state_dir=str(workspace3), clock=time.time)
    reg3.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK2,
    )
    reg3.mark("gen_1", FlowJobStatus.GENERATING)
    ui3 = FakeUi(_happy_script())
    gen3 = _generator(workspace3, ui=ui3,
                      fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out3 = asyncio.run(gen3.generate_video(_request(request_hash=HASH_OK2)))
    _record(checks, "browser_close_resumes_same_project",
            out3.submit_clicked is False and ui3.actions == [],
            "active job re-inspected, no resubmit")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_video/video_job_idempotency.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Technical validation receipt (plan §23.3)
# ---------------------------------------------------------------------------
def build_video_technical_validation_receipt() -> dict:
    checks: list[dict] = []
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")

    policy = VideoInspectionPolicy()
    valid = VideoInspection(
        has_video_stream=True, duration_seconds=4.0,
        width=1280, height=720, frame_rate=24.0, container="mp4", codec="h264",
    )
    no_stream = VideoInspection(has_video_stream=False)
    _record(checks, "policy_accepts_valid",
            policy.violations(valid) == (),
            f"violations={policy.violations(valid)}")
    _record(checks, "policy_rejects_no_stream",
            "no video stream detected" in policy.violations(no_stream),
            f"violations={policy.violations(no_stream)}")

    short = VideoInspection(
        has_video_stream=True, duration_seconds=0.01,
        width=1280, height=720, frame_rate=24.0, container="mp4",
    )
    _record(checks, "policy_rejects_short_duration",
            any("below min" in v for v in policy.violations(short)),
            f"violations={policy.violations(short)}")

    tiny = VideoInspection(
        has_video_stream=True, duration_seconds=4.0,
        width=32, height=32, frame_rate=24.0, container="mp4",
    )
    _record(checks, "policy_rejects_tiny_resolution",
            any("resolution" in v for v in policy.violations(tiny)),
            f"violations={policy.violations(tiny)}")

    # end-to-end: valid candidate published + COMPLETED
    gen = _generator(workspace, fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out = asyncio.run(gen.generate_video(_request()))
    _record(checks, "valid_candidate_published_completed",
            out.ok and out.job.status == FlowJobStatus.COMPLETED
            and len(store.list_hashes()) == 1,
            f"status={out.job.status.value} store_hashes={store.list_hashes()}")

    # invalid (no stream) candidate → job FAILED_TERMINAL, store clean
    workspace2 = _workspace()
    store2 = ContentAddressedStore(workspace2 / "store")
    gen2 = _generator(
        workspace2,
        fetcher=FakeFetcher({"res://clip.mp4": b"not a video"}),
        inspector=FakeInspector(valid=False),
    )
    rejected = False
    try:
        asyncio.run(gen2.generate_video(_request(request_hash=HASH_OK3)))
    except FlowVideoInvalidResultError:
        rejected = True
    _record(checks, "invalid_candidate_never_completed",
            rejected and len(store2.list_hashes()) == 0,
            f"store_hashes={store2.list_hashes()} (must be empty)")

    # zero-byte candidate rejected, store clean
    workspace3 = _workspace()
    store3 = ContentAddressedStore(workspace3 / "store")
    gen3 = _generator(
        workspace3, fetcher=FakeFetcher({"res://clip.mp4": b""}),
        inspector=FakeInspector(valid=True),
    )
    zero_rejected = False
    try:
        asyncio.run(gen3.generate_video(_request(request_hash=HASH_OK4)))
    except FlowVideoInvalidResultError:
        zero_rejected = True
    _record(checks, "zero_byte_candidate_rejected",
            zero_rejected and len(store3.list_hashes()) == 0,
            f"store_hashes={store3.list_hashes()} (must be empty)")

    # multi-candidate: every candidate acquired
    workspace4 = _workspace()
    store4 = ContentAddressedStore(workspace4 / "store")
    refs = ("candidate:res://a.mp4", "candidate:res://b.mp4")
    ui4 = FakeUi(_happy_script(refs))
    gen4 = _generator(
        workspace4, ui=ui4,
        fetcher=FakeFetcher({"res://a.mp4": _video_bytes(),
                             "res://b.mp4": _video_bytes_variant(9)}),
    )
    out4 = asyncio.run(gen4.generate_video(
        _request(request_hash=HASH_OK2, candidate_limit=2)
    ))
    _record(checks, "all_candidates_acquired",
            len(out4.candidates) == 2 and len(store4.list_hashes()) == 2,
            f"candidates={len(out4.candidates)} store_hashes={store4.list_hashes()}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_video/video_technical_validation.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 5. Cancel / retry receipt (plan §23.4)
# ---------------------------------------------------------------------------
def build_video_cancel_retry_receipt() -> dict:
    checks: list[dict] = []
    workspace = _workspace()

    cancelled = {"flag": False}

    def cancel_now() -> bool:
        return cancelled["flag"]

    ui = FakeUi([
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",), controls=(),
        ),
    ])
    gen = _generator(
        workspace, ui=ui, cancel_requested=cancel_now,
        fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}),
    )
    cancelled["flag"] = True
    msg = ""
    try:
        asyncio.run(gen.generate_video(_request()))
    except FlowVideoCancelledError as exc:
        msg = str(exc)
    _record(checks, "cancel_stops_poll_locally",
            "provider-side" in msg and "not asserted" in msg,
            "cancel never claims provider-side cancellation")
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    latest = registry.list_records()[-1]
    _record(checks, "cancel_marks_cancelled",
            latest.status == FlowJobStatus.CANCELLED,
            f"status={latest.status.value}")

    # cancel before submit → no action at all
    ui2 = FakeUi(_happy_script())
    gen2 = _generator(
        workspace, ui=ui2, cancel_requested=lambda: True,
        fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}),
    )
    try:
        asyncio.run(gen2.generate_video(_request(request_hash=HASH_OK2)))
    except FlowVideoCancelledError:
        pass
    _record(checks, "cancel_before_submit_blocks",
            ui2.actions == [],
            f"actions={ui2.actions} (must be empty)")

    # retry creates new attempt, keeps causal link, never overwrites receipts
    workspace2 = _workspace()
    registry2 = FlowJobRegistry(state_dir=str(workspace2), clock=time.time)
    registry2.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK3,
    )
    registry2.mark("gen_1", FlowJobStatus.FAILED_RETRYABLE)
    attempt = registry2.next_attempt("gen_1")
    decision = registry2.reconcile(
        request_hash=HASH_OK3, project_id="vp_1",
        provider="google_flow_browser",
    )
    _record(checks, "retry_new_attempt_causal_link",
            attempt.attempt == 2 and attempt.parent_generation_id == "gen_1",
            f"attempt={attempt.attempt} parent={attempt.parent_generation_id}")
    _record(checks, "retry_does_not_overwrite_receipt",
            registry2.get("gen_1") is not None
            and registry2.get("gen_1").status == FlowJobStatus.FAILED_RETRYABLE,
            "original receipt preserved")

    # terminal failure never auto-retried: mark the LATEST record (the
    # gen_1a2 attempt) FAILED_TERMINAL so the check tests the actual terminal
    # semantics instead of a leftover PREPARED record.
    registry2.mark(attempt.generation_id, FlowJobStatus.FAILED_TERMINAL)
    decision = registry2.reconcile(
        request_hash=HASH_OK3, project_id="vp_1",
        provider="google_flow_browser",
    )
    _record(checks, "terminal_never_auto_retried",
            decision.action == FlowReconcileAction.RECONCILE_UNKNOWN,
            "FAILED_TERMINAL → reconcile, no auto-retry")

    # invalid result (no candidate passed) → FAILED_TERMINAL, not COMPLETED.
    # Read a FRESH registry after the run (the generator owns its own
    # registry instance; a pre-created one would be empty).
    workspace3 = _workspace()
    gen3 = _generator(
        workspace3,
        fetcher=FakeFetcher({"res://clip.mp4": b"garbage"}),
        inspector=FakeInspector(valid=False),
    )
    try:
        asyncio.run(gen3.generate_video(_request(request_hash=HASH_OK4)))
    except FlowVideoInvalidResultError:
        pass
    fresh3 = FlowJobRegistry(state_dir=str(workspace3), clock=time.time)
    latest3 = fresh3.list_records()[-1]
    _record(checks, "invalid_result_terminal_not_completed",
            latest3.status == FlowJobStatus.FAILED_TERMINAL,
            f"status={latest3.status.value}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_video/video_cancel_retry.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
def main(no_write: bool = False) -> int:
    if not no_write:
        PHASE_DIR.mkdir(parents=True, exist_ok=True)

    video_ops = build_video_operations_receipt()
    mode = build_video_mode_validation_receipt()
    idem = build_video_idempotency_receipt()
    tech = build_video_technical_validation_receipt()
    cancel = build_video_cancel_retry_receipt()

    gate_reasons: list[str] = []
    if not video_ops["all_checks_pass"]:
        gate_reasons.append("video operations checks failed")
    if not mode["all_checks_pass"]:
        gate_reasons.append("mode validation checks failed")
    if not idem["all_checks_pass"]:
        gate_reasons.append("idempotency checks failed")
    if not tech["all_checks_pass"]:
        gate_reasons.append("technical validation checks failed")
    if not cancel["all_checks_pass"]:
        gate_reasons.append("cancel/retry checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 15,
        "status": overall_status,
        "gate": "VP15_FLOW_VIDEO_GENERATION_VERIFIED",
        "evidence": [
            {"path": "video_operations_receipt.json"},
            {"path": "video_mode_validation_receipt.json"},
            {"path": "video_idempotency_receipt.json"},
            {"path": "video_technical_validation_receipt.json"},
            {"path": "video_cancel_retry_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase15_flow_video.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "video_operations_receipt.json", video_ops)
        write_json(PHASE_DIR / "video_mode_validation_receipt.json", mode)
        write_json(PHASE_DIR / "video_idempotency_receipt.json", idem)
        write_json(PHASE_DIR / "video_technical_validation_receipt.json", tech)
        write_json(PHASE_DIR / "video_cancel_retry_receipt.json", cancel)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, video_ops, mode, idem, tech, cancel),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_15 artifacts untouched.")

    print(f"Phase 15 verdict: {overall_status}")
    print(f"  video operations: {'PASS' if video_ops['all_checks_pass'] else 'FAIL'}")
    print(f"  mode validation: {'PASS' if mode['all_checks_pass'] else 'FAIL'}")
    print(f"  idempotency: {'PASS' if idem['all_checks_pass'] else 'FAIL'}")
    print(f"  technical validation: {'PASS' if tech['all_checks_pass'] else 'FAIL'}")
    print(f"  cancel/retry: {'PASS' if cancel['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, ops, mode, idem, tech, cancel) -> str:
    return f"""# Phase 15 Report — Flow Video Generation

- **Gate:** `VP15_FLOW_VIDEO_GENERATION_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Video operations

- Contract: `docs/video_production/flow_video/video_operations_contract.md`
- Checks: {ops.get('check_count')}; all pass: {ops.get('all_checks_pass')}

## Mode validation

- Contract: `docs/video_production/flow_video/video_mode_validation.md`
- Checks: {mode.get('check_count')}; all pass: {mode.get('all_checks_pass')}

## Idempotency / reconciliation

- Contract: `docs/video_production/flow_video/video_job_idempotency.md`
- Checks: {idem.get('check_count')}; all pass: {idem.get('all_checks_pass')}

## Technical validation

- Contract: `docs/video_production/flow_video/video_technical_validation.md`
- Checks: {tech.get('check_count')}; all pass: {tech.get('all_checks_pass')}

## Cancel / retry

- Contract: `docs/video_production/flow_video/video_cancel_retry.md`
- Checks: {cancel.get('check_count')}; all pass: {cancel.get('all_checks_pass')}

## Evidence

- `video_operations_receipt.json`
- `video_mode_validation_receipt.json`
- `video_idempotency_receipt.json`
- `video_technical_validation_receipt.json`
- `video_cancel_retry_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
