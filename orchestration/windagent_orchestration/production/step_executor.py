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

from windagent_core.contracts.video_production.asset_resolver import (
    AssetResolverPort,
)
from windagent_core.domain.video_production.asset_resolution import (
    AssetKind,
    AssetRequirement,
    AssetResolutionRequest,
    AssetResolutionStatus,
)
from windagent_core.domain.video_production.production_ir.models import (
    AssetReference,
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
        asset_gateway: Optional[AssetResolverPort] = None,
    ) -> None:
        self._engine = engine
        self._ir_source = ir_source
        self._fallback = fallback or _default_planning_step_result
        self._asset_gateway = asset_gateway

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

    async def _resolve_pending_ir_assets(self, ir: ProductionIrDocument) -> str:
        """Resolve every pending IR asset reference through the gateway.

        Returns an error string when ANY pending asset could not be resolved
        to an APPROVED (RESOLVED) asset — fail closed, never proceed with a
        QUARANTINED/REJECTED/errored acquisition.
        """
        if self._asset_gateway is None:
            return ""
        pending = collect_pending_asset_references(ir)
        failures: List[str] = []
        for instance_id, ref in pending:
            kind = _ROLE_KINDS.get(ref.role, AssetKind.PROP)
            requirement = AssetRequirement(
                kind=kind,
                description=f"IR asset {ref.asset_id} ({ref.role})",
                metadata={"asset_id": str(ref.asset_id), "role": ref.role},
            )
            request = AssetResolutionRequest(requirement=requirement)
            try:
                # Canonical gateway flow: discover -> acquire (both through
                # AssetResolverPort; the gateway never bypasses its adapters).
                discovered = await self._asset_gateway.discover(request)
                if not discovered.candidates:
                    failures.append(
                        f"{instance_id}: no candidate found for {ref.role}"
                    )
                    continue
                result = await self._asset_gateway.acquire(
                    discovered.candidates[0], request
                )
            except Exception as exc:  # fail closed on any gateway error
                failures.append(f"{instance_id}: gateway error {exc}")
                continue
            if result.status != AssetResolutionStatus.RESOLVED:
                failures.append(
                    f"{instance_id}: asset resolution {result.status.value} "
                    f"({result.metadata.get('trust_decision', 'n/a')})"
                )
        if failures:
            return (
                "RENDER_ASSETS asset gateway failed closed: "
                + "; ".join(failures)
            )
        return ""

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

        # VP3D Phase 5: EVERY asset need goes through the gateway
        # (AssetResolverPort). RENDER_ASSETS first resolves any asset
        # references the IR marks as pending; a quarantined/rejected/errored
        # resolution fails the step closed — an untrusted asset never reaches
        # the engine.
        if step_id == RENDER_ASSETS:
            resolution_error = await self._resolve_pending_ir_assets(ir)
            if resolution_error:
                return StepExecutionResult(
                    step_id=step_id,
                    status="failed",
                    error=resolution_error,
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
PENDING_URI_PREFIX = "pending:"

_ROLE_KINDS = {
    "CHARACTER_MESH": AssetKind.CHARACTER,
    "SKELETON": AssetKind.CHARACTER,
    "PROP": AssetKind.PROP,
    "ENVIRONMENT": AssetKind.ENVIRONMENT,
    "TEXTURE": AssetKind.TEXTURE,
    "MATERIAL": AssetKind.MATERIAL,
}


def collect_pending_asset_references(
    ir: ProductionIrDocument,
) -> List[tuple[str, AssetReference]]:
    """Asset references the IR marks as not-yet-acquired (pending: URIs).

    Only references WITHOUT resolved bytes (empty or ``pending:`` uri) need
    gateway acquisition; everything else is already content-addressed.
    """
    refs: List[tuple[str, AssetReference]] = []
    for scene in ir.scenes:
        for character in scene.characters:
            if character.mesh is not None:
                refs.append((str(character.instance_id), character.mesh))
        for prop in scene.props:
            refs.append((str(prop.instance_id), prop.asset))
        for environment in scene.environment:
            refs.append((str(environment.instance_id), environment.asset))
    return [
        (instance_id, ref)
        for instance_id, ref in refs
        if ref is not None
        and (not ref.uri or ref.uri.startswith(PENDING_URI_PREFIX))
    ]


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
