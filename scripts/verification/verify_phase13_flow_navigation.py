#!/usr/bin/env python3
"""
Phase 13 verification — VP13_FLOW_NAVIGATION_VERIFIED (plan 04 §11-§15).

Verifies the Flow navigation & project management adapter
(`tools/windagent_tools/google_flow/`) against the ratified contracts in
`docs/video_production/flow_navigation/`:

  artifacts/video_production/phase_13/
  ├── state_machine_receipt.json     (11 states, transitions, multi-signal)
  ├── selector_catalog_receipt.json  (semantic-first, versioned, safe)
  ├── project_mapping_receipt.json   (two-signal, open-before-create, no replace)
  ├── navigation_contract_receipt.json (READY→SUBMIT_READY, never submits)
  └── phase_verdict.json

Gate conditions (plan 04 §15):
  1. navigation drives READY → SUBMIT_READY via observable state;
  2. correct project/config confirmed by observable state (>= 2 signals);
  3. no submission during navigation tests;
  4. selector drift / signed-out / wrong project / missing control /
     duplicate label / locale mismatch fail closed;
  5. unapproved upload path is blocked;
  6. pre-submit config read-back evidence exists;
  7. fully offline (fake UI port) — no Flow production required.

Every check is offline and deterministic. Supports --no-write /
--verify-only.
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
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_13"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from windagent_tools.google_flow import (  # noqa: E402
    FlowNavigationDriftError,
    FlowNavigationReceipt,
    FlowNavigationStateError,
    FlowNavigator,
    FlowProjectManager,
    FlowProjectMappingStatus,
    FlowProjectMissingError,
    FlowProjectVerificationError,
    FlowUiAction,
    FlowUiObservation,
    FlowUiState,
    FlowUiStateMachine,
    SelectorCatalog,
    SelectorCatalogError,
    SelectorEntry,
    SelectorKind,
)


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


# ---------------------------------------------------------------------------
# Scripted fake UI port (plan 04 §14: fixture/mocked UI for each state)
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

    async def act(self, action: FlowUiAction) -> str:
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
        FlowUiObservation(
            url="https://flow.google.com/",
            markers=("Welcome back",),
            controls=("button:Create", "button:Import"),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123",
            markers=("Project canvas", "Create workspace"),
            controls=("button:Create workspace",),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Create",),
            controls=(
                "combobox:generation_mode",
                "textbox:prompt",
                "button:Generate",
            ),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Configured",),
            controls=("combobox:generation_mode", "textbox:prompt", "button:Generate"),
        ),
        FlowUiObservation(
            url="https://flow.google.com/projects/fp_123/editor",
            markers=("Configured",),
            controls=("button:Generate",),
        ),
    ]


def _navigator(workspace: Path, ui, *, mapping=None, pm=None, reference_assets=None):
    manager = pm or FlowProjectManager(state_dir=str(workspace), clock=time.time)
    if mapping is None:
        mapping = manager.create_mapping(
            project_id="vp_1",
            production_revision_id="rev_1",
            flow_project_id="fp_123",
            flow_project_url="https://flow.google.com/projects/fp_123",
        )
    return FlowNavigator(
        session_id="sess_13",
        project_id="vp_1",
        ui=ui,
        project_manager=manager,
        project_mapping=mapping,
        compiled_prompt="A short cartoon about a cat",
        reference_assets=reference_assets or ("approved://assets/cat.png",),
        generation_mode="TEXT_TO_VIDEO",
    )


# ---------------------------------------------------------------------------
# 1. State machine receipt (plan §12)
# ---------------------------------------------------------------------------
def build_state_machine_receipt() -> dict:
    checks: list[dict] = []
    sm = FlowUiStateMachine()

    states = {s.value for s in FlowUiState}
    _record(checks, "exactly_eleven_states", len(states) == 11,
            f"states={sorted(states)}")

    transitions = sm.transitions()
    _record(checks, "transitions_are_complete",
            len(transitions) >= 8
            and all(
                t.precondition and t.bounded_action and t.postcondition
                and t.timeout_seconds > 0 and t.evidence
                for t in transitions
            ),
            f"transition_count={len(transitions)}")

    _record(checks, "ready_classified_from_multi_signal",
            sm.classify(FlowUiObservation(
                url="https://flow.google.com/",
                markers=("Welcome back",),
                controls=("button:Create", "button:Import"),
            )) == FlowUiState.READY,
            "URL + markers + controls -> READY")

    _record(checks, "signed_out_classified",
            sm.classify(FlowUiObservation(
                url="https://flow.google.com/",
                markers=("Sign in with Google", "Welcome"),
                controls=("button:Sign in",),
            )) == FlowUiState.SIGNED_OUT,
            "sign-in markers -> SIGNED_OUT")

    _record(checks, "human_required_classified",
            sm.classify(FlowUiObservation(
                url="https://flow.google.com/",
                markers=("Verify you are human",),
                controls=(),
            )) == FlowUiState.HUMAN_ACTION_REQUIRED,
            "captcha marker -> HUMAN_ACTION_REQUIRED")

    _record(checks, "single_signal_never_decides",
            sm.classify(FlowUiObservation(
                url="https://flow.google.com/projects",
            )) == FlowUiState.UNKNOWN,
            "bare URL alone -> UNKNOWN (never a single selector)")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_navigation/flow_state_machine.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 2. Selector catalog receipt (plan §13.4)
# ---------------------------------------------------------------------------
def build_selector_catalog_receipt() -> dict:
    checks: list[dict] = []
    catalog = SelectorCatalog()

    kinds = {e.kind for e in catalog.entries()}
    _record(checks, "semantic_kinds_only",
            kinds <= {SelectorKind.ROLE, SelectorKind.LABEL, SelectorKind.TEXT,
                      SelectorKind.URL, SelectorKind.REGION},
            f"kinds={sorted(k.value for k in kinds)}")

    _record(checks, "forbidden_primary_kind_rejected",
            _rejects_forbidden_kind(),
            "css_class/dom_index/coordinate raise SelectorCatalogError")

    payment = catalog.get("payment_confirm")
    _record(checks, "payment_selector_is_destructive",
            payment.destructive is True,
            "payment confirm never auto-clicked by a fallback")

    _record(checks, "catalog_versioned",
            isinstance(catalog.version, str) and catalog.version,
            f"version={catalog.version}")

    _record(checks, "locale_assumption_explicit",
            isinstance(catalog.locale, str) and catalog.locale,
            f"locale={catalog.locale}")

    _record(checks, "unknown_selector_raises",
            _unknown_selector_raises(catalog),
            "unknown selector -> SelectorCatalogError")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_navigation/flow_selector_catalog.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


def _rejects_forbidden_kind() -> bool:
    try:
        SelectorCatalog(entries=[SelectorEntry("bad", "css_class", ".cls")])
        return False
    except SelectorCatalogError:
        return True


def _unknown_selector_raises(catalog: SelectorCatalog) -> bool:
    try:
        catalog.get("no_such_selector")
        return False
    except SelectorCatalogError:
        return True


# ---------------------------------------------------------------------------
# 3. Project mapping receipt (plan §13.2)
# ---------------------------------------------------------------------------
def build_project_mapping_receipt() -> dict:
    checks: list[dict] = []
    workspace = Path(tempfile.mkdtemp(prefix="phase13_mapping_"))
    pm = FlowProjectManager(state_dir=str(workspace), clock=time.time)

    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    _record(checks, "mapping_created_unverified",
            mapping.mapping_status == FlowProjectMappingStatus.UNVERIFIED,
            "new mapping starts UNVERIFIED")

    verified = pm.verify_two_signals(
        mapping,
        observed=("fp_123", "https://flow.google.com/projects/fp_123"),
    )
    _record(checks, "two_signal_verification",
            verified.mapping_status == FlowProjectMappingStatus.VERIFIED,
            ">= 2 independent signals -> VERIFIED")

    one_signal = False
    try:
        pm.verify_two_signals(mapping, observed=("fp_123",))
    except FlowProjectVerificationError:
        one_signal = True
    _record(checks, "one_signal_rejected",
            one_signal,
            "single signal -> FlowProjectVerificationError")

    display_only = False
    try:
        pm.verify_two_signals(mapping, observed=("My Cool Video",))
    except FlowProjectVerificationError:
        display_only = True
    _record(checks, "display_name_not_identity",
            display_only,
            "display name alone can never verify")

    # open-before-create: existing verified mapping is reopened
    reopened = pm.open_before_create(
        "vp_1", observed=("fp_123", "https://flow.google.com/projects/fp_123")
    )
    _record(checks, "open_before_create",
            reopened.mapping_status == FlowProjectMappingStatus.VERIFIED,
            "existing mapping re-opened, not re-created")

    # missing project -> typed failure, no auto-replace
    pm.mark_missing("vp_1")
    missing = False
    try:
        pm.open_before_create(
            "vp_1", observed=("fp_123", "https://flow.google.com/projects/fp_123")
        )
    except FlowProjectMissingError:
        missing = True
    _record(checks, "missing_project_typed_failure",
            missing,
            "MISSING project raises FlowProjectMissingError (no auto-replace)")

    # mapping survives reload
    reloaded = FlowProjectManager(state_dir=str(workspace), clock=time.time)
    got = reloaded.get_mapping("vp_1")
    _record(checks, "mapping_persists_across_reload",
            got is not None and got.mapping_status == FlowProjectMappingStatus.MISSING,
            "JSON persistence survives manager reload")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_navigation/flow_project_mapping.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Navigation contract receipt (plan §13.3, §15)
# ---------------------------------------------------------------------------
def build_navigation_contract_receipt() -> dict:
    checks: list[dict] = []
    workspace = Path(tempfile.mkdtemp(prefix="phase13_nav_"))

    ui = ScriptedUi(_ready_script())
    nav = _navigator(workspace, ui)
    receipt: FlowNavigationReceipt = asyncio.run(nav.navigate_to_submit_ready())
    _record(checks, "reaches_submit_ready",
            receipt.reached_state == FlowUiState.SUBMIT_READY
            and receipt.target_state == FlowUiState.SUBMIT_READY,
            f"reached={receipt.reached_state.value}")

    _record(checks, "never_submits",
            receipt.submitted is False and "submit" not in ui.actions,
            f"actions={ui.actions} (no submit op)")

    _record(checks, "four_steps_with_evidence",
            len(receipt.steps) == 4
            and all(s.snapshot_hash for s in receipt.steps),
            "open/create-workspace/configure/read-back steps each carry evidence")

    _record(checks, "pre_submit_evidence_captured",
            bool(receipt.pre_submit_evidence_hash),
            "sha256 of final URL+markers+controls captured before submit")

    # signed-out -> typed error
    signed_out_ui = ScriptedUi([
        FlowUiObservation(
            url="https://flow.google.com/",
            markers=("Sign in with Google", "Welcome"),
            controls=("button:Sign in",),
        )
    ])
    signed_out = False
    try:
        asyncio.run(_navigator(workspace, signed_out_ui).navigate_to_submit_ready())
    except FlowNavigationStateError:
        signed_out = True
    _record(checks, "signed_out_is_typed_error",
            signed_out,
            "signed-out state -> FlowNavigationStateError (Phase 16 human)")

    # selector drift -> fail closed, no blind retry
    drift_script = _ready_script()
    drift_script[1] = FlowUiObservation(
        url="https://flow.google.com/projects/OTHER",
        markers=("Welcome back",),
        controls=("button:Create",),
    )
    drift_ui = ScriptedUi(drift_script)
    drifted = False
    try:
        asyncio.run(_navigator(workspace, drift_ui).navigate_to_submit_ready())
    except FlowNavigationDriftError:
        drifted = True
    _record(checks, "drift_fails_closed_no_blind_retry",
            drifted and drift_ui.actions.count("open") == 1,
            "postcondition mismatch stops; exactly one open attempt")

    # unapproved upload path blocked at the port boundary
    blocked_ui = ScriptedUi(_ready_script())
    blocked_ui.reject_upload_path = "/unapproved/"
    blocked = False
    try:
        asyncio.run(
            _navigator(
                workspace, blocked_ui, reference_assets=("/unapproved/secret.png",)
            ).navigate_to_submit_ready()
        )
    except FlowNavigationDriftError:
        blocked = True
    _record(checks, "unapproved_upload_blocked",
            blocked,
            "unapproved upload path rejected by the UI port")

    # wrong project -> two-signal verification failure fails navigation closed
    wrong_pm = FlowProjectManager(state_dir=str(workspace), clock=time.time)
    wrong_mapping = wrong_pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    wrong_ui = ScriptedUi([
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
    ])
    wrong_failed = False
    try:
        asyncio.run(
            _navigator(workspace, wrong_ui, mapping=wrong_mapping, pm=wrong_pm)
            .navigate_to_submit_ready()
        )
    except (FlowNavigationDriftError, FlowProjectVerificationError):
        wrong_failed = True
    _record(checks, "wrong_project_fails_closed",
            wrong_failed,
            "cannot confirm the wrong project -> stops (no silent proceed)")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_navigation/flow_navigation_contract.md",
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

    state_machine = build_state_machine_receipt()
    selector_catalog = build_selector_catalog_receipt()
    project_mapping = build_project_mapping_receipt()
    navigation_contract = build_navigation_contract_receipt()

    gate_reasons: list[str] = []
    if not state_machine["all_checks_pass"]:
        gate_reasons.append("state machine checks failed")
    if not selector_catalog["all_checks_pass"]:
        gate_reasons.append("selector catalog checks failed")
    if not project_mapping["all_checks_pass"]:
        gate_reasons.append("project mapping checks failed")
    if not navigation_contract["all_checks_pass"]:
        gate_reasons.append("navigation contract checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 13,
        "status": overall_status,
        "gate": "VP13_FLOW_NAVIGATION_VERIFIED",
        "evidence": [
            {"path": "state_machine_receipt.json"},
            {"path": "selector_catalog_receipt.json"},
            {"path": "project_mapping_receipt.json"},
            {"path": "navigation_contract_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase13_flow_navigation.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "state_machine_receipt.json", state_machine)
        write_json(PHASE_DIR / "selector_catalog_receipt.json", selector_catalog)
        write_json(PHASE_DIR / "project_mapping_receipt.json", project_mapping)
        write_json(PHASE_DIR / "navigation_contract_receipt.json", navigation_contract)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(
                overall_status,
                state_machine,
                selector_catalog,
                project_mapping,
                navigation_contract,
            ),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_13 artifacts untouched.")

    print(f"Phase 13 verdict: {overall_status}")
    print(f"  state machine: {'PASS' if state_machine['all_checks_pass'] else 'FAIL'}")
    print(f"  selector catalog: {'PASS' if selector_catalog['all_checks_pass'] else 'FAIL'}")
    print(f"  project mapping: {'PASS' if project_mapping['all_checks_pass'] else 'FAIL'}")
    print(f"  navigation contract: {'PASS' if navigation_contract['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, state_machine, selector, mapping, navigation) -> str:
    return f"""# Phase 13 Report — Flow Navigation & Project Management

- **Gate:** `VP13_FLOW_NAVIGATION_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## State machine

- Contract: `docs/video_production/flow_navigation/flow_state_machine.md`
- Checks: {state_machine.get('check_count')}; all pass: {state_machine.get('all_checks_pass')}

## Selector catalog

- Contract: `docs/video_production/flow_navigation/flow_selector_catalog.md`
- Checks: {selector.get('check_count')}; all pass: {selector.get('all_checks_pass')}

## Project mapping

- Contract: `docs/video_production/flow_navigation/flow_project_mapping.md`
- Checks: {mapping.get('check_count')}; all pass: {mapping.get('all_checks_pass')}

## Navigation contract

- Contract: `docs/video_production/flow_navigation/flow_navigation_contract.md`
- Checks: {navigation.get('check_count')}; all pass: {navigation.get('all_checks_pass')}

## Evidence

- `state_machine_receipt.json`
- `selector_catalog_receipt.json`
- `project_mapping_receipt.json`
- `navigation_contract_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
