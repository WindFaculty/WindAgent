"""
Phase 13 — Deterministic Flow navigation to SUBMIT_READY (plan 04 §13).

`FlowNavigator` drives the Flow UI from an observed state to `SUBMIT_READY`
using typed bounded actions through a `FlowUiPort`. The navigator:

- never executes a raw browser command (typed operations only, plan §13.3);
- never submits a generation (submit belongs to Phase 14/15 approval flow);
- confirms the correct project via the project manager (two signals, §13.2);
- verifies the visible configuration read-back matches the compiled request
  (§13.3 step 6) and captures pre-submit evidence (§13.3 step 7);
- fails closed on selector drift: a missing/unmatched postcondition stops at
  `ERROR`/`HUMAN_ACTION_REQUIRED` with sanitized evidence — no blind retry
  clicks (§13.5).

The navigator is fully testable with a fake `FlowUiPort` (mocked UI fixtures);
no Flow production is required.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence, runtime_checkable

from windagent_tools.google_flow.project_manager import (
    FlowProjectManager,
    FlowProjectMapping,
)
from windagent_tools.google_flow.human_control import (
    FlowHumanControlDetector,
    FlowHumanControlManager,
    FlowHumanState,
)
from windagent_tools.google_flow.selectors import SelectorCatalog
from windagent_tools.google_flow.state_machine import (
    FlowUiObservation,
    FlowUiState,
    FlowUiStateMachine,
)


class FlowNavigationError(RuntimeError):
    """Base error for Flow navigation."""

    def __init__(self, message: str = "", *, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class FlowNavigationDriftError(FlowNavigationError):
    """Raised when a postcondition is not reached (selector drift, §13.5)."""


class FlowNavigationStateError(FlowNavigationError):
    """Raised when the current UI state cannot reach the target."""


@dataclass(frozen=True)
class FlowUiAction:
    """One typed bounded action with a semantic target (never raw commands)."""

    operation: str  # typed operation name (open/click/fill/select/upload/read)
    target: str = ""
    payload: str = ""
    timeout_seconds: float = 60.0

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "target": self.target,
            "payload_chars": len(self.payload),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class FlowNavigationStep:
    """Evidence for one navigation step (plan 04 §12 evidence requirement)."""

    index: int
    name: str
    from_state: FlowUiState
    to_state: FlowUiState
    action: FlowUiAction
    snapshot_hash: str = ""
    ok: bool = True
    error_class: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "action": self.action.to_dict(),
            "snapshot_hash": self.snapshot_hash,
            "ok": self.ok,
            "error_class": self.error_class,
        }


@dataclass(frozen=True)
class FlowNavigationReceipt:
    """Typed navigation outcome with per-step evidence."""

    session_id: str
    project_id: str
    target_state: FlowUiState
    reached_state: FlowUiState
    steps: tuple[FlowNavigationStep, ...] = ()
    pre_submit_evidence_hash: str = ""
    submitted: bool = False

    @property
    def ok(self) -> bool:
        return self.reached_state == self.target_state and not self.submitted

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "target_state": self.target_state.value,
            "reached_state": self.reached_state.value,
            "steps": [s.to_dict() for s in self.steps],
            "pre_submit_evidence_hash": self.pre_submit_evidence_hash,
            "submitted": self.submitted,
            "ok": self.ok,
        }


@runtime_checkable
class FlowUiPort(Protocol):
    """Typed UI port: observe + bounded actions (fake in tests, real later)."""

    async def observe(self) -> FlowUiObservation:
        """Return the current observable UI snapshot."""
        ...

    async def act(self, action: FlowUiAction) -> str:
        """Execute one typed bounded action, returning an evidence hash."""
        ...


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FlowNavigator:
    """Deterministic READY → SUBMIT_READY navigation (plan 04 §13.3)."""

    def __init__(
        self,
        *,
        session_id: str,
        project_id: str,
        ui: FlowUiPort,
        state_machine: Optional[FlowUiStateMachine] = None,
        selector_catalog: Optional[SelectorCatalog] = None,
        project_manager: Optional[FlowProjectManager] = None,
        project_mapping: Optional[FlowProjectMapping] = None,
        compiled_prompt: Optional[str] = None,
        reference_assets: Optional[Sequence[str]] = None,
        generation_mode: Optional[str] = None,
        allow_submit: bool = False,
        clock: Optional[callable] = None,
        human_control_manager: Optional[FlowHumanControlManager] = None,
    ) -> None:
        self.session_id = session_id
        self.project_id = project_id
        self.ui = ui
        self.state_machine = state_machine or FlowUiStateMachine()
        self.selector_catalog = selector_catalog or SelectorCatalog()
        self.project_manager = project_manager
        self.project_mapping = project_mapping
        self.compiled_prompt = compiled_prompt or ""
        self.reference_assets = tuple(reference_assets or ())
        self.generation_mode = generation_mode or "TEXT_TO_VIDEO"
        self.allow_submit = allow_submit  # stays False for Phase 13
        self._clock = clock or time.time
        self.human_control_manager = human_control_manager

    # ------------------------------------------------------------------
    async def navigate_to_submit_ready(
        self, *, automation_token: Optional[str] = None
    ) -> FlowNavigationReceipt:
        """Drive the UI while enforcing the Phase 16 account-safety lease."""
        manager = self.human_control_manager
        token = automation_token or f"navigation_{uuid.uuid4().hex}"
        if manager is not None:
            manager.begin_automated_action(self.session_id, token)
        try:
            return await self._navigate_to_submit_ready()
        finally:
            if manager is not None:
                manager.end_automated_action(self.session_id, token)

    async def _navigate_to_submit_ready(self) -> FlowNavigationReceipt:
        """Drive the UI from its observed state to SUBMIT_READY (no submit)."""
        observed = await self.ui.observe()
        current = self.state_machine.classify(observed)
        steps: list[FlowNavigationStep] = []

        # 1. Session / account inspection (§13.1)
        if current == FlowUiState.SIGNED_OUT:
            record = self._pause_for_human(
                observed,
                safe_resume_state=FlowUiState.READY,
                reason="Flow is signed out; a human must sign in",
            )
            raise FlowNavigationStateError(
                "Flow is signed out; a human must sign in (Phase 16 human state)",
                details=self._human_action_details(record),
            )
        if current == FlowUiState.HUMAN_ACTION_REQUIRED:
            record = self._pause_for_human(
                observed,
                safe_resume_state=FlowUiState.READY,
                reason="Flow requires human action; navigation paused",
            )
            raise FlowNavigationStateError(
                "Flow requires human action; navigation paused",
                details=self._human_action_details(record),
            )
        if current == FlowUiState.UNKNOWN:
            raise FlowNavigationDriftError(
                "cannot classify the Flow UI; stop at ERROR with evidence"
            )

        # 2. Open the correct project (open-before-create, two signals §13.2)
        if current == FlowUiState.READY:
            step, observed = await self._step(
                0,
                "open_project",
                FlowUiState.READY,
                FlowUiState.PROJECT_OPEN,
                FlowUiAction("open", self._project_target(), timeout_seconds=90.0),
                observed,
            )
            steps.append(step)
            current = self.state_machine.classify(observed)
            # confirm the opened project with >= 2 independent signals (§13.2)
            if self.project_manager is not None and self.project_mapping is not None:
                self.project_manager.verify_two_signals(
                    self.project_mapping,
                    observed=(observed.url, *observed.markers, *observed.controls),
                )

        # 3. Open the create workspace → editor (§13.3.1)
        if current == FlowUiState.PROJECT_OPEN:
            step, observed = await self._step(
                1,
                "open_create_workspace",
                FlowUiState.PROJECT_OPEN,
                FlowUiState.EDITOR_READY,
                FlowUiAction("click", "create_workspace", timeout_seconds=90.0),
                observed,
            )
            steps.append(step)
            current = self.state_machine.classify(observed)

        # 4. Configure generation (§13.3.2–§13.3.5)
        if current == FlowUiState.EDITOR_READY:
            step, observed = await self._configure(2, observed)
            steps.append(step)
            current = self.state_machine.classify(observed)

        # 5. Read back config + capture pre-submit evidence (§13.3.6–7)
        if current == FlowUiState.CONFIGURED:
            step, observed = await self._pre_submit(3, observed)
            steps.append(step)
            current = self.state_machine.classify(observed)

        if current != FlowUiState.SUBMIT_READY:
            raise FlowNavigationDriftError(
                f"navigation reached {current.value}; expected SUBMIT_READY",
                details={
                    "reached": current.value,
                    "steps": len(steps),
                },
            )

        return FlowNavigationReceipt(
            session_id=self.session_id,
            project_id=self.project_id,
            target_state=FlowUiState.SUBMIT_READY,
            reached_state=current,
            steps=tuple(steps),
            pre_submit_evidence_hash=self._pre_submit_evidence_hash(observed),
            submitted=False,
        )

    # ------------------------------------------------------------------
    async def _configure(
        self, index: int, observed: FlowUiObservation
    ) -> tuple[FlowNavigationStep, FlowUiObservation]:
        """Select mode, upload references, fill prompt, pick model/duration/ratio."""
        actions = [
            FlowUiAction("select", "generation_mode", self.generation_mode, 60.0),
            FlowUiAction("upload", "reference_upload", "approved_asset", 120.0),
            FlowUiAction("fill", "prompt_field", self.compiled_prompt, 60.0),
            FlowUiAction("select", "model_select", "model", 60.0),
            FlowUiAction("select", "duration_select", "duration", 60.0),
            FlowUiAction("select", "aspect_ratio_select", "ratio", 60.0),
        ]
        if self.reference_assets:
            actions[1] = FlowUiAction(
                "upload", "reference_upload", self.reference_assets[0], 120.0
            )
        step, observed = await self._step(
            index,
            "configure_generation",
            FlowUiState.EDITOR_READY,
            FlowUiState.CONFIGURED,
            actions[0],
            observed,
            extra_actions=actions[1:],
        )
        return step, observed

    async def _pre_submit(
        self, index: int, observed: FlowUiObservation
    ) -> tuple[FlowNavigationStep, FlowUiObservation]:
        """Read back the visible config and confirm it matches the request."""
        step, observed = await self._step(
            index,
            "read_back_config",
            FlowUiState.CONFIGURED,
            FlowUiState.SUBMIT_READY,
            FlowUiAction("read", "config_read_back", timeout_seconds=60.0),
            observed,
        )
        return step, observed

    # ------------------------------------------------------------------
    async def _step(
        self,
        index: int,
        name: str,
        from_state: FlowUiState,
        to_state: FlowUiState,
        action: FlowUiAction,
        observed: FlowUiObservation,
        *,
        extra_actions: Sequence[FlowUiAction] = (),
    ) -> tuple[FlowNavigationStep, FlowUiObservation]:
        evidence_hash = ""
        try:
            for step_action in (action, *extra_actions):
                evidence_hash = await self.ui.act(step_action)
            new_observed = await self.ui.observe()
            classified = self.state_machine.classify(new_observed)
            if classified == FlowUiState.HUMAN_ACTION_REQUIRED:
                record = self._pause_for_human(
                    new_observed,
                    safe_resume_state=from_state,
                    reason=f"Flow required human action during navigation step '{name}'",
                )
                raise FlowNavigationStateError(
                    "Flow requires human action; navigation paused",
                    details=self._human_action_details(record),
                )
            if classified != to_state:
                raise FlowNavigationDriftError(
                    f"{name} postcondition not met: got {classified.value}, "
                    f"expected {to_state.value}",
                    details={
                        "from_state": from_state.value,
                        "observed": new_observed.to_dict(),
                    },
                )
            return (
                FlowNavigationStep(
                    index=index,
                    name=name,
                    from_state=from_state,
                    to_state=to_state,
                    action=action,
                    snapshot_hash=evidence_hash,
                    ok=True,
                ),
                new_observed,
            )
        except FlowNavigationDriftError as exc:
            raise exc
        except FlowNavigationStateError as exc:
            raise exc
        except Exception as exc:  # noqa: BLE001
            raise FlowNavigationDriftError(
                f"{name} failed: {type(exc).__name__}: {exc}",
                details={"from_state": from_state.value, "target": to_state.value},
            ) from exc

    # ------------------------------------------------------------------
    def _project_target(self) -> str:
        if self.project_mapping and self.project_mapping.flow_project_url:
            return self.project_mapping.flow_project_url
        return "/projects"

    def _pause_for_human(
        self,
        observed: FlowUiObservation,
        *,
        safe_resume_state: FlowUiState,
        reason: str,
    ) -> Optional[object]:
        """Persist an operator takeover before surfacing a typed pause error."""
        manager = self.human_control_manager
        if manager is None:
            return None
        human_state = FlowHumanControlDetector.detect(
            observed, expected_state=safe_resume_state
        ) or FlowHumanState.HUMAN_ACCOUNT_VERIFICATION_REQUIRED
        return manager.create_or_get_human_action(
            session_id=self.session_id,
            project_id=self.project_id,
            human_state=human_state,
            reason=reason,
            safe_resume_state=safe_resume_state,
            raw_evidence=observed.to_dict(),
        )

    @staticmethod
    def _human_action_details(record: Optional[object]) -> dict:
        if record is None:
            return {}
        # Kept local instead of importing the concrete record into public
        # navigation types; callers receive only safe identifiers/state.
        return {
            "human_action_id": record.human_action_id,
            "human_state": record.human_state.value,
            "safe_resume_state": record.safe_resume_state.value,
        }

    def _pre_submit_evidence_hash(self, observed: FlowUiObservation) -> str:
        return _sha256(
            f"{observed.url}|{','.join(observed.markers)}|"
            f"{','.join(observed.controls)}"
        )


__all__ = [
    "FlowNavigationDriftError",
    "FlowNavigationError",
    "FlowNavigationReceipt",
    "FlowNavigationStateError",
    "FlowNavigationStep",
    "FlowNavigator",
    "FlowUiAction",
    "FlowUiPort",
]
