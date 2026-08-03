"""Phase 14 — Flow image generation unit tests (plan 04 §16–§19).

Covers: 8 typed image operations mapped to typed config actions; pre-submit
guard fail-closed; durable job reconciliation (reuse/resume/new-attempt/
reconcile-unknown, no blind resubmit); candidate acquisition (0/1/n, invalid
never published); fail-closed review (character master → human, VLM low →
human, no auto-bind). All offline with fake UI / fetcher / VLM ports.
"""

from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path

import pytest
from PIL import Image

from windagent_tools.google_flow import (
    CandidateDownloader,
    CandidateInvalidError,
    FlowImageGenerationError,
    FlowImageGenerator,
    FlowImageHumanActionRequiredError,
    FlowImageOperation,
    FlowImageRequest,
    FlowJobRecord,
    FlowJobRegistry,
    FlowJobStatus,
    FlowHumanActionBlockedError,
    FlowHumanActionStatus,
    FlowHumanControlManager,
    FlowHumanState,
    FlowNavigationReceipt,
    FlowPreSubmitBlockedError,
    FlowProjectManager,
    FlowReconcileAction,
    FlowSubmitReconciledError,
    FlowUiAction,
    FlowUiObservation,
    FlowUiState,
    ImageOperationMapper,
    PreSubmitGuard,
    ReviewDecision,
    ReviewGate,
    VlmReviewPort,
    VlmScores,
)
from windagent_tools.media_assets.store import ContentAddressedStore


def _png_bytes(color: tuple = (255, 0, 0), size: tuple = (32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


REQUEST_HASH = "a" * 64


def _request(**overrides) -> FlowImageRequest:
    base = dict(
        operation=FlowImageOperation.CREATE_STORYBOARD_FRAME,
        request_hash=REQUEST_HASH,
        project_id="vp_1",
        revision_id="rev_1",
        shot_id="shot_1",
        prompt="a red cube",
        reference_bindings=(("identity", "hash0"),),
        candidate_limit=4,
    )
    base.update(overrides)
    return FlowImageRequest(**base)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeUi:
    """Scripted UI: returns observations per state, records actions."""

    def __init__(self, script: list[FlowUiObservation], *,
                 candidate_refs: tuple[str, ...] = ()) -> None:
        self.script = script
        self.index = 0
        self.pending_advance = False
        self.actions: list[str] = []
        self.candidate_refs = candidate_refs

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
    """Surface a challenge only when the first candidate fetch is about to run."""

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
            session_id="sess_1",
            project_id="vp_1",
            target_state=FlowUiState.SUBMIT_READY,
            reached_state=FlowUiState.SUBMIT_READY,
            pre_submit_evidence_hash="pre-evidence",
        )


class FakeFetcher:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    async def fetch(self, uri: str) -> bytes:
        return self.payloads[uri]


class FakeVlm(VlmReviewPort):
    def __init__(self, compliance: float = 0.9, identity: float = 0.9) -> None:
        self.compliance = compliance
        self.identity = identity

    async def score(self, *, candidate, request) -> VlmScores:
        return VlmScores(
            prompt_compliance=self.compliance, identity=self.identity
        )


def _happy_script() -> list[FlowUiObservation]:
    return [
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Generating",),
            controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Result", "candidate:https://cdn.example.com/a.png",
                     "candidate:https://cdn.example.com/b.png"),
            controls=("button:Download",),
        ),
    ]


def _generator(tmp_path: Path, *, ui=None, vlm=None, fetcher=None, mapper=None,
               request_hash=REQUEST_HASH, **kwargs):
    store = ContentAddressedStore(tmp_path / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(tmp_path / "quarantine"),
        store=store,
    )
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    job_registry = FlowJobRegistry(state_dir=str(tmp_path), clock=time.time)
    return FlowImageGenerator(
        session_id="sess_1",
        project_id="vp_1",
        ui=ui or FakeUi(_happy_script()),
        navigator=FakeNavigator(),
        project_manager=pm,
        project_mapping=mapping,
        guard=PreSubmitGuard(mapper=mapper or ImageOperationMapper()),
        job_registry=job_registry,
        downloader=downloader,
        review_gate=ReviewGate(clock=time.time),
        vlm=vlm,
        fetcher=fetcher,
        mapper=mapper,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Image operation mapping (plan §17)
# ---------------------------------------------------------------------------
def test_mapper_has_all_eight_operations():
    ops = {op.value for op in FlowImageOperation}
    assert len(ops) == 8
    for expected in (
        "CREATE_CHARACTER_REFERENCE",
        "CREATE_LOCATION_REFERENCE",
        "CREATE_PROP_REFERENCE",
        "CREATE_STORYBOARD_FRAME",
        "CREATE_FIRST_FRAME",
        "CREATE_LAST_FRAME",
        "EDIT_IMAGE",
        "UPSCALE_IMAGE",
    ):
        assert expected in ops


def test_mapper_configuration_uses_typed_actions_only():
    mapper = ImageOperationMapper()
    actions = mapper.configuration_actions(_request())
    assert actions
    assert all(isinstance(a, FlowUiAction) for a in actions)
    # typed operations only — never a raw browser command
    assert all(a.operation in ("select", "fill", "upload") for a in actions)


def test_mapper_character_master_and_reference_policy():
    mapper = ImageOperationMapper()
    assert mapper.is_character_master(FlowImageOperation.CREATE_CHARACTER_REFERENCE)
    assert not mapper.is_character_master(
        FlowImageOperation.CREATE_STORYBOARD_FRAME
    )
    assert mapper.requires_reference(FlowImageOperation.CREATE_FIRST_FRAME)
    assert not mapper.requires_reference(FlowImageOperation.EDIT_IMAGE)
    assert mapper.requires_source_image(FlowImageOperation.UPSCALE_IMAGE)


def test_mapper_capability_gate():
    mapper = ImageOperationMapper(
        capability=(FlowImageOperation.CREATE_STORYBOARD_FRAME,)
    )
    assert mapper.supported(FlowImageOperation.CREATE_STORYBOARD_FRAME)
    assert not mapper.supported(FlowImageOperation.UPSCALE_IMAGE)


# ---------------------------------------------------------------------------
# 2. Pre-submit guard (plan §18.1)
# ---------------------------------------------------------------------------
def test_pre_submit_guard_passes_when_all_conditions_ok():
    guard = PreSubmitGuard()
    verdict = guard.check(
        _request(),
        mapping_healthy=True,
        session_healthy=True,
        references_approved=True,
        upload_hash_matches=True,
        pre_submit_evidence_hash="evidence",
        operation_supported=True,
        cost_allowed=True,
    )
    assert verdict.ok
    assert verdict.reasons == ()


@pytest.mark.parametrize(
    "broken",
    [
        dict(request_hash="bad"),
        dict(mapping_healthy=False),
        dict(session_healthy=False),
        dict(references_approved=False),
        dict(upload_hash_matches=False),
        dict(pre_submit_evidence_hash=""),
        dict(operation_supported=False),
        dict(cost_allowed=False),
        dict(candidate_limit=0),
        dict(candidate_limit=99),
    ],
)
def test_pre_submit_guard_fails_closed(broken):
    guard = PreSubmitGuard()
    kwargs = dict(
        mapping_healthy=True,
        session_healthy=True,
        references_approved=True,
        upload_hash_matches=True,
        pre_submit_evidence_hash="evidence",
        operation_supported=True,
        cost_allowed=True,
    )
    # request fields that live on the request, not the check kwargs
    request_hash = REQUEST_HASH
    candidate_limit = 4
    if "request_hash" in broken:
        request_hash = "bad"
        kwargs.pop("request_hash", None)
    if "candidate_limit" in broken:
        candidate_limit = broken["candidate_limit"]
        kwargs.pop("candidate_limit", None)
    kwargs.update(broken)
    kwargs.pop("request_hash", None)
    kwargs.pop("candidate_limit", None)
    # reference-required operation so the reference/upload checks apply
    request = _request(
        operation=FlowImageOperation.CREATE_CHARACTER_REFERENCE,
        request_hash=request_hash,
        candidate_limit=candidate_limit,
    )
    verdict = guard.check(request, **kwargs)
    assert not verdict.ok
    assert verdict.reasons


# ---------------------------------------------------------------------------
# 3. Job reconciliation (plan §18.2 / §23.1)
# ---------------------------------------------------------------------------
def test_job_registry_reconcile_matrix(tmp_path):
    registry = FlowJobRegistry(state_dir=str(tmp_path), clock=time.time)
    key = dict(request_hash=REQUEST_HASH, project_id="vp_1",
               provider="google_flow_browser")

    # missing → CREATE_PREPARED
    assert registry.reconcile(**key).action == FlowReconcileAction.CREATE_PREPARED

    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=REQUEST_HASH,
    )
    # PREPARED is treated as non-active → reconcile unknown (no blind resubmit
    # once a record exists but was never submitted).
    decision = registry.reconcile(**key)
    assert decision.action == FlowReconcileAction.RECONCILE_UNKNOWN

    # COMPLETED → reuse
    registry.record_candidates("gen_1", ["c0", "c1"])
    assert registry.reconcile(**key).action == FlowReconcileAction.REUSE_COMPLETED

    # active → resume
    registry.mark("gen_1", FlowJobStatus.GENERATING)
    decision = registry.reconcile(**key)
    assert decision.action == FlowReconcileAction.RESUME_ACTIVE

    # failed retryable → new attempt (within budget)
    registry.mark("gen_1", FlowJobStatus.FAILED_RETRYABLE)
    decision = registry.reconcile(**key)
    assert decision.action == FlowReconcileAction.NEW_ATTEMPT
    assert decision.record.attempt == 1

    # budget exhausted → reconcile unknown (never blind resubmit)
    # chain attempts properly: FAILED_RETRYABLE -> NEW_ATTEMPT -> FAILED...
    current = "gen_1"
    for _ in range(3):  # attempt 2, 3, 4 — budget is 3, so >= 3 is exhausted
        nxt = registry.next_attempt(current)
        registry.mark(nxt.generation_id, FlowJobStatus.FAILED_RETRYABLE)
        current = nxt.generation_id
    assert registry.reconcile(**key).action == FlowReconcileAction.RECONCILE_UNKNOWN

    # terminal → reconcile unknown
    registry.mark(current, FlowJobStatus.FAILED_TERMINAL)
    assert registry.reconcile(**key).action == FlowReconcileAction.RECONCILE_UNKNOWN
    # causal link is preserved on the new attempt
    nxt2 = registry.next_attempt("gen_1")
    assert nxt2.attempt == 2
    assert nxt2.parent_generation_id == "gen_1"


def test_job_record_persists_across_reload(tmp_path):
    registry = FlowJobRegistry(state_dir=str(tmp_path), clock=time.time)
    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=REQUEST_HASH,
    )
    registry.mark("gen_1", FlowJobStatus.GENERATING)
    reloaded = FlowJobRegistry(state_dir=str(tmp_path), clock=time.time)
    got = reloaded.get("gen_1")
    assert got is not None
    assert got.status == FlowJobStatus.GENERATING


# ---------------------------------------------------------------------------
# 4. Candidate acquisition (plan §18.3)
# ---------------------------------------------------------------------------
def test_candidate_downloader_publishes_valid_candidate(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(tmp_path / "quarantine"), store=store
    )
    job = FlowJobRecord(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1"
    )
    png = _png_bytes()

    async def run():
        return await downloader.acquire(
            job=job, candidate_id="gen_1c0", uri="res://a.png", index=0,
            fetcher=FakeFetcher({"res://a.png": png}),
        )

    acquired = asyncio.run(run())
    assert acquired.published is True
    assert acquired.mime == "image/png"
    assert acquired.content_hash == store.content_hash(png)
    assert store.exists(acquired.content_hash)


def test_candidate_downloader_rejects_zero_byte_and_wrong_mime(tmp_path):
    store = ContentAddressedStore(tmp_path / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(tmp_path / "quarantine"), store=store
    )
    job = FlowJobRecord(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1"
    )

    async def run(payload):
        return await downloader.acquire(
            job=job, candidate_id="gen_1c0", uri="res://x", index=0,
            fetcher=FakeFetcher({"res://x": payload}),
        )

    with pytest.raises(CandidateInvalidError):
        asyncio.run(run(b""))
    with pytest.raises(CandidateInvalidError):
        asyncio.run(run(b"definitely not an image"))
    # nothing was published to the canonical store
    assert store.list_hashes() == []


# ---------------------------------------------------------------------------
# 5. Review / approval (plan §18.4)
# ---------------------------------------------------------------------------
def _acquired(tmp_path, png=None):
    store = ContentAddressedStore(tmp_path / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(tmp_path / "quarantine"), store=store
    )
    job = FlowJobRecord(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1"
    )
    payload = png or _png_bytes()

    async def run():
        return await downloader.acquire(
            job=job, candidate_id="gen_1c0", uri="res://a.png", index=0,
            fetcher=FakeFetcher({"res://a.png": payload}),
        )

    return asyncio.run(run())


def test_review_character_master_never_auto_approved(tmp_path):
    gate = ReviewGate(clock=time.time)
    acquired = _acquired(tmp_path)
    request = _request(operation=FlowImageOperation.CREATE_CHARACTER_REFERENCE)

    async def run():
        return await gate.review(
            candidate=acquired, request=request,
            vlm=FakeVlm(compliance=0.99, identity=0.99),
            deterministic_valid=True,
        )

    review = asyncio.run(run())
    assert review.decision == ReviewDecision.REQUIRES_HUMAN
    assert review.character_master is True


def test_review_vlm_low_confidence_needs_human(tmp_path):
    gate = ReviewGate(clock=time.time)
    acquired = _acquired(tmp_path)
    request = _request()

    async def run():
        return await gate.review(
            candidate=acquired, request=request,
            vlm=FakeVlm(compliance=0.2, identity=0.2),
            deterministic_valid=True,
        )

    review = asyncio.run(run())
    assert review.decision == ReviewDecision.REQUIRES_HUMAN


def test_review_invalid_candidate_rejected_before_vlm(tmp_path):
    """A candidate whose deterministic validity failed is rejected BEFORE any
    VLM scoring, even at high VLM confidence (plan 04 §18.4)."""
    gate = ReviewGate(clock=time.time)
    acquired = _acquired(tmp_path)  # valid acquisition
    request = _request()

    async def run():
        return await gate.review(
            candidate=acquired, request=request,
            vlm=FakeVlm(compliance=0.99, identity=0.99),
            deterministic_valid=False,  # file validation failed first
        )

    review = asyncio.run(run())
    assert review.decision == ReviewDecision.REJECTED
    assert review.reason.startswith("deterministic file validation")


def test_review_approves_high_confidence_non_master(tmp_path):
    gate = ReviewGate(clock=time.time)
    acquired = _acquired(tmp_path)
    request = _request()

    async def run():
        return await gate.review(
            candidate=acquired, request=request,
            vlm=FakeVlm(compliance=0.95, identity=0.95),
            deterministic_valid=True,
        )

    review = asyncio.run(run())
    assert review.decision == ReviewDecision.APPROVED


# ---------------------------------------------------------------------------
# 6. End-to-end generator (plan §18)
# ---------------------------------------------------------------------------
def test_generator_submits_once_and_acquires_candidates(tmp_path):
    ui = FakeUi(_happy_script())
    png = _png_bytes()
    fetcher = FakeFetcher({
        "https://cdn.example.com/a.png": png,
        "https://cdn.example.com/b.png": _png_bytes((0, 255, 0)),
    })
    gen = _generator(tmp_path, ui=ui, fetcher=fetcher, vlm=FakeVlm())
    outcome = asyncio.run(gen.generate_image(_request()))
    assert outcome.submit_clicked is True
    assert outcome.reached_state == FlowUiState.RESULT_READY
    assert outcome.ok is True
    # exactly one submit click (plan §18.2)
    assert ui.actions.count("submit") == 1
    # every candidate acquired, none defaulted to first
    assert len(outcome.candidates) == 2
    assert all(c.published for c in outcome.candidates)
    # every candidate reviewed (no auto-bind)
    assert len(outcome.reviews) == 2
    assert all(r.decision in ReviewDecision for r in outcome.reviews)


def test_generator_zero_candidates_is_not_ok(tmp_path):
    ui = FakeUi([
        FlowUiObservation(url="https://flow.google.com/editor",
                          markers=("Generating",), controls=()),
        FlowUiObservation(url="https://flow.google.com/editor",
                          markers=("Result",), controls=("button:Download",)),
    ])
    gen = _generator(tmp_path, ui=ui, fetcher=FakeFetcher({}), vlm=FakeVlm())
    outcome = asyncio.run(gen.generate_image(_request()))
    assert outcome.submit_clicked is True
    assert outcome.candidates == ()
    assert outcome.ok is False


def test_generator_pre_submit_blocked_never_clicks(tmp_path):
    """Supported operation but a failing guard condition → blocked before any
    submit click (plan 04 §18.1)."""
    ui = FakeUi(_happy_script())
    gen = _generator(tmp_path, ui=ui)
    # supported operation with an invalid request hash → guard blocks
    request = _request(request_hash="not-a-real-hash")
    with pytest.raises(FlowPreSubmitBlockedError):
        asyncio.run(gen.generate_image(request))
    assert ui.actions.count("submit") == 0


def test_generator_reuse_completed_no_resubmit(tmp_path):
    ui = FakeUi(_happy_script())
    png = _png_bytes()
    fetcher = FakeFetcher({
        "https://cdn.example.com/a.png": png,
        "https://cdn.example.com/b.png": _png_bytes((0, 255, 0)),
    })
    gen = _generator(tmp_path, ui=ui, fetcher=fetcher, vlm=FakeVlm())
    asyncio.run(gen.generate_image(_request()))
    # second identical command → completed job reused, no second submit
    outcome2 = asyncio.run(gen.generate_image(_request()))
    assert outcome2.submit_clicked is False
    assert outcome2.candidates == ()  # reuse signals intact record, no re-download


def test_generator_resume_active_no_resubmit(tmp_path):
    registry = FlowJobRegistry(state_dir=str(tmp_path), clock=time.time)
    registry.create_prepared(
        generation_id="gen_active", project_id="vp_1", revision_id="rev_1",
        request_hash=REQUEST_HASH,
    )
    registry.mark("gen_active", FlowJobStatus.GENERATING)
    ui = FakeUi([
        FlowUiObservation(url="https://flow.google.com/editor",
                          markers=("Generating",), controls=()),
    ])
    gen = _generator(tmp_path, ui=ui, fetcher=FakeFetcher({}), vlm=FakeVlm())
    # registry already has an active job for this request_hash → resume
    outcome = asyncio.run(gen.generate_image(_request()))
    assert outcome.submit_clicked is False


def test_generator_unknown_state_reconciles_no_resubmit(tmp_path):
    ui = FakeUi([
        FlowUiObservation(url="https://flow.google.com/editor",
                          markers=("Generating",), controls=()),
        FlowUiObservation(url="https://flow.google.com/editor",
                          markers=(), controls=()),
    ])
    gen = _generator(tmp_path, ui=ui, fetcher=FakeFetcher({}), vlm=FakeVlm())
    with pytest.raises(FlowSubmitReconciledError):
        asyncio.run(gen.generate_image(_request()))
    # job is recorded as requiring reconciliation
    job = gen.job_registry.list_records()[-1]
    assert job.status == FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION


def test_generator_human_challenge_creates_durable_takeover(tmp_path):
    manager = FlowHumanControlManager(state_dir=str(tmp_path))
    ui = FakeUi([
        FlowUiObservation(
            url="https://flow.google.com/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/editor",
            markers=("Verify you are human",), controls=("button:Continue",),
        ),
    ])
    gen = _generator(
        tmp_path,
        ui=ui,
        fetcher=FakeFetcher({}),
        vlm=FakeVlm(),
        human_control_manager=manager,
    )
    with pytest.raises(FlowImageHumanActionRequiredError) as exc_info:
        asyncio.run(gen.generate_image(_request()))

    record = exc_info.value.record
    assert record.status == FlowHumanActionStatus.PENDING
    assert record.human_state == FlowHumanState.HUMAN_CAPTCHA_REQUIRED
    assert gen.job_registry.get(record.generation_id).status == FlowJobStatus.HUMAN_ACTION_REQUIRED
    with pytest.raises(FlowHumanActionBlockedError):
        manager.assert_session_active("sess_1")
    assert (
        FlowHumanControlManager(state_dir=str(tmp_path))
        .get_record(record.human_action_id)
        .status
        == FlowHumanActionStatus.PENDING
    )


def test_generator_stops_before_download_when_challenge_appears(tmp_path):
    manager = FlowHumanControlManager(state_dir=str(tmp_path))
    ui = DownloadChallengeUi([
        FlowUiObservation(
            url="https://flow.google.com/editor",
            markers=("Generating",), controls=(),
        ),
        FlowUiObservation(
            url="https://flow.google.com/editor",
            markers=("Result", "candidate:https://cdn.example.com/a.png"),
            controls=("button:Download",),
        ),
        FlowUiObservation(
            url="https://flow.google.com/editor",
            markers=("Verify you are human",), controls=("button:Continue",),
        ),
    ])
    gen = _generator(
        tmp_path,
        ui=ui,
        fetcher=FakeFetcher({}),
        vlm=FakeVlm(),
        human_control_manager=manager,
    )
    with pytest.raises(FlowImageHumanActionRequiredError) as exc_info:
        asyncio.run(gen.generate_image(_request()))

    record = exc_info.value.record
    assert record.safe_resume_state == FlowUiState.RESULT_READY
    assert "before image candidate download" in record.reason
    assert gen.job_registry.get(record.generation_id).status == FlowJobStatus.HUMAN_ACTION_REQUIRED


def test_generator_unsupported_operation_raises(tmp_path):
    gen = _generator(tmp_path, mapper=ImageOperationMapper(
        capability=()
    ))
    with pytest.raises(FlowImageGenerationError):
        asyncio.run(gen.generate_image(_request()))


if __name__ == "__main__":
    import pytest as _pt

    _pt.main([__file__, "-v"])
