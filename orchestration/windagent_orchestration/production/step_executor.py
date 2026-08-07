"""
ProductionStepExecutor — StepExecutorPort that dispatches RENDER steps through
`ProductionEngineExecutor` (VP3D Stage A consumer cutover).

This is the REAL runtime call site the Stage A cutover required: a queued
RENDER step in the durable production workflow actually goes through
`ProductionEngineExecutor` -> `ProductionEnginePort` + IR. The engine port is
injected (engine-neutral) — the workflow never depends on a concrete engine
adapter (Blender, Unreal, ...).

Dispatch contract (plan 05 §8.5 / Stage A §5.2):

- `RENDER_ASSETS`: for every IR scene, `executor.submit_scene(scene, render)`
  — the scene compiles the approved assets onto the engine.
- `RENDER_SHOTS`: for every IR shot intent, `executor.submit_shot(intent,
  render)` — each shot render is an engine job.
- Receipts are persisted by the executor for durable re-attach.
- The step returns `waiting_provider` with a `PendingExternalOperation` whose
  `request_hash` is the IR content hash and whose `external_id` is the engine
  job id — the engine never blindly resubmits over a job it already knows
  (inspect-before-resubmit is enforced by `ProductionEngineExecutor.reconcile`
  and by `ProductionWorkflowEngine.recover`).

`ir_source(revision_id)` loads the engine-neutral IR document for the run's
revision (the runtime builds it at LOCK_SHOT_PLAN / migration time). A missing
IR fails closed: the step fails instead of submitting garbage.

Non-RENDER steps are delegated to an injected `fallback` handler so the
workflow can progress to the RENDER steps; the default completes them with a
deterministic output hash derived from the run's revision hash + step id
(their planning artifacts are pre-baked into the locked package).
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Callable, Dict, List, Optional

from windagent_core.domain.video_production.production_ir.models import (
    ProductionIrDocument,
)

from windagent_orchestration.production.checkpoint import PendingExternalOperation
from windagent_orchestration.production.engine import (
    ProductionRun,
    StepExecutionResult,
    StepExecutorPort,
)
from windagent_orchestration.production.engine_executor import (
    ProductionEngineExecutor,
)

RENDER_ASSETS = "RENDER_ASSETS"
RENDER_SHOTS = "RENDER_SHOTS"
ENGINE_STEPS = frozenset({RENDER_ASSETS, RENDER_SHOTS})


class ProductionStepExecutor(StepExecutorPort):
    """Workflow step executor that dispatches RENDER steps through the
    engine-neutral `ProductionEngineExecutor` seam."""

    def __init__(
        self,
        *,
        engine: ProductionEngineExecutor,
        ir_source: Callable[[str], ProductionIrDocument],
        fallback: Optional[Callable[[str, ProductionRun], StepExecutionResult]] = None,
    ) -> None:
        self._engine = engine
        self._ir_source = ir_source
        self._fallback = fallback or _default_planning_step_result

    # ------------------------------------------------------------------
    # StepExecutorPort (sync) — used by the file-backed workflow engine.
    # ------------------------------------------------------------------
    def execute(self, step_id: str, run: ProductionRun) -> StepExecutionResult:
        """Execute one step; RENDER steps dispatch through the engine seam."""
        if step_id not in ENGINE_STEPS:
            return self._fallback(step_id, run)
        try:
            return asyncio.run(self._execute_engine_step(step_id, run))
        except Exception as exc:  # fail closed: never pretend a render succeeded
            return StepExecutionResult(
                step_id=step_id,
                status="failed",
                error=f"RENDER step {step_id} failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Async variant — callable from an async worker (no asyncio.run bridge).
    # ------------------------------------------------------------------
    async def async_execute(self, step_id: str, run: ProductionRun) -> StepExecutionResult:
        if step_id not in ENGINE_STEPS:
            return self._fallback(step_id, run)
        try:
            return await self._execute_engine_step(step_id, run)
        except Exception as exc:  # fail closed
            return StepExecutionResult(
                step_id=step_id,
                status="failed",
                error=f"RENDER step {step_id} failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Engine dispatch
    # ------------------------------------------------------------------
    async def _execute_engine_step(
        self, step_id: str, run: ProductionRun
    ) -> StepExecutionResult:
        ir = self._ir_source(run.revision_id)
        if ir is None:
            return StepExecutionResult(
                step_id=step_id,
                status="failed",
                error=(
                    f"No IR document available for revision {run.revision_id}; "
                    "RENDER step fails closed (no IR -> no submit)."
                ),
            )

        ir_hash = ir.content_hash()
        job_ids: List[str] = []
        output_hashes: Dict[str, str] = {}

        if step_id == RENDER_ASSETS:
            for scene in ir.scenes:
                render = _render_intent_for(ir, scene.scene_id)
                if render is None:
                    continue
                receipt = await self._engine.submit_scene(scene, render)
                job_ids.append(str(receipt.job_id))
                output_hashes[str(receipt.job_id)] = receipt.ir_hash or ir_hash
        else:  # RENDER_SHOTS
            for intent in ir.shots:
                render = _render_intent_for(ir, intent.scene_id)
                if render is None:
                    continue
                receipt = await self._engine.submit_shot(intent, render)
                job_ids.append(str(receipt.job_id))
                output_hashes[str(receipt.job_id)] = receipt.ir_hash or ir_hash

        if not job_ids:
            return StepExecutionResult(
                step_id=step_id,
                status="failed",
                error=(
                    f"RENDER step {step_id} found no IR units to submit "
                    f"(revision {run.revision_id})."
                ),
            )

        # The durable engine op the workflow reconciles against. A RENDER
        # step submits one engine job PER scene/shot unit, so the pending op
        # must carry EVERY engine job of the batch (not just job_ids[0]) —
        # otherwise a crash after a later job was submitted loses that job
        # from recovery (VP3D: track every engine job, not just the first).
        pending = PendingExternalOperation(
            step_id=step_id,
            provider="engine",
            request_hash=ir_hash,
            external_id=job_ids[0],
            job_ids=list(job_ids),
        )
        return StepExecutionResult(
            step_id=step_id,
            status="waiting_provider",
            output_hashes=output_hashes,
            pending_external_operation=pending,
            candidate_count=len(job_ids),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _render_intent_for(ir: ProductionIrDocument, scene_id: object):
    for render in ir.render_intents:
        if str(render.scene_id) == str(scene_id):
            return render
    return None


def _default_planning_step_result(step_id: str, run: ProductionRun) -> StepExecutionResult:
    """Deterministic completion for non-RENDER steps in the current runtime.

    Planning artifacts (concepts, screenplay, bibles, shot plan) are authored
    into the locked package before the workflow reaches the RENDER steps; the
    runtime records a deterministic output hash per step for traceability.
    """
    seed = f"{run.revision_hash}:{step_id}"
    output_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return StepExecutionResult(
        step_id=step_id,
        status="completed",
        output_hashes={step_id: output_hash},
    )


__all__ = ["ProductionStepExecutor", "RENDER_ASSETS", "RENDER_SHOTS", "ENGINE_STEPS"]
