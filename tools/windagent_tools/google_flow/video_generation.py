"""
Phase 15 — Video generation orchestrator (plan 04 §20-§24).

`FlowVideoGenerator.generate_video()` runs the durable video pipeline:

    1. mode validation (plan §23.2) — fail closed BEFORE anything else;
    2. idempotency reconciliation (plan §23.1) — reuse completed / resume
       active / new attempt / reconcile unknown — never blind resubmit;
    3. navigate → pre-submit guard → persist SUBMITTING intent → click submit
       exactly once with the internal idempotency token;
    4. bounded poll (backoff + deadline) → DOWNLOADING;
    5. acquire EVERY video candidate with technical validation (stream,
       duration, resolution, fps) → atomic publish → COMPLETED only after a
       valid candidate is published (plan §23.3).

Cancel/retry (plan §23.4): a `cancel_requested` callback stops the poll loop
locally and marks the job CANCELLED — the generator NEVER asserts the
provider-side cancellation it cannot observe. Retry creates a NEW attempt
with a causal parent link (never overwrites an old receipt); terminal states
(account/payment/safety) are never auto-retried.

Fully testable offline with a fake `FlowUiPort` + `VideoFetcherPort` +
`VideoInspectorPort`.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from windagent_tools.google_flow.image_generation import FlowSubmitReconciledError
from windagent_tools.google_flow.human_control import (
    FlowHumanActionRecord,
    FlowHumanControlDetector,
    FlowHumanControlManager,
    FlowHumanState,
)
from windagent_tools.google_flow.job_record import (
    FlowJobRecord,
    FlowJobRegistry,
    FlowJobStatus,
    FlowReconcileAction,
)
from windagent_tools.google_flow.navigation import (
    FlowNavigator,
    FlowUiAction,
    FlowUiPort,
)
from windagent_tools.google_flow.pre_submit_guard import (
    FlowPreSubmitBlockedError,
    PreSubmitGuard,
)
from windagent_tools.google_flow.project_manager import (
    FlowProjectManager,
    FlowProjectMapping,
)
from windagent_tools.google_flow.state_machine import (
    FlowUiState,
    FlowUiStateMachine,
)
from windagent_tools.google_flow.video_candidates import (
    VideoCandidateAcquisition,
    VideoCandidateDownloader,
    VideoCandidateInvalidError,
    VideoFetcherPort,
)
from windagent_tools.google_flow.video_operations import (
    FlowVideoModeIssue,
    FlowVideoOperation,
    FlowVideoRequest,
    VideoOperationMapper,
)


class FlowVideoGenerationError(RuntimeError):
    """Base error for video generation orchestration."""


class FlowVideoHumanActionRequiredError(FlowVideoGenerationError):
    """A browser challenge paused the video job for manual resolution."""

    def __init__(self, record: FlowHumanActionRecord) -> None:
        super().__init__(
            "human action required; generation paused "
            f"(human_action_id={record.human_action_id})"
        )
        self.record = record


class FlowVideoModeValidationError(FlowVideoGenerationError):
    """Mode validation failed (plan §23.2); nothing was submitted."""

    def __init__(
        self,
        message: str = "video mode validation failed",
        *,
        issues: tuple[FlowVideoModeIssue, ...] = (),
    ) -> None:
        super().__init__(message)
        self.issues = issues


class FlowVideoCancelledError(FlowVideoGenerationError):
    """Generation was cancelled locally (plan §23.4).

    The provider-side cancellation is NOT asserted — WindAgent only stopped
    its own action/poll loop.
    """


class FlowVideoSubmitReconciledError(FlowSubmitReconciledError):
    """The job requires reconciliation; the generator never blind-resubmits.

    Subclasses the shared package-level reconciliation error so callers
    catching `FlowSubmitReconciledError` (image or video) stay correct.
    """


class FlowVideoInvalidResultError(FlowVideoGenerationError):
    """No candidate passed technical validation; the job is never COMPLETED
    with an invalid candidate set (plan §23.3)."""


@dataclass(frozen=True)
class FlowVideoOutcome:
    """Typed outcome of one video generation run."""

    job: FlowJobRecord
    operation: FlowVideoOperation
    submit_clicked: bool
    reached_state: FlowUiState
    candidates: tuple[VideoCandidateAcquisition, ...] = ()
    mode_issues: tuple[FlowVideoModeIssue, ...] = ()
    pre_submit_evidence_hash: str = ""

    @property
    def ok(self) -> bool:
        return self.submit_clicked and bool(self.candidates)


_CANDIDATE_MARKER_PREFIX = "candidate:"


class FlowVideoGenerator:
    """Orchestrates video generation through the typed Flow UI port."""

    def __init__(
        self,
        *,
        session_id: str,
        project_id: str,
        ui: FlowUiPort,
        navigator: FlowNavigator,
        project_manager: FlowProjectManager,
        project_mapping: FlowProjectMapping,
        guard: PreSubmitGuard,
        job_registry: FlowJobRegistry,
        downloader: VideoCandidateDownloader,
        fetcher: Optional[VideoFetcherPort] = None,
        state_machine: Optional[FlowUiStateMachine] = None,
        mapper: Optional[VideoOperationMapper] = None,
        clock: Optional[callable] = None,
        poll_interval_seconds: float = 0.01,
        poll_deadline_seconds: float = 30.0,
        max_backoff_seconds: float = 0.5,
        # Mode validation (plan §23.2): content hashes of APPROVED assets.
        approved_hashes: frozenset[str] = frozenset(),
        # Fail-closed guard inputs wired from the composition root (§18.1).
        session_healthy: bool = True,
        references_approved: bool = True,
        upload_hash_matches: bool = True,
        test_approved: bool = False,
        # Plan §23.4: local cancellation signal (never asserts provider side).
        cancel_requested: Optional[Callable[[], bool]] = None,
        human_control_manager: Optional[FlowHumanControlManager] = None,
    ) -> None:
        self.session_id = session_id
        self.project_id = project_id
        self.ui = ui
        self.navigator = navigator
        self.project_manager = project_manager
        self.project_mapping = project_mapping
        self.guard = guard
        self.job_registry = job_registry
        self.downloader = downloader
        self.fetcher = fetcher
        self.state_machine = state_machine or FlowUiStateMachine()
        self.mapper = mapper or VideoOperationMapper()
        self._clock = clock or time.time
        self.poll_interval = poll_interval_seconds
        self.poll_deadline = poll_deadline_seconds
        self.max_backoff = max_backoff_seconds
        self.approved_hashes = approved_hashes
        self.session_healthy = session_healthy
        self.references_approved = references_approved
        self.upload_hash_matches = upload_hash_matches
        self.test_approved = test_approved
        self.cancel_requested = cancel_requested
        navigator_manager = getattr(navigator, "human_control_manager", None)
        self.human_control_manager = (
            human_control_manager
            or navigator_manager
            or FlowHumanControlManager(state_dir=str(job_registry.state_dir))
        )
        if hasattr(navigator, "human_control_manager"):
            if (
                navigator_manager is not None
                and navigator_manager is not self.human_control_manager
            ):
                raise ValueError(
                    "navigator and video generator must share one human-control manager"
                )
            navigator.human_control_manager = self.human_control_manager

    # ------------------------------------------------------------------
    def _raise_if_cancelled(self, job: FlowJobRecord) -> None:
        """Local cancellation: stop the poll loop, mark CANCELLED, never
        claim the provider side was cancelled (plan §23.4)."""
        if self.cancel_requested is not None and self.cancel_requested():
            self.job_registry.mark(job.generation_id, FlowJobStatus.CANCELLED)
            raise FlowVideoCancelledError(
                "generation cancelled locally; provider-side cancellation "
                "is not asserted"
            )

    # ------------------------------------------------------------------
    async def generate_video(
        self, request: FlowVideoRequest
    ) -> FlowVideoOutcome:
        """Run the pipeline under one account-safety reservation."""
        automation_token = f"video_{uuid.uuid4().hex}"
        self.human_control_manager.begin_automated_action(
            self.session_id, automation_token
        )
        try:
            return await self._generate_video(request, automation_token)
        finally:
            self.human_control_manager.end_automated_action(
                self.session_id, automation_token
            )

    async def _generate_video(
        self, request: FlowVideoRequest, automation_token: str
    ) -> FlowVideoOutcome:
        """Run the full video generation pipeline (plan 04 §23)."""
        if not self.mapper.supported(request.operation):
            raise FlowVideoGenerationError(
                f"operation {request.operation.value} not supported by provider"
            )

        # 1. Mode validation FIRST — fail closed before any navigation or
        #    submit (plan §23.2).
        issues = self.mapper.validate_mode(
            request, approved_hashes=self.approved_hashes
        )
        if issues:
            raise FlowVideoModeValidationError(
                "video mode validation failed", issues=issues
            )

        # 2. Reconcile the idempotency key (§23.1) — never blind-resubmit.
        decision = self.job_registry.reconcile(
            request_hash=request.request_hash,
            project_id=request.project_id,
            provider="google_flow_browser",
        )
        if decision.action == FlowReconcileAction.RECONCILE_UNKNOWN:
            raise FlowVideoSubmitReconciledError(
                f"job requires reconciliation: {decision.reason}"
            )
        if decision.action == FlowReconcileAction.REUSE_COMPLETED:
            assert decision.record is not None
            # candidate set is intact on the job record; no re-download
            return FlowVideoOutcome(
                job=decision.record,
                operation=request.operation,
                submit_clicked=False,
                reached_state=FlowUiState.RESULT_READY,
                candidates=(),
            )
        if decision.action == FlowReconcileAction.RESUME_ACTIVE:
            assert decision.record is not None
            # Browser/session failure after submit prefers re-inspection of
            # the SAME Flow project (plan §23.4).
            observed = await self.ui.observe()
            current = self.state_machine.classify(observed)
            return FlowVideoOutcome(
                job=decision.record,
                operation=request.operation,
                submit_clicked=False,
                reached_state=current,
                candidates=(),
            )

        # 3. Fresh or new-attempt job (PREPARED).
        if decision.action == FlowReconcileAction.NEW_ATTEMPT:
            assert decision.record is not None
            # Retry creates a NEW attempt with a causal parent link; old
            # receipts are never overwritten (plan §23.4).
            job = self.job_registry.next_attempt(
                decision.record.generation_id, reason="retryable failure"
            )
        else:
            job = self.job_registry.create_prepared(
                generation_id=f"gen_{request.project_id}_{self._clock():.0f}",
                project_id=request.project_id,
                revision_id=request.revision_id,
                shot_id=request.shot_id,
                request_hash=request.request_hash,
                browser_session_id=self.session_id,
                flow_project_id=(
                    self.project_mapping.flow_project_id
                    if self.project_mapping
                    else ""
                ),
            )

        # 4. Navigate to SUBMIT_READY (Phase 13 navigator never submits).
        receipt = await self._navigate_to_submit_ready(automation_token)
        pre_submit_evidence = receipt.pre_submit_evidence_hash

        # 5. Pre-submit guard (fail closed, §18.1 reused for video).
        verdict = self.guard.check(
            request,
            mapping_healthy=self.project_manager.get_mapping(request.project_id)
            is not None,
            session_healthy=self.session_healthy,
            references_approved=self.references_approved,
            upload_hash_matches=self.upload_hash_matches,
            pre_submit_evidence_hash=pre_submit_evidence,
            operation_supported=self.mapper.supported(request.operation),
            cost_allowed=(request.max_cost_credits <= 0.0 or self.test_approved),
        )
        if not verdict.ok:
            raise FlowPreSubmitBlockedError(
                "pre-submit guard blocked", reasons=verdict.reasons
            )

        self._raise_if_cancelled(job)

        # 6. Persist SUBMITTING intent BEFORE the click (§23.1).
        job = self.job_registry.mark(job.generation_id, FlowJobStatus.SUBMITTING)

        # 7. Click submit exactly once with the internal idempotency token.
        await self.ui.act(
            FlowUiAction(
                "submit",
                "submit_generation",
                request.idempotency_token or job.generation_id,
                timeout_seconds=120.0,
            )
        )

        # 8. Observe + poll with backoff + deadline until RESULT_READY (§23.3).
        observed = await self.ui.observe()
        current = self.state_machine.classify(observed)
        deadline = self._clock() + self.poll_deadline
        backoff = self.poll_interval
        while current != FlowUiState.RESULT_READY:
            self._raise_if_cancelled(job)
            if current == FlowUiState.HUMAN_ACTION_REQUIRED:
                raise FlowVideoHumanActionRequiredError(
                    self._record_human_pause(
                        job,
                        observed,
                        safe_resume_state=FlowUiState.GENERATING,
                        reason="Flow required human action while video generation was running",
                    )
                )
            if current == FlowUiState.ERROR:
                job = self.job_registry.mark(
                    job.generation_id, FlowJobStatus.FAILED_TERMINAL
                )
                raise FlowVideoGenerationError("Flow UI reported an error state")
            if current == FlowUiState.UNKNOWN:
                job = self.job_registry.mark(
                    job.generation_id,
                    FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION,
                )
                raise FlowVideoSubmitReconciledError(
                    "UI state unknown; requires reconciliation (no resubmit)"
                )
            if self._clock() >= deadline:
                job = self.job_registry.mark(
                    job.generation_id,
                    FlowJobStatus.UNKNOWN_REQUIRES_RECONCILIATION,
                )
                raise FlowVideoSubmitReconciledError(
                    "poll deadline exceeded; requires reconciliation"
                )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.max_backoff)
            observed = await self.ui.observe()
            current = self.state_machine.classify(observed)

        job = self.job_registry.mark(job.generation_id, FlowJobStatus.RESULT_READY)
        job = self.job_registry.mark(job.generation_id, FlowJobStatus.DOWNLOADING)

        # 9. Acquire EVERY candidate with technical validation (§23.3) —
        #    never default to the first, never COMPLETED with an invalid set.
        candidate_refs = [
            m[len(_CANDIDATE_MARKER_PREFIX):]
            for m in observed.markers
            if m.startswith(_CANDIDATE_MARKER_PREFIX)
        ]
        acquisitions: list[VideoCandidateAcquisition] = []
        candidate_ids: list[str] = []
        for index, ref in enumerate(candidate_refs):
            self._raise_if_cancelled(job)
            # A result/download view can surface an account challenge after
            # generation completes.  Re-observe before every fetch and never
            # download a candidate once control has transferred to a human.
            download_observation = await self.ui.observe()
            if (
                self.state_machine.classify(download_observation)
                == FlowUiState.HUMAN_ACTION_REQUIRED
            ):
                raise FlowVideoHumanActionRequiredError(
                    self._record_human_pause(
                        job,
                        download_observation,
                        safe_resume_state=FlowUiState.RESULT_READY,
                        reason="Flow required human action before video candidate download",
                    )
                )
            try:
                acquired = await self.downloader.acquire(
                    job=job,
                    candidate_id=f"{job.generation_id}c{index}",
                    uri=ref,
                    index=index,
                    fetcher=self.fetcher or _NullFetcher(),
                )
                acquisitions.append(acquired)
                candidate_ids.append(acquired.candidate_id)
            except VideoCandidateInvalidError:
                # invalid candidate: never published, never part of COMPLETED
                continue

        if not candidate_ids:
            job = self.job_registry.mark(
                job.generation_id, FlowJobStatus.FAILED_TERMINAL
            )
            raise FlowVideoInvalidResultError(
                "no video candidate passed technical validation; job not "
                "COMPLETED"
            )

        # COMPLETED only after atomic artifact publish + relationship record
        # (record_candidates sets COMPLETED + candidate_ids atomically).
        job = self.job_registry.record_candidates(job.generation_id, candidate_ids)

        return FlowVideoOutcome(
            job=job,
            operation=request.operation,
            submit_clicked=True,
            reached_state=FlowUiState.RESULT_READY,
            candidates=tuple(acquisitions),
            pre_submit_evidence_hash=pre_submit_evidence,
        )

    async def _navigate_to_submit_ready(self, automation_token: str):
        """Pass the parent safety lease to a real navigator when available."""
        if isinstance(self.navigator, FlowNavigator):
            return await self.navigator.navigate_to_submit_ready(
                automation_token=automation_token
            )
        return await self.navigator.navigate_to_submit_ready()

    def _record_human_pause(
        self,
        job: FlowJobRecord,
        observed,
        *,
        safe_resume_state: FlowUiState,
        reason: str,
    ) -> FlowHumanActionRecord:
        self.job_registry.mark(job.generation_id, FlowJobStatus.HUMAN_ACTION_REQUIRED)
        return self.human_control_manager.create_or_get_human_action(
            session_id=self.session_id,
            project_id=self.project_id,
            human_state=(
                FlowHumanControlDetector.detect(
                    observed, expected_state=safe_resume_state
                )
                or FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED
            ),
            reason=reason,
            safe_resume_state=safe_resume_state,
            raw_evidence=observed.to_dict(),
            generation_id=job.generation_id,
        )


class _NullFetcher:
    """Fails deterministically when no fetcher is configured."""

    async def fetch(self, uri: str) -> bytes:
        raise RuntimeError(f"no video candidate fetcher configured for {uri!r}")


__all__ = [
    "FlowVideoCancelledError",
    "FlowVideoGenerationError",
    "FlowVideoGenerator",
    "FlowVideoHumanActionRequiredError",
    "FlowVideoInvalidResultError",
    "FlowVideoModeValidationError",
    "FlowVideoOutcome",
    "FlowVideoSubmitReconciledError",
]
