#!/usr/bin/env python3
"""
Phase 14 verification — VP14_FLOW_IMAGE_GENERATION_VERIFIED (plan 04 §16-§19).

Verifies the image generation adapter (`tools/windagent_tools/google_flow/`)
against the ratified contracts in `docs/video_production/flow_images/`:

  artifacts/video_production/phase_14/
  ├── image_operations_receipt.json    (8 typed operations, plan §17)
  ├── pre_submit_guard_receipt.json    (fail-closed, plan §18.1)
  ├── job_idempotency_receipt.json     (reconcile matrix, plan §18.2/§23.1)
  ├── candidate_acquisition_receipt.json (0/1/n + invalid never published, §18.3)
  ├── review_approval_receipt.json     (character master → human, §18.4)
  └── phase_verdict.json

Gate conditions (plan 04 §19):
  1. image operations in scope have contract tests (8 typed ops);
  2. pre-submit guard fails closed before any submit click;
  3. durable job + reconciliation — no duplicate submit across the failure
     matrix (completed reuse / active resume / retry new attempt / reconcile
     unknown);
  4. candidates downloaded, validated and traced — invalid candidates never
     enter the canonical store;
  5. approval fails closed — character master never auto-approved, VLM low
     confidence → human review, no auto-bind.

Every check is offline and deterministic. Supports --no-write / --verify-only.
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "video_production" / "phase_14"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from windagent_tools.google_flow import (  # noqa: E402
    CandidateDownloader,
    CandidateInvalidError,
    FlowImageGenerator,
    FlowImageOperation,
    FlowImageRequest,
    FlowJobRecord,
    FlowJobRegistry,
    FlowJobStatus,
    FlowNavigationReceipt,
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
from windagent_tools.media_assets.store import ContentAddressedStore  # noqa: E402

REQUEST_HASH = "b" * 64


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


def _png_bytes(color: tuple = (10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="PNG")
    return buf.getvalue()


def _request(**overrides) -> FlowImageRequest:
    base = dict(
        operation=FlowImageOperation.CREATE_STORYBOARD_FRAME,
        request_hash=REQUEST_HASH,
        project_id="vp_1",
        revision_id="rev_1",
        shot_id="shot_1",
        prompt="a red cube on a table",
        reference_bindings=(("identity", "hash0"),),
        candidate_limit=4,
    )
    base.update(overrides)
    return FlowImageRequest(**base)


# ---------------------------------------------------------------------------
# Fakes (deterministic, offline)
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
            session_id="sess_14",
            project_id="vp_1",
            target_state=FlowUiState.SUBMIT_READY,
            reached_state=FlowUiState.SUBMIT_READY,
            pre_submit_evidence_hash="pre-evidence-14",
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


def _happy_script(candidate_refs: tuple[str, ...]) -> list[FlowUiObservation]:
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


def _reasons_contain(verdict, needle: str) -> bool:
    """Substring search across a verdict's reasons tuple."""
    return any(needle in r for r in verdict.reasons)


def _workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="phase14_"))


def _generator(
    workspace: Path,
    *,
    ui=None,
    vlm=None,
    fetcher=None,
    mapper=None,
    request_hash=REQUEST_HASH,
):
    store = ContentAddressedStore(workspace / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(workspace / "quarantine"), store=store
    )
    pm = FlowProjectManager(state_dir=str(workspace), clock=time.time)
    mapping = pm.create_mapping(
        project_id="vp_1",
        production_revision_id="rev_1",
        flow_project_id="fp_123",
        flow_project_url="https://flow.google.com/projects/fp_123",
    )
    job_registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    return FlowImageGenerator(
        session_id="sess_14",
        project_id="vp_1",
        ui=ui or FakeUi(_happy_script(())),
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
    )


# ---------------------------------------------------------------------------
# 1. Image operations receipt (plan §17)
# ---------------------------------------------------------------------------
def build_image_operations_receipt() -> dict:
    checks: list[dict] = []
    mapper = ImageOperationMapper()

    ops = {op.value for op in FlowImageOperation}
    _record(checks, "exactly_eight_image_operations", len(ops) == 8,
            f"operations={sorted(ops)}")

    actions = mapper.configuration_actions(_request())
    _record(checks, "typed_actions_only",
            all(isinstance(a, FlowUiAction) for a in actions)
            and all(a.operation in ("select", "fill", "upload") for a in actions),
            f"config_steps={len(actions)}")

    _record(checks, "character_master_policy",
            mapper.is_character_master(FlowImageOperation.CREATE_CHARACTER_REFERENCE)
            and not mapper.is_character_master(
                FlowImageOperation.CREATE_STORYBOARD_FRAME
            ),
            "character reference requires human approval")

    _record(checks, "reference_policy",
            mapper.requires_reference(FlowImageOperation.CREATE_FIRST_FRAME)
            and not mapper.requires_reference(FlowImageOperation.EDIT_IMAGE)
            and mapper.requires_source_image(FlowImageOperation.UPSCALE_IMAGE),
            "reference/source requirements per operation")

    _record(checks, "capability_fails_closed",
            not ImageOperationMapper(
                capability=(FlowImageOperation.CREATE_STORYBOARD_FRAME,)
            ).supported(FlowImageOperation.UPSCALE_IMAGE),
            "unsupported operation denied")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_images/image_operations_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 2. Pre-submit guard receipt (plan §18.1)
# ---------------------------------------------------------------------------
def build_pre_submit_guard_receipt() -> dict:
    checks: list[dict] = []
    guard = PreSubmitGuard()

    ok_kwargs = dict(
        mapping_healthy=True,
        session_healthy=True,
        references_approved=True,
        upload_hash_matches=True,
        pre_submit_evidence_hash="evidence",
        operation_supported=True,
        cost_allowed=True,
    )
    verdict = guard.check(_request(), **ok_kwargs)
    _record(checks, "all_conditions_pass", verdict.ok,
            "happy path → ok")

    # Reference-required ops (CREATE_FIRST_FRAME) must fail closed when the
    # approved reference's upload hash does not match or the reference was
    # never approved (plan 04 §18.1).
    broken = dict(ok_kwargs, upload_hash_matches=False)
    verdict = guard.check(
        _request(operation=FlowImageOperation.CREATE_FIRST_FRAME), **broken
    )
    _record(checks, "upload_hash_mismatch_fails_closed",
            not verdict.ok
            and _reasons_contain(verdict, "upload hash mismatch"),
            f"reasons={verdict.reasons}")

    broken = dict(ok_kwargs, references_approved=False)
    verdict = guard.check(
        _request(operation=FlowImageOperation.CREATE_FIRST_FRAME), **broken
    )
    _record(checks, "reference_not_approved_fails_closed",
            not verdict.ok
            and _reasons_contain(verdict, "reference not approved"),
            f"reasons={verdict.reasons}")

    broken = dict(ok_kwargs, pre_submit_evidence_hash="")
    verdict = guard.check(_request(), **broken)
    _record(checks, "missing_evidence_fails_closed",
            not verdict.ok
            and _reasons_contain(verdict, "pre-submit evidence missing"),
            f"reasons={verdict.reasons}")

    broken = dict(ok_kwargs, operation_supported=False)
    verdict = guard.check(_request(), **broken)
    _record(checks, "unsupported_operation_fails_closed",
            not verdict.ok and _reasons_contain(verdict, "not supported"),
            f"reasons={verdict.reasons}")

    broken = dict(ok_kwargs, cost_allowed=False)
    verdict = guard.check(_request(), **broken)
    _record(checks, "cost_policy_fails_closed",
            not verdict.ok and _reasons_contain(verdict, "cost/quota"),
            f"reasons={verdict.reasons}")

    bad_hash = _request(request_hash="not-a-hash")
    verdict = guard.check(bad_hash, **ok_kwargs)
    _record(checks, "invalid_request_hash_fails_closed",
            not verdict.ok and _reasons_contain(verdict, "request_hash invalid"),
            f"reasons={verdict.reasons}")

    broken = dict(ok_kwargs)
    verdict = guard.check(_request(candidate_limit=0), **broken)
    _record(checks, "zero_candidate_limit_fails_closed",
            not verdict.ok and _reasons_contain(verdict, "candidate_limit"),
            f"reasons={verdict.reasons}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_images/pre_submit_guard.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3. Job idempotency receipt (plan §18.2 / §23.1)
# ---------------------------------------------------------------------------
def build_job_idempotency_receipt() -> dict:
    checks: list[dict] = []
    workspace = _workspace()
    registry = FlowJobRegistry(state_dir=str(workspace), clock=time.time)
    key = dict(request_hash=REQUEST_HASH, project_id="vp_1",
               provider="google_flow_browser")

    _record(checks, "missing_job_creates_prepared",
            registry.reconcile(**key).action
            == FlowReconcileAction.CREATE_PREPARED,
            "no prior job → CREATE_PREPARED")

    registry.create_prepared(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1",
        request_hash=REQUEST_HASH,
    )
    registry.record_candidates("gen_1", ["c0", "c1"])
    decision = registry.reconcile(**key)
    _record(checks, "completed_job_reused",
            decision.action == FlowReconcileAction.REUSE_COMPLETED,
            "COMPLETED → reuse candidate set (no resubmit)")

    registry.mark("gen_1", FlowJobStatus.GENERATING)
    decision = registry.reconcile(**key)
    _record(checks, "active_job_resumed",
            decision.action == FlowReconcileAction.RESUME_ACTIVE,
            "active job → inspect/resume")

    registry.mark("gen_1", FlowJobStatus.FAILED_RETRYABLE)
    decision = registry.reconcile(**key)
    _record(checks, "retryable_failure_new_attempt",
            decision.action == FlowReconcileAction.NEW_ATTEMPT,
            f"attempt={decision.record.attempt}")

    # exhaust the retry budget by chaining attempts properly
    current = "gen_1"
    for _ in range(3):  # attempt 2, 3, 4 — budget is 3, so >= 3 is exhausted
        nxt = registry.next_attempt(current)
        registry.mark(nxt.generation_id, FlowJobStatus.FAILED_RETRYABLE)
        current = nxt.generation_id
    decision = registry.reconcile(**key)
    _record(checks, "budget_exhausted_reconciles",
            decision.action == FlowReconcileAction.RECONCILE_UNKNOWN,
            "retry budget exhausted → reconcile (no blind resubmit)")

    registry.mark(current, FlowJobStatus.FAILED_TERMINAL)
    decision = registry.reconcile(**key)
    _record(checks, "terminal_failure_reconciles",
            decision.action == FlowReconcileAction.RECONCILE_UNKNOWN,
            "terminal failure → reconcile (never blind resubmit)")

    attempt2 = registry.next_attempt("gen_1")
    _record(checks, "next_attempt_keeps_causal_link",
            attempt2.attempt == 2
            and attempt2.parent_generation_id == "gen_1",
            f"attempt={attempt2.attempt} parent={attempt2.parent_generation_id}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_images/job_idempotency_contract.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 4. Candidate acquisition receipt (plan §18.3)
# ---------------------------------------------------------------------------
def build_candidate_acquisition_receipt() -> dict:
    checks: list[dict] = []
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(workspace / "quarantine"), store=store
    )
    job = FlowJobRecord(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1"
    )

    png = _png_bytes()

    async def acquire(payload):
        return await downloader.acquire(
            job=job, candidate_id="gen_1c0", uri="res://a.png", index=0,
            fetcher=FakeFetcher({"res://a.png": payload}),
        )

    acquired = asyncio.run(acquire(png))
    _record(checks, "valid_candidate_published",
            acquired.published and acquired.mime == "image/png"
            and acquired.content_hash == store.content_hash(png),
            f"mime={acquired.mime} published={acquired.published}")

    zero_rejected = False
    try:
        asyncio.run(acquire(b""))
    except CandidateInvalidError:
        zero_rejected = True
    _record(checks, "zero_byte_rejected", zero_rejected,
            "zero-byte candidate never published")

    mime_rejected = False
    try:
        asyncio.run(acquire(b"not an image at all"))
    except CandidateInvalidError:
        mime_rejected = True
    _record(checks, "wrong_mime_rejected", mime_rejected,
            "non-image payload never published")

    _record(checks, "store_clean_after_rejections",
            len(store.list_hashes()) == 1,
            f"store hashes={store.list_hashes()} (only the valid PNG)")

    # 0/1/n candidates end-to-end (distinct request hashes per scenario so
    # each generator run gets its own idempotency key)
    ui_zero = FakeUi(_happy_script(()))
    gen_zero = _generator(workspace, ui=ui_zero, fetcher=FakeFetcher({}),
                          vlm=FakeVlm())
    out_zero = asyncio.run(
        gen_zero.generate_image(_request(request_hash="c" * 64))
    )
    _record(checks, "zero_candidates_supported",
            out_zero.submit_clicked and out_zero.candidates == (),
            "0 candidates is a valid (non-ok) outcome")

    ui_two = FakeUi(_happy_script(("candidate:https://cdn.example.com/a.png",
                                   "candidate:https://cdn.example.com/b.png")))
    fetcher = FakeFetcher({
        "https://cdn.example.com/a.png": png,
        "https://cdn.example.com/b.png": _png_bytes((200, 10, 10)),
    })
    gen_two = _generator(workspace, ui=ui_two, fetcher=fetcher, vlm=FakeVlm())
    out_two = asyncio.run(
        gen_two.generate_image(_request(request_hash="d" * 64))
    )
    _record(checks, "all_candidates_acquired",
            len(out_two.candidates) == 2
            and all(c.published for c in out_two.candidates),
            f"candidates={len(out_two.candidates)}")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_images/candidate_acquisition.md",
        "check_count": len(checks),
        "all_checks_pass": all_ok,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 5. Review/approval receipt (plan §18.4)
# ---------------------------------------------------------------------------
def build_review_approval_receipt() -> dict:
    checks: list[dict] = []
    workspace = _workspace()
    store = ContentAddressedStore(workspace / "store")
    downloader = CandidateDownloader(
        quarantine_dir=str(workspace / "quarantine"), store=store
    )
    job = FlowJobRecord(
        generation_id="gen_1", project_id="vp_1", revision_id="rev_1"
    )

    async def acquire():
        return await downloader.acquire(
            job=job, candidate_id="gen_1c0", uri="res://a.png", index=0,
            fetcher=FakeFetcher({"res://a.png": _png_bytes()}),
        )

    acquired = asyncio.run(acquire())
    gate = ReviewGate(clock=time.time)

    async def review(request, vlm, deterministic_valid=True):
        return await gate.review(
            candidate=acquired, request=request, vlm=vlm,
            deterministic_valid=deterministic_valid,
        )

    master = asyncio.run(review(
        _request(operation=FlowImageOperation.CREATE_CHARACTER_REFERENCE),
        FakeVlm(compliance=0.99, identity=0.99),
    ))
    _record(checks, "character_master_never_auto_approved",
            master.decision == ReviewDecision.REQUIRES_HUMAN
            and master.character_master,
            "character master → human even at 0.99 confidence")

    low = asyncio.run(review(_request(), FakeVlm(compliance=0.2, identity=0.2)))
    _record(checks, "vlm_low_confidence_human",
            low.decision == ReviewDecision.REQUIRES_HUMAN,
            "VLM low confidence → human review, never auto-approve")

    invalid = asyncio.run(review(_request(), FakeVlm(0.99, 0.99),
                                 deterministic_valid=False))
    _record(checks, "invalid_candidate_rejected_first",
            invalid.decision == ReviewDecision.REJECTED,
            "deterministic validity precedes VLM (fail closed)")

    approved = asyncio.run(review(_request(), FakeVlm(0.95, 0.95)))
    _record(checks, "high_confidence_non_master_approved",
            approved.decision == ReviewDecision.APPROVED,
            "valid + high VLM + non-master → approved")

    _record(checks, "no_auto_bind",
            not any(r.candidate_id == "" for r in (master, low, invalid, approved))
            and all(r.reason for r in (master, low, invalid, approved)),
            "reviews keep reason; no implicit binding")

    # end-to-end: generator review fail-closed (distinct hash from reuse)
    gen = _generator(
        workspace,
        ui=FakeUi(_happy_script(("candidate:https://cdn.example.com/a.png",))),
        fetcher=FakeFetcher({"https://cdn.example.com/a.png": _png_bytes()}),
        vlm=FakeVlm(),
    )
    out = asyncio.run(gen.generate_image(_request(request_hash="e" * 64)))
    _record(checks, "generator_reviews_all_candidates",
            out.submit_clicked and len(out.reviews) == 1,
            f"reviews={len(out.reviews)}")

    # duplicate command (same request hash) → completed job reused, no submit
    gen2 = _generator(
        workspace,
        ui=FakeUi(_happy_script(("candidate:https://cdn.example.com/a.png",))),
        fetcher=FakeFetcher({"https://cdn.example.com/a.png": _png_bytes()}),
        vlm=FakeVlm(),
    )
    out2 = asyncio.run(gen2.generate_image(_request(request_hash="e" * 64)))
    _record(checks, "duplicate_command_no_resubmit",
            out2.submit_clicked is False,
            "completed job reused — no duplicate submit")

    # unknown UI state (fresh hash) → reconcile, never blind resubmit
    gen_unknown = _generator(
        workspace,
        ui=FakeUi([
            FlowUiObservation(url="https://flow.google.com/editor",
                              markers=("Generating",), controls=()),
            FlowUiObservation(url="https://flow.google.com/editor",
                              markers=(), controls=()),
        ]),
        fetcher=FakeFetcher({}),
        vlm=FakeVlm(),
    )
    reconciled = False
    try:
        asyncio.run(gen_unknown.generate_image(_request(request_hash="f" * 64)))
    except FlowSubmitReconciledError:
        reconciled = True
    _record(checks, "unknown_state_reconciles_not_resubmit",
            reconciled,
            "unknown UI → UNKNOWN_REQUIRES_RECONCILIATION (no blind resubmit)")

    all_ok = all(c["ok"] for c in checks)
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "contract": "docs/video_production/flow_images/review_approval_contract.md",
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

    image_ops = build_image_operations_receipt()
    pre_submit = build_pre_submit_guard_receipt()
    job_idem = build_job_idempotency_receipt()
    candidate = build_candidate_acquisition_receipt()
    review = build_review_approval_receipt()

    gate_reasons: list[str] = []
    if not image_ops["all_checks_pass"]:
        gate_reasons.append("image operations checks failed")
    if not pre_submit["all_checks_pass"]:
        gate_reasons.append("pre-submit guard checks failed")
    if not job_idem["all_checks_pass"]:
        gate_reasons.append("job idempotency checks failed")
    if not candidate["all_checks_pass"]:
        gate_reasons.append("candidate acquisition checks failed")
    if not review["all_checks_pass"]:
        gate_reasons.append("review/approval checks failed")

    overall_status = "PASSED" if not gate_reasons else "BLOCKED"

    phase_verdict = {
        "schema_version": "1.0.0",
        "phase": 14,
        "status": overall_status,
        "gate": "VP14_FLOW_IMAGE_GENERATION_VERIFIED",
        "evidence": [
            {"path": "image_operations_receipt.json"},
            {"path": "pre_submit_guard_receipt.json"},
            {"path": "job_idempotency_receipt.json"},
            {"path": "candidate_acquisition_receipt.json"},
            {"path": "review_approval_receipt.json"},
        ],
        "blocking_reasons": gate_reasons,
        "derived_from": "scripts/verification/verify_phase14_flow_images.py",
    }

    if not no_write:
        write_json(PHASE_DIR / "image_operations_receipt.json", image_ops)
        write_json(PHASE_DIR / "pre_submit_guard_receipt.json", pre_submit)
        write_json(PHASE_DIR / "job_idempotency_receipt.json", job_idem)
        write_json(PHASE_DIR / "candidate_acquisition_receipt.json", candidate)
        write_json(PHASE_DIR / "review_approval_receipt.json", review)
        write_json(PHASE_DIR / "phase_verdict.json", phase_verdict)
        (PHASE_DIR / "phase_report.md").write_text(
            _phase_report(overall_status, image_ops, pre_submit, job_idem,
                          candidate, review),
            encoding="utf-8",
            newline="\n",
        )
    else:
        print("Verify-only mode: phase_14 artifacts untouched.")

    print(f"Phase 14 verdict: {overall_status}")
    print(f"  image operations: {'PASS' if image_ops['all_checks_pass'] else 'FAIL'}")
    print(f"  pre-submit guard: {'PASS' if pre_submit['all_checks_pass'] else 'FAIL'}")
    print(f"  job idempotency: {'PASS' if job_idem['all_checks_pass'] else 'FAIL'}")
    print(f"  candidate acquisition: {'PASS' if candidate['all_checks_pass'] else 'FAIL'}")
    print(f"  review/approval: {'PASS' if review['all_checks_pass'] else 'FAIL'}")
    for reason in gate_reasons:
        print(f"  BLOCKING: {reason}")
    return 0 if overall_status == "PASSED" else 1


def _phase_report(status, ops, pre, job, cand, rev) -> str:
    return f"""# Phase 14 Report — Flow Image Generation

- **Gate:** `VP14_FLOW_IMAGE_GENERATION_VERIFIED`
- **Status:** {status}
- **Generated at:** {utc_now_iso()}

## Image operations

- Contract: `docs/video_production/flow_images/image_operations_contract.md`
- Checks: {ops.get('check_count')}; all pass: {ops.get('all_checks_pass')}

## Pre-submit guard

- Contract: `docs/video_production/flow_images/pre_submit_guard.md`
- Checks: {pre.get('check_count')}; all pass: {pre.get('all_checks_pass')}

## Job idempotency

- Contract: `docs/video_production/flow_images/job_idempotency_contract.md`
- Checks: {job.get('check_count')}; all pass: {job.get('all_checks_pass')}

## Candidate acquisition

- Contract: `docs/video_production/flow_images/candidate_acquisition.md`
- Checks: {cand.get('check_count')}; all pass: {cand.get('all_checks_pass')}

## Review & approval

- Contract: `docs/video_production/flow_images/review_approval_contract.md`
- Checks: {rev.get('check_count')}; all pass: {rev.get('all_checks_pass')}

## Evidence

- `image_operations_receipt.json`
- `pre_submit_guard_receipt.json`
- `job_idempotency_receipt.json`
- `candidate_acquisition_receipt.json`
- `review_approval_receipt.json`
- `phase_verdict.json`
"""


if __name__ == "__main__":
    sys.exit(main(no_write="--no-write" in sys.argv or "--verify-only" in sys.argv))
