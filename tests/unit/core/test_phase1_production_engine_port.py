"""
Contract tests for ProductionEnginePort (VP3D Phase 1).

Proves (plan §4 "Kiểm thử"):
- a fake engine adapter consumes the same IR a production pipeline would
  submit (contract test);
- the port is runtime-checkable;
- the port source contains NO Flow prompt / selector / cookie / `bpy` /
  engine-SDK leakage;
- receipts and derived artifacts carry the IR hash for precise invalidation.
"""

import inspect


from windagent_core.contracts.video_production import ProductionEnginePort
from windagent_core.domain.video_production import (
    DerivedArtifact,
    EngineJobReceipt,
)
from windagent_core.domain.video_production.ids import EngineJobId
from windagent_core.domain.video_production.production_ir.enums import (
    DerivedArtifactKind,
    EngineJobStatus,
)
from windagent_core.events.video_production_ir import (
    IrEventIdempotencyGuard,
    ProductionIrEventCatalog,
    ProductionIrEventEnvelope,
    ProductionIrEventTransitions,
)

from tests.fixtures.video_production.ir_fixture_builder import (
    build_derived_artifact,
    build_valid_ir,
    build_valid_shot_intent,
)


class FakeEngineAdapter:
    """Minimal fake implementing ProductionEnginePort semantics."""

    def __init__(self) -> None:
        self.submitted: list = []
        self._jobs: dict = {}

    async def submit_scene(self, scene, render):
        receipt = EngineJobReceipt(
            job_id=EngineJobId("ej_scene_0001"),
            project_id="vp_ir_0001",
            revision_id="rev_0001",
            ir_hash=str(render.profile.profile_id),
            engine_name="fake-engine",
        )
        self.submitted.append(("scene", scene.scene_id))
        self._jobs[receipt.job_id] = receipt
        return receipt

    async def submit_shot(self, intent, render):
        receipt = EngineJobReceipt(
            job_id=EngineJobId(f"ej_{intent.shot_id}"),
            project_id="vp_ir_0001",
            revision_id="rev_0001",
            ir_hash=str(render.profile.profile_id),
            engine_name="fake-engine",
        )
        self.submitted.append(("shot", intent.shot_id))
        self._jobs[receipt.job_id] = receipt
        return receipt

    async def inspect_job(self, job_id):
        return self._jobs.get(job_id, EngineJobReceipt(
            job_id=job_id,
            project_id="vp_unknown",
            revision_id="rev_unknown",
            status=EngineJobStatus.FAILED,
            error="unknown job",
        ))

    async def cancel_job(self, job_id):
        receipt = self._jobs.get(job_id)
        if receipt is not None:
            receipt = receipt.model_copy(update={"status": EngineJobStatus.CANCELLED})
            self._jobs[job_id] = receipt
        return receipt

    async def download_artifact(self, job_id, artifact_kind):
        return build_derived_artifact().model_copy(
            update={"job_id": job_id, "kind": artifact_kind}
        )


class TestPortConformance:
    def test_port_is_runtime_checkable(self):
        fake = FakeEngineAdapter()
        assert isinstance(fake, ProductionEnginePort)

    def test_port_has_no_engine_or_flow_leakage(self):
        import ast

        source = inspect.getsource(ProductionEnginePort)
        tree = ast.parse(source)
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    identifiers.add(alias.name.lower())
            elif isinstance(node, ast.ImportFrom) and node.module:
                identifiers.add(node.module.lower())
                for alias in node.names:
                    identifiers.add(alias.name.lower())
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.arg)):
                identifiers.add(getattr(node, "name", "").lower())
        # The port may NAME blender/unreal in prose (they are what adapters
        # target); it must never IMPORT or reference engine SDK objects or
        # Flow prompts as identifiers.
        for forbidden in ("bpy", "generation_mode", "selector", "cookie", "flow_prompt"):
            assert forbidden not in identifiers, f"ProductionEnginePort leaks {forbidden}"


class TestFakeEngineConsumesIR:
    def test_same_ir_consumed_by_fake_engine(self):
        import asyncio

        fake = FakeEngineAdapter()
        intent = build_valid_shot_intent()
        render = build_valid_ir().render_intents[0]

        receipt_shot = asyncio.run(fake.submit_shot(intent, render))
        receipt_scene = asyncio.run(fake.submit_scene(build_valid_ir().scenes[0], render))
        assert receipt_shot.status == EngineJobStatus.SUBMITTED
        assert receipt_scene.status == EngineJobStatus.SUBMITTED
        assert fake.submitted[0] == ("shot", intent.shot_id)
        assert fake.submitted[1] == ("scene", build_valid_ir().scenes[0].scene_id)

    def test_receipt_and_artifact_round_trip(self):
        import asyncio

        fake = FakeEngineAdapter()
        intent = build_valid_shot_intent()
        render = build_valid_ir().render_intents[0]

        receipt = asyncio.run(fake.submit_shot(intent, render))
        inspected = asyncio.run(fake.inspect_job(receipt.job_id))
        assert inspected.status == EngineJobStatus.SUBMITTED
        assert inspected.ir_hash

        artifact = asyncio.run(
            fake.download_artifact(receipt.job_id, DerivedArtifactKind.FRAME_SEQUENCE)
        )
        assert isinstance(artifact, DerivedArtifact)
        assert artifact.derived_from_ir_hash
        assert artifact.kind == DerivedArtifactKind.FRAME_SEQUENCE


class TestIrEvents:
    def test_ir_event_transitions_are_enforced(self):
        cat = ProductionIrEventCatalog
        assert ProductionIrEventTransitions.can_transition(cat.IR_CREATED, cat.IR_LOCKED)
        assert ProductionIrEventTransitions.can_transition(cat.IR_LOCKED, cat.ENGINE_JOB_SUBMITTED)
        assert ProductionIrEventTransitions.can_transition(
            cat.ENGINE_JOB_SUBMITTED, cat.ENGINE_JOB_COMPLETED
        )
        assert ProductionIrEventTransitions.can_transition(
            cat.ENGINE_JOB_FAILED, cat.ENGINE_JOB_SUBMITTED  # retry
        )
        assert ProductionIrEventTransitions.can_transition(
            cat.ENGINE_JOB_COMPLETED, cat.DERIVED_ARTIFACT_PUBLISHED
        )
        # illegal: skipping straight to a completed artifact before submission
        assert not ProductionIrEventTransitions.can_transition(cat.IR_CREATED, cat.ENGINE_JOB_COMPLETED)

    def test_ir_event_sequence_validation(self):
        cat = ProductionIrEventCatalog
        seq = [
            cat.IR_CREATED,
            cat.IR_LOCKED,
            cat.ENGINE_JOB_SUBMITTED,
            cat.ENGINE_JOB_COMPLETED,
            cat.DERIVED_ARTIFACT_PUBLISHED,
        ]
        assert ProductionIrEventTransitions.validate_sequence(seq) is None
        bad = [cat.IR_CREATED, cat.DERIVED_ARTIFACT_PUBLISHED]
        assert ProductionIrEventTransitions.validate_sequence(bad) is not None

    def test_ir_event_lifecycle_valid(self):
        env = ProductionIrEventEnvelope(
            event_type=ProductionIrEventCatalog.IR_CREATED,
            project_id="vp_ir_0001",
            revision_id="rev_0001",
            ir_id="ir_0001",
            aggregate_id="vp_ir_0001",
        )
        assert env.to_dict()["event_type"] == ProductionIrEventCatalog.IR_CREATED

    def test_event_idempotency_guard(self):
        guard = IrEventIdempotencyGuard()
        env = ProductionIrEventEnvelope(
            event_type=ProductionIrEventCatalog.ENGINE_JOB_SUBMITTED,
            project_id="vp_ir_0001",
            revision_id="rev_0001",
            ir_id="ir_0001",
            aggregate_id="vp_ir_0001",
        )
        assert guard.process(env) is True
        assert guard.process(env) is False


class TestEngineExecutorConsumer:
    """VP3D Stage A consumer cutover (audit finding #1): the worker-facing
    `ProductionEngineExecutor` dispatches IR units through a real
    `ProductionEnginePort`, persists receipts durably, and a restarted worker
    can re-attach to in-flight jobs WITHOUT blind resubmit.
    """

    def _executor(self, tmp_path):
        from windagent_orchestration.production import ProductionEngineExecutor

        engine = FakeEngineAdapter()
        return ProductionEngineExecutor(port=engine, state_dir=tmp_path / "exec_state"), engine

    def test_executor_dispatch_submit_and_persist(self, tmp_path):
        import asyncio

        executor, engine = self._executor(tmp_path)
        intent = build_valid_shot_intent()
        render = build_valid_ir().render_intents[0]

        receipt = asyncio.run(executor.submit_shot(intent, render))
        assert receipt.status == EngineJobStatus.SUBMITTED
        assert engine.submitted == [("shot", intent.shot_id)]
        # Receipt persisted for durable re-attach.
        assert len(executor.persisted_receipts()) == 1
        assert executor.persisted_receipts()[0].job_id == receipt.job_id

    def test_executor_cancel_persists_terminal_state(self, tmp_path):
        import asyncio

        executor, _ = self._executor(tmp_path)
        intent = build_valid_shot_intent()
        render = build_valid_ir().render_intents[0]

        submitted = asyncio.run(executor.submit_shot(intent, render))
        cancelled = asyncio.run(executor.cancel_job(submitted.job_id))
        assert cancelled.status == EngineJobStatus.CANCELLED
        assert executor.has_terminal(submitted.job_id) is True

    def test_executor_restart_reconciles_before_resubmit(self, tmp_path):
        """A NEW executor over the same state dir simulates a worker restart:
        its reconcile() sees the durable receipt and flags a terminal job so the
        caller never blind-resubmits over a finished one (plan §5 recovery)."""
        import asyncio

        from windagent_orchestration.production import ProductionEngineExecutor

        intent = build_valid_shot_intent()
        render = build_valid_ir().render_intents[0]

        # Worker v1 submits + cancels.
        exec1 = ProductionEngineExecutor(
            port=FakeEngineAdapter(), state_dir=tmp_path / "exec_state"
        )
        submitted = asyncio.run(exec1.submit_shot(intent, render))
        asyncio.run(exec1.cancel_job(submitted.job_id))

        # Worker v2 restarts over the SAME durable state.
        exec2 = ProductionEngineExecutor(
            port=FakeEngineAdapter(), state_dir=tmp_path / "exec_state"
        )
        persisted = exec2.reconcile(submitted.job_id)
        assert persisted is not None
        assert persisted.status == EngineJobStatus.CANCELLED
        assert exec2.has_terminal(submitted.job_id) is True

    def test_executor_unknown_job_reconciles_to_none(self, tmp_path):
        executor, _ = self._executor(tmp_path)
        assert executor.reconcile(EngineJobId("ej_nonexistent")) is None
        assert executor.has_terminal(EngineJobId("ej_nonexistent")) is False
