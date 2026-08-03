"""
Phase 15 — Flow video generation unit tests (plan 04 §20-§24).

Covers the durable video pipeline with mocked UI / fetcher / inspector
fixtures (offline, deterministic):

- 5 typed video operations + mode validation matrix (§21, §23.2);
- mode validation fails closed BEFORE navigation/submit;
- idempotency/reconciliation — no duplicate submit across the failure
  matrix (crash before/during/after submit intent; repeated command;
  existing completed/active/unknown job; §23.1);
- submit exactly once; bounded poll with deadline;
- video candidates technically validated — invalid/no-video-stream never
  published and the job is NEVER COMPLETED with an invalid set (§23.3);
- cancel semantics — local stop, never asserts provider-side cancellation
  (§23.4); retry creates a new attempt with a causal link; terminal states
  are never auto-retried.
"""

import asyncio
import time
from pathlib import Path

import pytest

from windagent_tools.google_flow import (
    FlowJobRegistry,
    FlowJobStatus,
    FlowHumanActionBlockedError,
    FlowHumanActionStatus,
    FlowHumanControlManager,
    FlowHumanState,
    FlowNavigationReceipt,
    FlowProjectManager,
    FlowReconcileAction,
    FlowSubmitReconciledError,
    FlowUiAction,
    FlowUiObservation,
    FlowUiState,
    FlowVideoCancelledError,
    FlowVideoGenerator,
    FlowVideoHumanActionRequiredError,
    FlowVideoInvalidResultError,
    FlowVideoModeIssueCode,
    FlowVideoModeValidationError,
    FlowVideoOperation,
    FlowVideoRequest,
    PreSubmitGuard,
    VideoCandidateDownloader,
    VideoInspection,
    VideoInspectorPort,
    VideoOperationMapper,
)
from windagent_tools.media_assets.store import ContentAddressedStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HASH_OK = "a" * 64
HASH_UNAPPROVED = "b" * 64
HASH_OTHER = "c" * 64


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


class DownloadChallengeUi(FakeUi):
    """Returns a challenge only after the result view has been reached."""

    def __init__(self, script: list[FlowUiObservation]) -> None:
        super().__init__(script)
        self._result_seen = False

    async def observe(self) -> FlowUiObservation:
        observed = await super().observe()
        if "Result" in observed.markers:
            if self._result_seen:
                return self.script[2]
            self._result_seen = True
        return observed


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


def _video_bytes() -> bytes:
    # mp4-magic prefix passes the FakeInspector gate (content irrelevant).
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _happy_script(candidate_refs: tuple[str, ...] = ("candidate:res://clip.mp4",)):
    return [
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",),
            controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Result", *candidate_refs),
            controls=("button:Download",),
        ),
    ]


def _workspace() -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix="phase15_"))


def _generator(
    workspace: Path,
    *,
    ui=None,
    fetcher=None,
    inspector=None,
    mapper=None,
    cancel_requested=None,
    approved_hashes=frozenset({HASH_OK}),
    human_control_manager=None,
):
    store = ContentAddressedStore(workspace / "store")
    downloader = VideoCandidateDownloader(
        quarantine_dir=str(workspace / "quarantine"),
        store=store,
        inspector=inspector or FakeInspector(),
    )
    pm = FlowProjectManager(state_dir=str(workspace), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    return FlowVideoGenerator(
        session_id="sess_15",
        project_id="vp_1",
        ui=ui or FakeUi(_happy_script()),
        navigator=FakeNavigator(),
        project_manager=pm,
        project_mapping=mapping,
        guard=PreSubmitGuard(mapper=mapper or VideoOperationMapper()),
        job_registry=registry,
        downloader=downloader,
        fetcher=fetcher or FakeFetcher({"res://clip.mp4": _video_bytes()}),
        mapper=mapper,
        approved_hashes=approved_hashes,
        cancel_requested=cancel_requested,
        human_control_manager=human_control_manager,
    )


# ---------------------------------------------------------------------------
# 1. Operations + mode validation (§21, §23.2)
# ---------------------------------------------------------------------------

def test_video_operation_set_is_exactly_five():
    assert len(FlowVideoOperation) == 5
    values = {op.value for op in FlowVideoOperation}
    assert values == {
        "TEXT_TO_VIDEO",
        "FRAMES_TO_VIDEO",
        "INGREDIENTS_TO_VIDEO",
        "VIDEO_EXTENSION",
        "VIDEO_TO_VIDEO",
    }


def test_typed_configuration_actions_only():
    mapper = VideoOperationMapper()
    actions = mapper.configuration_actions(_request())
    assert all(isinstance(a, FlowUiAction) for a in actions)
    assert all(a.operation in ("select", "fill", "upload") for a in actions)


@pytest.mark.parametrize(
    "request_overrides,expected_codes",
    [
        # FRAMES_TO_VIDEO needs both frames approved
        (
            dict(
                operation=FlowVideoOperation.FRAMES_TO_VIDEO,
                reference_bindings=(("FIRST_FRAME", HASH_OTHER),),
            ),
            [FlowVideoModeIssueCode.MISSING_LAST_FRAME,
             FlowVideoModeIssueCode.FIRST_FRAME_NOT_APPROVED],
        ),
        (
            dict(
                operation=FlowVideoOperation.FRAMES_TO_VIDEO,
                reference_bindings=(
                    ("FIRST_FRAME", HASH_OK),
                    ("LAST_FRAME", HASH_OK),
                ),
            ),
            [],
        ),
        # INGREDIENTS_TO_VIDEO needs all ingredients approved
        (
            dict(
                operation=FlowVideoOperation.INGREDIENTS_TO_VIDEO,
                reference_bindings=(("INGREDIENT", HASH_UNAPPROVED),),
            ),
            [FlowVideoModeIssueCode.INGREDIENT_NOT_APPROVED],
        ),
        (
            dict(
                operation=FlowVideoOperation.INGREDIENTS_TO_VIDEO,
                reference_bindings=(),
            ),
            [FlowVideoModeIssueCode.MISSING_INGREDIENT],
        ),
        # VIDEO_EXTENSION needs approved predecessor + continuity state
        (
            dict(
                operation=FlowVideoOperation.VIDEO_EXTENSION,
                reference_bindings=(("PREDECESSOR_CLIP", HASH_OK),),
                continuity_state="",
            ),
            [FlowVideoModeIssueCode.CONTINUITY_NOT_READY],
        ),
        # VIDEO_TO_VIDEO needs source clip + transformation intent
        (
            dict(
                operation=FlowVideoOperation.VIDEO_TO_VIDEO,
                reference_bindings=(("SOURCE_CLIP", HASH_OK),),
                transformation_intent="",
            ),
            [FlowVideoModeIssueCode.TRANSFORMATION_INTENT_MISSING],
        ),
        (
            dict(
                operation=FlowVideoOperation.VIDEO_TO_VIDEO,
                reference_bindings=(("SOURCE_CLIP", HASH_UNAPPROVED),),
                transformation_intent="style transfer",
            ),
            [FlowVideoModeIssueCode.SOURCE_NOT_APPROVED],
        ),
        # duration / aspect / model policy
        (
            dict(duration_seconds=0.2),
            [FlowVideoModeIssueCode.DURATION_OUT_OF_POLICY],
        ),
        (
            dict(aspect_ratio="2:3"),
            [FlowVideoModeIssueCode.ASPECT_RATIO_UNSUPPORTED],
        ),
        (
            dict(model="unknown-model"),
            [FlowVideoModeIssueCode.MODEL_UNSUPPORTED],
        ),
    ],
)
def test_mode_validation_matrix(request_overrides, expected_codes):
    mapper = VideoOperationMapper()
    issues = mapper.validate_mode(
        _request(**request_overrides), approved_hashes=frozenset({HASH_OK})
    )
    codes = [i.code for i in issues]
    assert sorted(codes) == sorted(expected_codes), codes


def test_text_to_video_requires_no_bindings():
    mapper = VideoOperationMapper()
    assert mapper.validate_mode(
        _request(), approved_hashes=frozenset()
    ) == ()


def test_capability_fails_closed():
    mapper = VideoOperationMapper(
        capability=(FlowVideoOperation.TEXT_TO_VIDEO,)
    )
    assert mapper.supported(FlowVideoOperation.TEXT_TO_VIDEO)
    assert not mapper.supported(FlowVideoOperation.VIDEO_TO_VIDEO)


def test_generator_blocks_mode_validation_before_submit():
    workspace = _workspace()
    ui = FakeUi(_happy_script())
    gen = _generator(workspace, ui=ui)
    with pytest.raises(FlowVideoModeValidationError) as exc:
        asyncio.run(
            gen.generate_video(
                _request(operation=FlowVideoOperation.FRAMES_TO_VIDEO,
                         reference_bindings=())
            )
        )
    codes = [i.code for i in exc.value.issues]
    assert FlowVideoModeIssueCode.MISSING_FIRST_FRAME in codes
    assert ui.actions == []  # nothing clicked, no submit


def test_generator_unsupported_operation_raises():
    workspace = _workspace()
    gen = _generator(workspace, mapper=VideoOperationMapper(capability=()))
    with pytest.raises(Exception):
        asyncio.run(gen.generate_video(_request()))


# ---------------------------------------------------------------------------
# 2. Idempotency / reconciliation (§23.1)
# ---------------------------------------------------------------------------

def test_repeated_command_reuses_completed_job():
    workspace = _workspace()
    gen = _generator(workspace, fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out1 = asyncio.run(gen.generate_video(_request()))
    assert out1.submit_clicked and len(out1.candidates) == 1

    # same request hash → REUSE_COMPLETED, no submit
    ui2 = FakeUi(_happy_script())
    gen2 = _generator(workspace, ui=ui2, fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out2 = asyncio.run(gen2.generate_video(_request()))
    assert out2.submit_clicked is False
    assert ui2.actions == []


def test_crash_before_submit_intent_creates_new_prepared():
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    decision = registry.reconcile(
        request_hash=HASH_OK, project_id="vp_1", provider="google_flow_browser"
    )
    assert decision.action == FlowReconcileAction.CREATE_PREPARED


def test_crash_after_submit_intent_resumes_active():
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK,
    )
    registry.mark("gen_1", FlowJobStatus.SUBMITTING)
    decision = registry.reconcile(
        request_hash=HASH_OK, project_id="vp_1", provider="google_flow_browser"
    )
    assert decision.action == FlowReconcileAction.RESUME_ACTIVE


def test_unknown_job_state_reconciles_never_resubmits():
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK,
    )
    registry.mark("gen_1", FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION)
    decision = registry.reconcile(
        request_hash=HASH_OK, project_id="vp_1", provider="google_flow_browser"
    )
    assert decision.action == FlowReconcileAction.RECONCILE_UNKNOWN

    gen = _generator(workspace)
    with pytest.raises(FlowSubmitReconciledError):
        asyncio.run(gen.generate_video(_request()))


def test_browser_close_after_submit_prefers_reinspection():
    """RESUME_ACTIVE path re-inspects the SAME Flow project (plan §23.4)."""
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK,
    )
    registry.mark("gen_1", FlowJobStatus.GENERATING)
    ui = FakeUi([
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Result", "candidate:res://clip.mp4"),
            controls=("button:Download",),
        ),
    ])
    gen = _generator(workspace, ui=ui, fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out = asyncio.run(gen.generate_video(_request()))
    assert out.submit_clicked is False  # re-inspection, no resubmit
    assert ui.actions == []


def test_video_generator_human_challenge_creates_durable_takeover():
    workspace = _workspace()
    manager = FlowHumanControlManager(state_dir=str(workspace))
    ui = FakeUi([
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Verify you are human",), controls=("button:Continue",),
        ),
    ])
    gen = _generator(
        workspace,
        ui=ui,
        human_control_manager=manager,
        fetcher=FakeFetcher({}),
    )
    with pytest.raises(FlowVideoHumanActionRequiredError) as exc_info:
        asyncio.run(gen.generate_video(_request()))

    record = exc_info.value.record
    assert record.status == FlowHumanActionStatus.PENDING
    assert record.human_state == FlowHumanState.HUMAN_CAPTCHA_REQUIRED
    assert gen.job_registry.get(record.generation_id).status == FlowJobStatus.HUMAN_ACTION_REQUIRED
    with pytest.raises(FlowHumanActionBlockedError):
        manager.assert_session_active("sess_15")
    assert (
        FlowHumanControlManager(state_dir=str(workspace))
        .get_record(record.human_action_id)
        .status
        == FlowHumanActionStatus.PENDING
    )


def test_video_generator_stops_before_download_when_challenge_appears():
    workspace = _workspace()
    manager = FlowHumanControlManager(state_dir=str(workspace))
    ui = DownloadChallengeUi([
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Result", "candidate:res://clip.mp4"),
            controls=("button:Download",),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Verify you are human",), controls=("button:Continue",),
        ),
    ])
    gen = _generator(
        workspace,
        ui=ui,
        human_control_manager=manager,
        fetcher=FakeFetcher({}),
    )
    with pytest.raises(FlowVideoHumanActionRequiredError) as exc_info:
        asyncio.run(gen.generate_video(_request()))

    record = exc_info.value.record
    assert record.safe_resume_state == FlowUiState.RESULT_READY
    assert "before video candidate download" in record.reason
    assert gen.job_registry.get(record.generation_id).status == FlowJobStatus.HUMAN_ACTION_REQUIRED


def test_retry_creates_new_attempt_with_causal_link():
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK,
    )
    registry.mark("gen_1", FlowJobStatus.FAILED_RETRYABLE)
    attempt = registry.next_attempt("gen_1")
    assert attempt.attempt == 2
    assert attempt.parent_generation_id == "gen_1"
    assert attempt.generation_id != "gen_1"


def test_terminal_failure_never_auto_retried():
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=HASH_OK,
    )
    registry.mark("gen_1", FlowJobStatus.FAILED_TERMINAL)
    decision = registry.reconcile(
        request_hash=HASH_OK, project_id="vp_1", provider="google_flow_browser"
    )
    assert decision.action == FlowReconcileAction.RECONCILE_UNKNOWN


# ---------------------------------------------------------------------------
# 3. Candidate technical validation (§23.3)
# ---------------------------------------------------------------------------

def test_submit_exactly_once():
    workspace = _workspace()
    ui = FakeUi(_happy_script())
    gen = _generator(workspace, ui=ui)
    asyncio.run(gen.generate_video(_request()))
    assert ui.actions.count("submit") == 1  # operation name is "submit"


def test_valid_video_candidate_published_and_completed():
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")
    gen = _generator(workspace, fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}))
    out = asyncio.run(gen.generate_video(_request()))
    assert out.ok
    assert out.job.status == FlowJobStatus.COMPLETED
    assert len(out.candidates) == 1
    assert out.candidates[0].published
    assert out.candidates[0].inspection.has_video_stream
    assert len(store.list_hashes()) == 1


def test_no_video_stream_candidate_never_completed():
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")
    gen = _generator(
        workspace,
        fetcher=FakeFetcher({"res://clip.mp4": b"not a video at all"}),
        inspector=FakeInspector(valid=False),
    )
    with pytest.raises(FlowVideoInvalidResultError):
        asyncio.run(gen.generate_video(_request()))
    assert len(store.list_hashes()) == 0  # never published
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    latest = registry.list_records()[-1]
    assert latest.status == FlowJobStatus.FAILED_TERMINAL


def test_zero_byte_candidate_rejected():
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")
    gen = _generator(
        workspace,
        fetcher=FakeFetcher({"res://clip.mp4": b""}),
        inspector=FakeInspector(valid=True),
    )
    with pytest.raises(FlowVideoInvalidResultError):
        asyncio.run(gen.generate_video(_request()))
    assert len(store.list_hashes()) == 0


def test_duration_out_of_policy_rejected():
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")

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

    gen = _generator(
        workspace,
        fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}),
        inspector=ShortInspector(),
        mapper=VideoOperationMapper(),  # request duration passes mode check
    )
    with pytest.raises(FlowVideoInvalidResultError):
        asyncio.run(gen.generate_video(_request()))
    assert len(store.list_hashes()) == 0


def _video_bytes_variant(seed: int) -> bytes:
    # distinct payload so the content-addressed store keeps two artifacts
    return b"\x00\x00\x00\x18ftypmp42" + bytes([seed & 0xFF]) * 64


def test_multi_candidate_acquires_all():
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")
    refs = ("candidate:res://a.mp4", "candidate:res://b.mp4")
    ui = FakeUi(_happy_script(refs))
    gen = _generator(
        workspace, ui=ui,
        fetcher=FakeFetcher({
            "res://a.mp4": _video_bytes(),
            "res://b.mp4": _video_bytes_variant(9),
        }),
    )
    out = asyncio.run(
        gen.generate_video(_request(request_hash=HASH_OTHER))
    )
    assert len(out.candidates) == 2
    assert len(store.list_hashes()) == 2
    assert out.job.status == FlowJobStatus.COMPLETED


# ---------------------------------------------------------------------------
# 4. Cancel / retry semantics (§23.4)
# ---------------------------------------------------------------------------

def test_cancel_stops_poll_and_never_claims_provider_side():
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
    with pytest.raises(FlowVideoCancelledError) as exc:
        asyncio.run(gen.generate_video(_request()))
    assert "provider-side" in str(exc.value)  # never claims provider cancelled
    # re-read the persisted registry (the generator owns its own instance)
    fresh = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    latest = fresh.list_records()[-1]
    assert latest.status == FlowJobStatus.CANCELLED


def test_cancel_before_submit_blocks():
    workspace = _workspace()
    ui = FakeUi(_happy_script())
    gen = _generator(
        workspace, ui=ui, cancel_requested=lambda: True,
        fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}),
    )
    with pytest.raises(FlowVideoCancelledError):
        asyncio.run(gen.generate_video(_request()))
    assert ui.actions == []


def test_pre_submit_guard_still_fails_closed_for_video():
    workspace = _workspace()
    gen = _generator(
        workspace,
        mapper=VideoOperationMapper(),
    )
    # invalid request hash → guard blocks before any submit
    with pytest.raises(Exception):
        asyncio.run(gen.generate_video(_request(request_hash="bad-hash")))
    ui = FakeUi(_happy_script())
    gen2 = _generator(
        workspace, ui=ui,
        mapper=VideoOperationMapper(),
        fetcher=FakeFetcher({"res://clip.mp4": _video_bytes()}),
    )
    with pytest.raises(Exception):
        asyncio.run(gen2.generate_video(_request(request_hash="bad-hash")))
    assert ui.actions == []
