"""
Phase 13 — Flow UI state machine (plan 04 §12).

Models the observable Google Flow UI as a typed state machine:

    UNKNOWN → SIGNED_OUT → READY → PROJECT_OPEN → EDITOR_READY →
    CONFIGURED → SUBMIT_READY → GENERATING → RESULT_READY
                                     ↘ ERROR / HUMAN_ACTION_REQUIRED

Every transition carries an observable precondition, a bounded action, an
observable postcondition, a timeout, a retry classification, evidence, and a
recovery/human state (plan 04 §12).

Classification never relies on a single selector: a state is inferred from the
URL + semantic markers + visible controls together. The machine is
deterministic and fully offline — no browser or network call happens while
classifying.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FlowUiState(str, Enum):
    UNKNOWN = "UNKNOWN"
    SIGNED_OUT = "SIGNED_OUT"
    READY = "READY"
    PROJECT_OPEN = "PROJECT_OPEN"
    EDITOR_READY = "EDITOR_READY"
    CONFIGURED = "CONFIGURED"
    SUBMIT_READY = "SUBMIT_READY"
    GENERATING = "GENERATING"
    RESULT_READY = "RESULT_READY"
    ERROR = "ERROR"
    HUMAN_ACTION_REQUIRED = "HUMAN_ACTION_REQUIRED"


class FlowRetryClassification(str, Enum):
    RETRYABLE = "RETRYABLE"  # transient: can retry the same bounded action
    NOT_RETRYABLE = "NOT_RETRYABLE"  # deterministic: fail closed, no blind retry


@dataclass(frozen=True)
class FlowUiObservation:
    """One observable snapshot of the Flow UI (plan 04 §12)."""

    url: str = ""
    markers: tuple[str, ...] = ()  # semantic text markers / headings / labels
    controls: tuple[str, ...] = ()  # visible control semantics (role:label)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "markers": list(self.markers),
            "controls": list(self.controls),
        }


@dataclass(frozen=True)
class FlowStateTransition:
    """One typed transition in the Flow UI state machine (plan 04 §12)."""

    name: str
    from_state: FlowUiState
    to_state: FlowUiState
    precondition: str  # observable precondition
    bounded_action: str  # typed bounded action name (never a raw command)
    postcondition: str  # observable postcondition
    timeout_seconds: float = 60.0
    retry_classification: FlowRetryClassification = FlowRetryClassification.NOT_RETRYABLE
    evidence: str = "snapshot_hash"
    recovery_state: Optional[FlowUiState] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "from": self.from_state.value,
            "to": self.to_state.value,
            "precondition": self.precondition,
            "bounded_action": self.bounded_action,
            "postcondition": self.postcondition,
            "timeout_seconds": self.timeout_seconds,
            "retry_classification": self.retry_classification.value,
            "evidence": self.evidence,
            "recovery_state": self.recovery_state.value if self.recovery_state else None,
        }


class FlowUiStateMachine:
    """Deterministic Flow UI state machine with observable signals.

    `classify` returns a state inferred from *all* observable signals (URL +
    markers + visible controls). Rules are ordered most-specific first.
    """

    # Canonical Flow domain; signed-out and signed-in pages share the domain.
    FLOW_DOMAIN = "flow.google.com"
    SIGN_IN_MARKERS = ("Sign in", "Sign in with Google", "Welcome")
    CHALLENGE_MARKERS = ("Verification", "Verify you are human", "captcha")
    PAYMENT_MARKERS = ("Payment", "Checkout", "Buy credits", "Upgrade")

    def __init__(self) -> None:
        self._transitions: dict[str, FlowStateTransition] = {
            t.name: t for t in self._build_transitions()
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _build_transitions() -> list[FlowStateTransition]:
        return [
            FlowStateTransition(
                name="signed_out_to_ready",
                from_state=FlowUiState.SIGNED_OUT,
                to_state=FlowUiState.READY,
                precondition="signed-in home with create/import controls visible",
                bounded_action="account_ready_check",
                postcondition="ready home visible",
                retry_classification=FlowRetryClassification.NOT_RETRYABLE,
            ),
            FlowStateTransition(
                name="ready_to_project_open",
                from_state=FlowUiState.READY,
                to_state=FlowUiState.PROJECT_OPEN,
                precondition="known flow project url or stable locator",
                bounded_action="open_project",
                postcondition="project canvas visible",
                timeout_seconds=90.0,
                retry_classification=FlowRetryClassification.RETRYABLE,
            ),
            FlowStateTransition(
                name="ready_to_project_new",
                from_state=FlowUiState.READY,
                to_state=FlowUiState.PROJECT_OPEN,
                precondition="no existing project mapping; create workspace",
                bounded_action="create_project",
                postcondition="new project canvas visible",
                timeout_seconds=120.0,
                retry_classification=FlowRetryClassification.NOT_RETRYABLE,
            ),
            FlowStateTransition(
                name="project_open_to_editor_ready",
                from_state=FlowUiState.PROJECT_OPEN,
                to_state=FlowUiState.EDITOR_READY,
                precondition="project canvas open; create workspace button visible",
                bounded_action="open_create_workspace",
                postcondition="generation editor visible",
                timeout_seconds=90.0,
                retry_classification=FlowRetryClassification.RETRYABLE,
            ),
            FlowStateTransition(
                name="editor_ready_to_configured",
                from_state=FlowUiState.EDITOR_READY,
                to_state=FlowUiState.CONFIGURED,
                precondition="editor ready; mode/reference/prompt controls visible",
                bounded_action="configure_generation",
                postcondition="visible config matches the compiled request",
                timeout_seconds=120.0,
                retry_classification=FlowRetryClassification.NOT_RETRYABLE,
            ),
            FlowStateTransition(
                name="configured_to_submit_ready",
                from_state=FlowUiState.CONFIGURED,
                to_state=FlowUiState.SUBMIT_READY,
                precondition="config read-back matches request; pre-submit evidence captured",
                bounded_action="read_back_config",
                postcondition="submit control visible and enabled",
                timeout_seconds=60.0,
                retry_classification=FlowRetryClassification.NOT_RETRYABLE,
            ),
            FlowStateTransition(
                name="submit_ready_to_generating",
                from_state=FlowUiState.SUBMIT_READY,
                to_state=FlowUiState.GENERATING,
                precondition="explicit submit approval and idempotency token",
                bounded_action="submit_generation",
                postcondition="generating/progress state visible",
                timeout_seconds=120.0,
                retry_classification=FlowRetryClassification.NOT_RETRYABLE,
            ),
            FlowStateTransition(
                name="generating_to_result_ready",
                from_state=FlowUiState.GENERATING,
                to_state=FlowUiState.RESULT_READY,
                precondition="job completed; result surface visible",
                bounded_action="poll_result",
                postcondition="result candidates visible",
                timeout_seconds=600.0,
                retry_classification=FlowRetryClassification.RETRYABLE,
            ),
        ]

    # ------------------------------------------------------------------
    def transitions(self) -> list[FlowStateTransition]:
        return sorted(self._transitions.values(), key=lambda t: t.name)

    def transition(self, name: str) -> FlowStateTransition:
        return self._transitions[name]

    def allowed_from(self, state: FlowUiState) -> list[FlowStateTransition]:
        return [t for t in self.transitions() if t.from_state == state]

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def classify(self, observation: FlowUiObservation) -> FlowUiState:
        """Classify the UI state from URL + markers + visible controls.

        Rules are applied most-specific first. No single signal decides a
        state (plan 04 §12: never infer from one selector).
        """
        url = (observation.url or "").lower()
        markers = " ".join(observation.markers).lower()
        controls = " ".join(observation.controls).lower()

        if self._is_human_required(observation):
            return FlowUiState.HUMAN_ACTION_REQUIRED
        if self._is_error(observation):
            return FlowUiState.ERROR
        if self._is_signed_out(url, markers, controls):
            return FlowUiState.SIGNED_OUT
        if self._is_result_ready(url, markers, controls):
            return FlowUiState.RESULT_READY
        if self._is_generating(url, markers, controls):
            return FlowUiState.GENERATING
        if self._is_submit_ready(url, markers, controls):
            return FlowUiState.SUBMIT_READY
        if self._is_configured(url, markers, controls):
            return FlowUiState.CONFIGURED
        if self._is_editor_ready(url, markers, controls):
            return FlowUiState.EDITOR_READY
        if self._is_project_open(url, markers, controls):
            return FlowUiState.PROJECT_OPEN
        if self._is_ready(url, markers, controls):
            return FlowUiState.READY
        return FlowUiState.UNKNOWN

    # ------------------------------------------------------------------
    # Signal rules (multi-signal: URL + markers + controls where possible)
    # ------------------------------------------------------------------
    @staticmethod
    def _is_human_required(observation: FlowUiObservation) -> bool:
        joined = " ".join(observation.markers).lower()
        return any(m in joined for m in ("captcha", "verify you are human", "check your email"))

    @staticmethod
    def _is_error(observation: FlowUiObservation) -> bool:
        joined = " ".join(observation.markers).lower()
        controls = " ".join(observation.controls).lower()
        return ("error" in joined or "something went wrong" in joined) and "retry" in controls

    @staticmethod
    def _is_signed_out(url: str, markers: str, controls: str) -> bool:
        if FlowUiStateMachine.FLOW_DOMAIN not in url:
            return False
        has_sign_in = any(m in markers for m in ("sign in", "sign in with google"))
        has_welcome = "welcome" in markers
        return has_sign_in or (has_welcome and "create" not in controls)

    @staticmethod
    def _is_result_ready(url: str, markers: str, controls: str) -> bool:
        return ("result" in markers or "candidates" in markers) and "download" in controls

    @staticmethod
    def _is_generating(url: str, markers: str, controls: str) -> bool:
        return "generating" in markers or "in progress" in markers

    @staticmethod
    def _is_configured(url: str, markers: str, controls: str) -> bool:
        """Config is set but editing controls are still visible."""
        has_editor_controls = "combobox" in controls or "textbox" in controls
        return (
            "configured" in markers or "configuration" in markers
        ) and (
            "submit" in controls or "generate" in controls
        ) and has_editor_controls

    @staticmethod
    def _is_submit_ready(url: str, markers: str, controls: str) -> bool:
        """Config read-back done: submit control visible, editing controls gone."""
        has_submit = "submit" in controls or "generate" in controls
        has_editor_controls = "combobox" in controls or "textbox" in controls
        return has_submit and not has_editor_controls and (
            "configured" in markers or "configuration" in markers
        )

    @staticmethod
    def _is_editor_ready(url: str, markers: str, controls: str) -> bool:
        return "editor" in url and (
            "create" in markers
            or "workspace" in controls
            or "combobox" in controls
            or "textbox" in controls
        )

    @staticmethod
    def _is_project_open(url: str, markers: str, controls: str) -> bool:
        return ("project" in url or "projects" in url) and (
            "create" in markers or "canvas" in markers or "open" in controls
        )

    @staticmethod
    def _is_ready(url: str, markers: str, controls: str) -> bool:
        return FlowUiStateMachine.FLOW_DOMAIN in url and (
            "create" in controls or "new project" in markers or "import" in controls
        )


__all__ = [
    "FlowRetryClassification",
    "FlowStateTransition",
    "FlowUiObservation",
    "FlowUiState",
    "FlowUiStateMachine",
]
