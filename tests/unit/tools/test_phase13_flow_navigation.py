"""Phase 13 — Flow navigation & project management unit tests (plan 04 §11–§15).

Covers: UI state machine classification (11 states, multi-signal), selector
catalog (semantic-first, versioned, no destructive fallback), project mapping
(two-signal verification, open-before-create, display-name not identity,
missing → typed failure), and deterministic navigation READY → SUBMIT_READY
(never submits, drift fail-closed, pre-submit read-back) — all with a
scripted fake UI, no Flow production.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from windagent_tools.google_flow import (
    FlowNavigationDriftError,
    FlowNavigationStateError,
    FlowHumanActionBlockedError,
    FlowHumanActionStatus,
    FlowHumanControlManager,
    FlowHumanState,
    FlowNavigator,
    FlowProjectManager,
    FlowProjectMappingStatus,
    FlowProjectMissingError,
    FlowProjectVerificationError,
    FlowUiObservation,
    FlowUiState,
    FlowUiStateMachine,
    SelectorCatalog,
    SelectorKind,
)


# ---------------------------------------------------------------------------
# State machine classification
# ---------------------------------------------------------------------------
def test_state_machine_has_all_states_and_transitions():
    sm = FlowUiStateMachine()
    states = {s.value for s in FlowUiState}
    assert len(states) == 11
    for expected in (
        "UNKNOWN",
        "SIGNED_OUT",
        "READY",
        "PROJECT_OPEN",
        "EDITOR_READY",
        "CONFIGURED",
        "SUBMIT_READY",
        "GENERATING",
        "RESULT_READY",
        "ERROR",
        "HUMAN_ACTION_REQUIRED",
    ):
        assert expected in states
    transitions = sm.transitions()
    assert len(transitions) >= 8
    for t in transitions:
        assert t.precondition and t.bounded_action and t.postcondition
        assert t.timeout_seconds > 0
        assert t.retry_classification.value in ("RETRYABLE", "NOT_RETRYABLE")
        assert t.evidence


def test_state_machine_classify_ready():
    sm = FlowUiStateMachine()
    state = sm.classify(
        FlowUiObservation(
            url="https://flow.google.com/",
            markers=("Welcome back",),
            controls=("button:Create", "button:Import"),
        )
    )
    assert state == FlowUiState.READY


def test_state_machine_classify_signed_out():
    sm = FlowUiStateMachine()
    state = sm.classify(
        FlowUiObservation(
            url="https://flow.google.com/",
            markers=("Sign in with Google", "Welcome"),
            controls=("button:Sign in",),
        )
    )
    assert state == FlowUiState.SIGNED_OUT


def test_state_machine_classify_submit_ready():
    sm = FlowUiStateMachine()
    state = sm.classify(
        FlowUiObservation(
            url="https://flow.google.com/projects/p1/editor",
            markers=("Configured",),
            controls=("button:Generate",),
        )
    )
    assert state == FlowUiState.SUBMIT_READY


def test_state_machine_classify_human_required():
    sm = FlowUiStateMachine()
    state = sm.classify(
        FlowUiObservation(
            url="https://flow.google.com/",
            markers=("Verify you are human",),
            controls=(),
        )
    )
    assert state == FlowUiState.HUMAN_ACTION_REQUIRED


def test_state_machine_never_single_signal():
    """URL alone must not decide a state (plan 04 §12)."""
    sm = FlowUiStateMachine()
    state = sm.classify(FlowUiObservation(url="https://flow.google.com/projects"))
    assert state == FlowUiState.UNKNOWN  # no markers/controls -> unknown


# ---------------------------------------------------------------------------
# Selector catalog
# ---------------------------------------------------------------------------
def test_selector_catalog_semantic_only():
    catalog = SelectorCatalog()
    kinds = {e.kind for e in catalog.entries()}
    assert kinds <= {SelectorKind.ROLE, SelectorKind.LABEL, SelectorKind.TEXT,
                     SelectorKind.URL, SelectorKind.REGION}
    assert "css_class" not in {e.kind.value for e in catalog.entries()}


def test_selector_catalog_forbids_destructive_fallback_auto_click():
    catalog = SelectorCatalog()
    payment = catalog.get("payment_confirm")
    assert payment.destructive is True


def test_selector_catalog_version_and_locale():
    catalog = SelectorCatalog(version="2.0.0", locale="vi")
    assert catalog.version == "2.0.0"
    assert catalog.locale == "vi"


def test_selector_catalog_unknown_raises():
    catalog = SelectorCatalog()
    with pytest.raises(Exception):
        catalog.get("no_such_selector")


# ---------------------------------------------------------------------------
# Project mapping
# ---------------------------------------------------------------------------
def test_project_manager_two_signal_verification(tmp_path):
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    verified = pm.verify_two_signals(
        mapping, observed=("fp_123", "https://flow.google.com/projects/fp_123")
    )
    assert verified.mapping_status == FlowProjectMappingStatus.VERIFIED
    # survives reload
    reloaded = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    got = reloaded.get_mapping("vp_1")
    assert got.mapping_status == FlowProjectMappingStatus.VERIFIED


def test_project_manager_one_signal_rejected(tmp_path):
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    with pytest.raises(FlowProjectVerificationError):
        pm.verify_two_signals(mapping, observed=("fp_123",))


def test_project_manager_display_name_not_identity(tmp_path):
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
        display_name="My Cool Video",
    )
    with pytest.raises(FlowProjectVerificationError):
        pm.verify_two_signals(mapping, observed=("My Cool Video",))


def test_project_manager_missing_is_typed_failure(tmp_path):
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    pm.mark_missing("vp_1")
    with pytest.raises(FlowProjectMissingError):
        pm.open_before_create("vp_1", observed=("fp_123", "https://flow.google.com/projects/fp_123"))


# ---------------------------------------------------------------------------
# Navigation (scripted fake UI)
# ---------------------------------------------------------------------------
class ScriptedUi:
    """Scripted fake UI: returns observations per state, records actions.

    `act` marks the next `observe` to advance to the postcondition observation
    of the current step. Several actions inside one step (configure runs six
    typed actions) share a single postcondition observation, so the index is
    advanced per step, not per action.
    """

    def __init__(self, script: list[FlowUiObservation]) -> None:
        self.script = script
        self.index = 0
        self.pending_advance = False
        self.actions: list[str] = []
        self.reject_upload_path: str | None = None

    async def observe(self) -> FlowUiObservation:
        if self.pending_advance:
            self.pending_advance = False
            self.index = min(self.index + 1, len(self.script) - 1)
        return self.script[self.index]

    async def act(self, action) -> str:
        self.actions.append(action.operation)
        if (
            action.operation == "upload"
            and self.reject_upload_path
            and action.payload.startswith(self.reject_upload_path)
        ):
            raise FlowNavigationDriftError(
                "unapproved upload path blocked", details={"path": action.payload}
            )
        self.pending_advance = True
        return "ev_" + action.operation


def _ready_script():
    return [
        # initial observation: READY
        FlowUiObservation(
            url="https://flow.google.com/",
            markers=("Welcome back",),
            controls=("button:Create", "button:Import"),
        ),
        # after open_project: PROJECT_OPEN
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123",
            markers=("Project canvas", "Create workspace"),
            controls=("button:Create workspace",),
        ),
        # after open_create_workspace: EDITOR_READY
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Create",),
            controls=("combobox:generation_mode", "textbox:prompt", "button:Generate"),
        ),
        # after configure: CONFIGURED
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Configured",),
            controls=("combobox:generation_mode", "textbox:prompt", "button:Generate"),
        ),
        # after read_back: SUBMIT_READY
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Configured",),
            controls=("button:Generate",),
        ),
    ]


def _navigator(
    tmp_path: Path,
    ui,
    *,
    project_mapping=None,
    reference_assets=None,
    human_control_manager=None,
):
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    mapping = project_mapping or pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    return FlowNavigator(
        session_id="sess_1",
        project_id="vp_1",
        ui=ui,
        project_manager=pm,
        project_mapping=mapping,
        compiled_prompt="A short cartoon about a cat",
        reference_assets=reference_assets or ("approved://assets/cat.png",),
        generation_mode="TEXT_TO_VIDEO",
        human_control_manager=human_control_manager,
    )


def test_navigation_reaches_submit_ready_without_submitting(tmp_path):
    ui = ScriptedUi(_ready_script())
    nav = _navigator(tmp_path, ui)
    receipt = asyncio.run(nav.navigate_to_submit_ready())
    assert receipt.reached_state == FlowUiState.SUBMIT_READY
    assert receipt.target_state == FlowUiState.SUBMIT_READY
    assert receipt.submitted is False
    assert receipt.ok is True
    assert len(receipt.steps) == 4
    assert receipt.pre_submit_evidence_hash
    # the fake UI must never have been asked to submit
    assert "submit" not in ui.actions


def test_navigation_signed_out_is_typed_error(tmp_path):
    ui = ScriptedUi(
        [
            FlowUiObservation(
                url="https://flow.google.com/",
                markers=("Sign in with Google", "Welcome"),
                controls=("button:Sign in",),
            )
        ]
    )
    nav = _navigator(tmp_path, ui)
    with pytest.raises(FlowNavigationStateError):
        asyncio.run(nav.navigate_to_submit_ready())


def test_navigation_challenge_creates_durable_human_takeover(tmp_path):
    manager = FlowHumanControlManager(state_dir=str(tmp_path))
    ui = ScriptedUi(
        [
            FlowUiObservation(
                url="https://flow.google.com/",
                markers=("Verify you are human",),
                controls=("button:Continue",),
            )
        ]
    )
    nav = _navigator(tmp_path, ui, human_control_manager=manager)
    with pytest.raises(FlowNavigationStateError) as exc_info:
        asyncio.run(nav.navigate_to_submit_ready())

    action_id = exc_info.value.details["human_action_id"]
    record = manager.get_record(action_id)
    assert record is not None
    assert record.human_state == FlowHumanState.HUMAN_CAPTCHA_REQUIRED
    assert record.status == FlowHumanActionStatus.PENDING
    with pytest.raises(FlowHumanActionBlockedError):
        manager.assert_session_active("sess_1")

    # Restarting the manager must retain the pause, not accidentally allow a
    # second automation process to operate the same browser session.
    reloaded = FlowHumanControlManager(state_dir=str(tmp_path))
    assert reloaded.get_record(action_id).status == FlowHumanActionStatus.PENDING
    with pytest.raises(FlowHumanActionBlockedError):
        reloaded.assert_session_active("sess_1")


def test_navigation_drift_fails_closed(tmp_path):
    """Postcondition mismatch stops navigation; no blind retry."""
    script = _ready_script()
    # make the post-open observation NOT project-open (drift)
    script[1] = FlowUiObservation(
        url="https://flow.google.com/projects/OTHER",
        markers=("Welcome back",),
        controls=("button:Create",),
    )
    ui = ScriptedUi(script)
    nav = _navigator(tmp_path, ui)
    with pytest.raises(FlowNavigationDriftError):
        asyncio.run(nav.navigate_to_submit_ready())
    # exactly one open action attempted — no blind retry clicks
    assert ui.actions.count("open") == 1


def test_navigation_unapproved_upload_blocked(tmp_path):
    """An unapproved upload path is rejected at the port boundary."""
    ui = ScriptedUi(_ready_script())
    ui.reject_upload_path = "/unapproved/"
    nav = _navigator(tmp_path, ui, reference_assets=("/unapproved/secret.png",))
    with pytest.raises(FlowNavigationDriftError):
        asyncio.run(nav.navigate_to_submit_ready())


def test_navigation_wrong_project_two_signal_failure(tmp_path):
    """Project confirmation requires >= 2 signals; a wrong project stops."""
    pm = FlowProjectManager(state_dir=str(tmp_path), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    # fake UI points at a DIFFERENT project (fp_999) — only display-level text
    ui = ScriptedUi(
        [
            FlowUiObservation(
                url="https://flow.google.com/",
                markers=("Welcome back",),
                controls=("button:Create", "button:Import"),
            ),
            FlowUiObservation(
                url="https://flow.google.com/projects/fp_999",
                markers=("Project canvas",),
                controls=("button:Create workspace",),
            ),
        ]
    )
    nav = _navigator(tmp_path, ui, project_mapping=mapping)
    # navigation cannot confirm the wrong project; it fails closed (drift or
    # verification error) rather than proceeding on the wrong project
    with pytest.raises((FlowNavigationDriftError, FlowProjectVerificationError)):
        asyncio.run(nav.navigate_to_submit_ready())
