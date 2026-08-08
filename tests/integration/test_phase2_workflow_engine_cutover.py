"""
VP3D Stage A Phase 2 — Workflow → Executor → Port cutover integration test.

Proves (Stage A §5.2 / §6 acceptance criteria):

1. The durable production workflow actually dispatches a queued RENDER step
   through `ProductionEngineExecutor` -> `ProductionEnginePort` + IR (a real
   runtime call site, not just registration).
2. The workflow creates/reads the IR and the executor persists every receipt
   durably.
3. A worker restart re-attaches to in-flight jobs from durable state and never
   blind-resubmits (plan §5 'compensation_or_recovery').
4. Cancel + retry use inspect-before-resubmit: a retried job gets a NEW engine
   job id, never a resubmit on top of a terminated one.
5. The engine seam is engine-neutral: the workflow depends only on the
   injected `ProductionEnginePort` (fake here), never on a Blender adapter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from windagent_core.domain.video_production.ids import EngineJobId
from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    EngineJobStatus,
)
from windagent_core.domain.video_production.production_ir.models import (
    DerivedArtifact,
    EngineJobReceipt,
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)
from windagent_orchestration.production import (
    ProductionApprovalGate,
    ProductionEngineExecutor,
    ProductionRun,
    ProductionRunState,
    ProductionRunStore,
    ProductionStepExecutor,
    ProductionWorkflowEngine,
    StepExecutionResult,
)
from windagent_workflows.video_production.definition import (
    build_production_step_nodes,
)

from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir


class RecordingEnginePort:
    """Fake ProductionEnginePort that records every submit and job lifecycle.

    Job receipts are ALSO persisted to `state_dir` so a fresh instance over the
    same directory simulates a worker restart (durable re-attach).
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.submitted_scenes: list[str] = []
        self.submitted_shots: list[str] = []
        self.cancelled_job_ids: list[str] = []
        self._seq = 0

    def _next_job_id(self, prefix: str) -> EngineJobId:
        self._seq += 1
        return EngineJobId(f"ej_{prefix}_{self._seq}")

    def _path(self, job_id: EngineJobId) -> Path:
        return self.state_dir / f"{str(job_id)}.receipt.json"

    def _read(self, job_id: EngineJobId) -> EngineJobReceipt | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        return EngineJobReceipt.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def _persist(self, receipt: EngineJobReceipt) -> None:
        self._path(receipt.job_id).write_text(receipt.model_dump_json(), encoding="utf-8")

    def _receipt(self, job_id: EngineJobId, status: EngineJobStatus) -> EngineJobReceipt:
        return EngineJobReceipt(
            job_id=job_id,
            project_id="vp_ir_0001",
            revision_id="rev_0001",
            ir_hash="a" * 64,
            status=status,
            engine_name="fake-engine",
        )

    async def submit_scene(self, scene: SceneDescription, render: RenderIntent) -> EngineJobReceipt:
        self.submitted_scenes.append(str(scene.scene_id))
        receipt = self._receipt(self._next_job_id("scene"), EngineJobStatus.SUBMITTED)
        self._persist(receipt)
        return receipt

    async def submit_shot(self, intent: ShotExecutionIntent, render: RenderIntent) -> EngineJobReceipt:
        self.submitted_shots.append(str(intent.shot_id))
        receipt = self._receipt(self._next_job_id("shot"), EngineJobStatus.SUBMITTED)
        self._persist(receipt)
        return receipt

    async def inspect_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        return self._read(job_id) or self._receipt(job_id, EngineJobStatus.FAILED)

    async def cancel_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        self.cancelled_job_ids.append(str(job_id))
        known = self._read(job_id)
        cancelled = (known or self._receipt(job_id, EngineJobStatus.SUBMITTED)).model_copy(
            update={"status": EngineJobStatus.CANCELLED, "error": "cancelled"}
        )
        self._persist(cancelled)
        return cancelled

    async def download_artifact(
        self, job_id: EngineJobId, artifact_kind: DerivedArtifactKind
    ) -> DerivedArtifact:
        return DerivedArtifact(
            artifact_id="da_0001",
            job_id=job_id,
            kind=artifact_kind,
            uri=f"file:///tmp/{job_id}.bin",
            content_hash="b" * 64,
            derived_from_ir_hash="a" * 64,
            size_bytes=1,
        )


def _build_engine(
    *,
    store_dir: Path,
    port_state_dir: Path,
    executor_state_dir: Path,
    revision_to_ir=None,
) -> tuple[ProductionWorkflowEngine, RecordingEnginePort, ProductionEngineExecutor]:
    port = RecordingEnginePort(port_state_dir)
    executor = ProductionEngineExecutor(port=port, state_dir=executor_state_dir)
    ir_source = revision_to_ir or (lambda revision_id: build_valid_ir())
    step_executor = ProductionStepExecutor(engine=executor, ir_source=ir_source)
    engine = ProductionWorkflowEngine(
        store=ProductionRunStore(store_dir),
        executor=step_executor,
        step_nodes=build_production_step_nodes(),
    )
    return engine, port, executor


def _approve_required_gates(engine: ProductionWorkflowEngine, run: ProductionRun) -> None:
    for gate in (
        ProductionApprovalGate.CONCEPT_APPROVAL,
        ProductionApprovalGate.SCREENPLAY_APPROVAL,
        ProductionApprovalGate.CHARACTER_APPROVAL,
        ProductionApprovalGate.LOCATION_APPROVAL,
        ProductionApprovalGate.SHOT_PLAN_APPROVAL,
        ProductionApprovalGate.COST_APPROVAL,
    ):
        engine.approve(
            run.run_id,
            gate=gate,
            revision_id=run.revision_id,
            target_hash=run.revision_hash,
            actor="integration-tester",
        )


def _advance_until(
    engine: ProductionWorkflowEngine, run_id: str, step_id: str, *, worker_id: str = "worker_default"
) -> ProductionRun:
    run = engine.load(run_id)
    for _ in range(200):
        if run.current_step == step_id:
            return run
        run = engine.advance(run_id, worker_id=worker_id)
        if run.state == ProductionRunState.FAILED:
            raise AssertionError(f"Run failed before reaching {step_id}: {run}")
    raise AssertionError(f"Timed out waiting for step {step_id}; at {run.current_step}")


class TestRenderStepDispatchesThroughExecutor:
    def test_render_assets_goes_through_port_and_persists_receipt(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        engine, port, executor = _build_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine.create_run(
            project_id="vp_cutover",
            revision_id="rev_0001",
            revision_hash="c" * 64,
            run_id="run_render_assets",
        )
        engine.start(run.run_id)
        _approve_required_gates(engine, run)

        # Advance until RENDER_ASSETS submits through the engine seam.
        run = _advance_until(engine, run.run_id, "RENDER_ASSETS")

        assert run.state == ProductionRunState.WAITING_PROVIDER
        assert run.checkpoint is not None
        pending = run.checkpoint.pending_external_operation
        assert pending is not None
        assert pending.step_id == "RENDER_ASSETS"
        assert pending.provider == "engine"
        # The IR content hash is the request hash (engine-neutral provenance).
        assert pending.request_hash == build_valid_ir().content_hash()
        # The engine job id is the durable external id the workflow reconciles.
        assert pending.external_id.startswith("ej_")

        # The fake port received the IR scene + the executor persisted receipt.
        assert port.submitted_scenes == ["scn_01"]
        assert len(executor.persisted_receipts()) == 1
        persisted = executor.persisted_receipts()[0]
        assert persisted.job_id == EngineJobId(pending.external_id)
        assert persisted.status == EngineJobStatus.SUBMITTED

        # Ingesting the external result completes the step (idempotent).
        completed = engine.ingest_external_result(
            run.run_id,
            external_id=pending.external_id,
            output_hashes={str(persisted.job_id): persisted.ir_hash},
        )
        assert "RENDER_ASSETS" in completed.completed_steps

    def test_render_shots_dispatches_each_shot(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        engine, port, executor = _build_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine.create_run(
            project_id="vp_cutover",
            revision_id="rev_0001",
            revision_hash="d" * 64,
            run_id="run_render_shots",
        )
        engine.start(run.run_id)
        _approve_required_gates(engine, run)

        # RENDER_ASSETS goes through the engine seam first; ingest it so the
        # workflow may advance to RENDER_SHOTS (WAITING_PROVIDER never
        # re-schedules before ingestion).
        run = _advance_until(engine, run.run_id, "RENDER_ASSETS")
        first_job = run.checkpoint.pending_external_operation.external_id
        engine.ingest_external_result(
            run.run_id, external_id=first_job, output_hashes={first_job: "a" * 64}
        )

        run = _advance_until(engine, run.run_id, "RENDER_SHOTS")
        assert run.state == ProductionRunState.WAITING_PROVIDER
        pending = run.checkpoint.pending_external_operation
        assert pending.step_id == "RENDER_SHOTS"
        # The fixture IR has one shot.
        assert port.submitted_shots == ["sht_010"]
        assert len(executor.persisted_receipts()) >= 2

    def test_missing_ir_fails_closed_no_submit(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        engine, port, _ = _build_engine(
            store_dir=store_dir,
            port_state_dir=port_dir,
            executor_state_dir=exec_dir,
            revision_to_ir=lambda revision_id: None,
        )
        run = engine.create_run(
            project_id="vp_cutover",
            revision_id="rev_missing_ir",
            revision_hash="e" * 64,
            run_id="run_missing_ir",
        )
        engine.start(run.run_id)
        _approve_required_gates(engine, run)
        run = _advance_until(engine, run.run_id, "RENDER_ASSETS")
        # Fail closed: nothing was submitted, run is not stuck in provider.
        assert port.submitted_scenes == []
        assert run.state in (ProductionRunState.RUNNING, ProductionRunState.FAILED)


class TestWorkerRestartReconcileNeverBlindResubmit:
    def test_restart_reattaches_and_does_not_resubmit(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        # Worker v1: submit RENDER_ASSETS and reach WAITING_PROVIDER.
        engine1, port1, executor1 = _build_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine1.create_run(
            project_id="vp_cutover",
            revision_id="rev_0001",
            revision_hash="f" * 64,
            run_id="run_restart",
        )
        engine1.start(run.run_id)
        _approve_required_gates(engine1, run)
        run = _advance_until(engine1, run.run_id, "RENDER_ASSETS")
        job_id = EngineJobId(run.checkpoint.pending_external_operation.external_id)
        assert port1.submitted_scenes == ["scn_01"]

        # Worker v2 restarts over the SAME durable state (fresh port + executor).
        engine2, port2, executor2 = _build_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        # Fresh port submitted NOTHING on startup — no blind resubmit.
        assert port2.submitted_scenes == []
        assert port2.submitted_shots == []

        # Durable re-attach: executor2 reconciles the in-flight job.
        known = executor2.reconcile(job_id)
        assert known is not None
        assert known.status == EngineJobStatus.SUBMITTED
        assert known.job_id == job_id

        # The workflow engine re-attaches to WAITING_PROVIDER (never re-submits).
        recovered = engine2.recover(run.run_id)
        assert recovered.state == ProductionRunState.WAITING_PROVIDER
        assert port2.submitted_scenes == []  # still nothing resubmitted

        # Ingestion completes the step after restart.
        finished = engine2.ingest_external_result(
            run.run_id,
            external_id=str(job_id),
            output_hashes={str(job_id): known.ir_hash},
        )
        assert "RENDER_ASSETS" in finished.completed_steps

    def test_cancel_then_retry_uses_new_job_id(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        engine, port, executor = _build_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine.create_run(
            project_id="vp_cutover",
            revision_id="rev_0001",
            revision_hash="ab" * 32,
            run_id="run_cancel_retry",
        )
        engine.start(run.run_id)
        _approve_required_gates(engine, run)
        run = _advance_until(engine, run.run_id, "RENDER_ASSETS")
        first_job_id = EngineJobId(run.checkpoint.pending_external_operation.external_id)

        # Cancel the engine job through the executor (durable terminal state).
        cancelled = engine2_executor_cancel(executor, first_job_id)
        assert cancelled.status == EngineJobStatus.CANCELLED

        # Inspect-before-resubmit: the executor knows the job is terminal.
        assert executor.has_terminal(first_job_id) is True

        # A retry submits a NEW engine job with a DIFFERENT id (never a blind
        # resubmit on top of the cancelled one).
        ir_doc = build_valid_ir()
        retry_receipt = run_sync(executor.submit_scene(ir_doc.scenes[0], ir_doc.render_intents[0]))
        assert retry_receipt.job_id != first_job_id
        assert port.cancelled_job_ids == [str(first_job_id)]


# ---------------------------------------------------------------------------
# Small sync/async helpers
# ---------------------------------------------------------------------------
def run_sync(coro):
    import asyncio

    return asyncio.run(coro)


def engine2_executor_cancel(executor: ProductionEngineExecutor, job_id: EngineJobId) -> EngineJobReceipt:
    return run_sync(executor.cancel_job(job_id))


# ---------------------------------------------------------------------------
# VP3D batch tracking — EVERY engine job of a scene/shot, not just the first
# ---------------------------------------------------------------------------
def _build_multi_shot_ir():
    """IR with TWO scenes and TWO shots so RENDER_ASSETS/RENDER_SHOTS fan out
    into TWO engine jobs each (the batch recovery scenario)."""
    from windagent_core.domain.video_production.production_ir.models import (
        ProductionIrDocument,
    )

    from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir_dict

    raw = build_valid_ir_dict()
    scenes = list(raw["scenes"])
    shots = list(raw["shots"])
    render_intents = list(raw["render_intents"])

    scene2 = dict(scenes[0], scene_id="scn_02", screenplay_scene_id="scn_02")
    raw["scenes"] = scenes + [scene2]
    shot2 = dict(
        shots[0],
        intent_id="sht_020",
        shot_id="sht_020",
        scene_id="scn_02",
    )
    raw["shots"] = shots + [shot2]
    render2 = dict(
        render_intents[0],
        intent_id="ri_scn_02",
        scene_id="scn_02",
        shot_execution_intent_ids=["sht_020"],
    )
    raw["render_intents"] = render_intents + [render2]
    return ProductionIrDocument.model_validate(raw)


def _build_batch_engine(
    *,
    store_dir: Path,
    port_state_dir: Path,
    executor_state_dir: Path,
    revision_to_ir=None,
):
    """Engine over a multi-shot IR plus a per-job inspector for recovery."""
    from windagent_orchestration.production import ProductionRecovery
    from windagent_orchestration.production.recovery import ProviderJobState

    port = RecordingEnginePort(port_state_dir)
    executor = ProductionEngineExecutor(port=port, state_dir=executor_state_dir)
    ir_source = revision_to_ir or (lambda revision_id: _build_multi_shot_ir())
    step_executor = ProductionStepExecutor(engine=executor, ir_source=ir_source)

    def _inspect(job_id: str) -> ProviderJobState:
        receipt = executor.reconcile(EngineJobId(job_id))
        if receipt is None:
            return ProviderJobState.UNKNOWN
        return {
            EngineJobStatus.COMPLETED: ProviderJobState.COMPLETED,
            EngineJobStatus.CANCELLED: ProviderJobState.FAILED,
            EngineJobStatus.FAILED: ProviderJobState.FAILED,
        }.get(receipt.status, ProviderJobState.GENERATING)

    recovery = ProductionRecovery(inspect_engine_job=_inspect)
    engine = ProductionWorkflowEngine(
        store=ProductionRunStore(store_dir),
        executor=step_executor,
        step_nodes=build_production_step_nodes(),
        recovery=recovery,
    )
    return engine, port, executor


class TestBatchTracksEveryEngineJob:
    def test_render_assets_batch_carries_all_jobs_and_ingest_waits_for_all(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        engine, port, _ = _build_batch_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine.create_run(
            project_id="vp_cutover",
            revision_id="rev_batch",
            revision_hash="bb" * 32,
            run_id="run_batch_assets",
        )
        engine.start(run.run_id)
        _approve_required_gates(engine, run)

        run = _advance_until(engine, run.run_id, "RENDER_ASSETS")
        pending = run.checkpoint.pending_external_operation
        # TWO scenes -> TWO engine jobs, both recorded (never just the first).
        assert len(pending.job_ids) == 2
        assert port.submitted_scenes == ["scn_01", "scn_02"]
        assert pending.external_id in pending.job_ids

        # Ingesting ONLY the first job must NOT complete the step: the second
        # engine job is still unaccounted for.
        first, second = pending.job_ids[0], pending.job_ids[1]
        after_one = engine.ingest_external_result(
            run.run_id, external_id=first, output_hashes={first: "a" * 64}
        )
        assert "RENDER_ASSETS" not in after_one.completed_steps
        assert after_one.state == ProductionRunState.WAITING_PROVIDER
        assert (
            after_one.checkpoint.pending_external_operation is not None
        ), "pending op must survive until EVERY batch job is ingested"

        after_two = engine.ingest_external_result(
            run.run_id, external_id=second, output_hashes={second: "b" * 64}
        )
        assert "RENDER_ASSETS" in after_two.completed_steps
        assert after_two.checkpoint.pending_external_operation is None

    def test_recover_reconciles_every_batch_job_never_first_only(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        # Worker v1 submits the batch and dies before ingestion.
        engine1, port1, executor1 = _build_batch_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine1.create_run(
            project_id="vp_cutover",
            revision_id="rev_batch2",
            revision_hash="cc" * 32,
            run_id="run_batch_recover",
        )
        engine1.start(run.run_id)
        _approve_required_gates(engine1, run)
        run = _advance_until(engine1, run.run_id, "RENDER_ASSETS")
        pending = run.checkpoint.pending_external_operation
        assert len(pending.job_ids) == 2
        first, second = pending.job_ids[0], pending.job_ids[1]

        # Simulate: the FIRST job completed, the SECOND is still generating.
        completed = port1._read(EngineJobId(first))
        port1._persist(completed.model_copy(update={"status": EngineJobStatus.COMPLETED}))
        assert executor1.reconcile(EngineJobId(second)).status == EngineJobStatus.SUBMITTED

        # Worker v2 restarts: recovery must inspect BOTH jobs and land on
        # REATTACH (second still generating) — NOT claim completion from the
        # first job alone.
        engine2, port2, _ = _build_batch_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        assert port2.submitted_scenes == []
        recovered = engine2.recover(run.run_id)
        assert recovered.state == ProductionRunState.WAITING_PROVIDER
        assert port2.submitted_scenes == []  # never a blind resubmit

        # The batch only completes when BOTH jobs are ingested.
        finished = engine2.ingest_external_result(
            run.run_id, external_id=first, output_hashes={first: "a" * 64}
        )
        assert "RENDER_ASSETS" not in finished.completed_steps
        finished = engine2.ingest_external_result(
            run.run_id, external_id=second, output_hashes={second: "b" * 64}
        )
        assert "RENDER_ASSETS" in finished.completed_steps

    def test_cancel_batch_cancels_every_job(self, tmp_path):
        store_dir = tmp_path / "runs"
        port_dir = tmp_path / "port_state"
        exec_dir = tmp_path / "exec_state"

        engine, port, executor = _build_batch_engine(
            store_dir=store_dir, port_state_dir=port_dir, executor_state_dir=exec_dir
        )
        run = engine.create_run(
            project_id="vp_cutover",
            revision_id="rev_batch3",
            revision_hash="dd" * 32,
            run_id="run_batch_cancel",
        )
        engine.start(run.run_id)
        _approve_required_gates(engine, run)
        run = _advance_until(engine, run.run_id, "RENDER_ASSETS")
        pending = run.checkpoint.pending_external_operation
        job_ids = [EngineJobId(j) for j in pending.job_ids]
        assert len(job_ids) == 2

        receipts = run_sync(executor.cancel_batch(job_ids))
        assert len(receipts) == 2
        assert set(port.cancelled_job_ids) == {str(j) for j in job_ids}
        for receipt in receipts:
            assert receipt.status == EngineJobStatus.CANCELLED

        # A retry after batch cancel starts a NEW engine job per unit — never
        # resubmits over a cancelled one.
        ir = _build_multi_shot_ir()
        retry = run_sync(executor.submit_scene(ir.scenes[0], ir.render_intents[0]))
        assert retry.job_id not in {str(j) for j in job_ids}
