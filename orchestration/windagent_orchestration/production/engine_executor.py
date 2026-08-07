"""
ProductionEngineExecutor — engine-neutral worker-facing facade over
`ProductionEnginePort` (VP3D Stage A Phase 2 consumer cutover).

`ProductionEnginePort` (core contract) is the engine adapter contract. This
executor is the WORKER-side consumer: the seam a workflow RENDER step
dispatches through. It delegates to the composed `ProductionEnginePort` and
keeps a durable receipt log so a restarted worker can re-attach to in-flight
jobs (plan Stage A §5.2: composition root / workflow dispatch onto
ProductionEnginePort + IR; §5 recovery: "inspect durable state + provider
before retry; never blind resubmit").

LAYERING: the executor lives in the orchestration layer (not core/contracts)
because it is a concrete implementation with filesystem persistence — core
keeps only the protocol/type contract (`ProductionEnginePort`).

It is engine-neutral by construction — it never sees a Flow prompt, a
generation mode, or an engine SDK object. The concrete engine (Blender,
Unreal, fake) is injected via the port.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from windagent_core.contracts.video_production.production_engine import ProductionEnginePort
from windagent_core.domain.video_production.ids import EngineJobId
from windagent_core.domain.video_production.production_ir.enums import DerivedArtifactKind
from windagent_core.domain.video_production.production_ir.models import (
    DerivedArtifact,
    EngineJobReceipt,
    EngineJobStatus,
    RenderIntent,
    SceneDescription,
    ShotExecutionIntent,
)


class ProductionEngineExecutor:
    """Worker-facing facade over a composed `ProductionEnginePort`.

    Arguments
    ---------
    port:
        The engine adapter (Blender, Unreal, fake) implementing
        `ProductionEnginePort`. Never None in the canonical composition.
    state_dir:
        Directory where job receipts are persisted for durable re-attach on
        worker restart. `None` disables persistence (in-memory only), which is
        useful for tests and for engines that own their own durable state.

    Every `submit_*` returns a `EngineJobReceipt` that is also persisted;
    `reconcile()` lists persisted receipts so a restarted worker can inspect
    BEFORE blindly resubmitting.
    """

    def __init__(self, port: ProductionEnginePort, state_dir: str | Path | None = None) -> None:
        self._port = port
        self._state_dir = Path(state_dir) if state_dir is not None else None
        if self._state_dir is not None:
            self._state_dir.mkdir(parents=True, exist_ok=True)

    # -- engine-neutral job dispatch --------------------------------------
    async def submit_shot(
        self, intent: ShotExecutionIntent, render: RenderIntent
    ) -> EngineJobReceipt:
        receipt = await self._port.submit_shot(intent, render)
        self._persist(receipt)
        return receipt

    async def submit_scene(
        self, scene: SceneDescription, render: RenderIntent
    ) -> EngineJobReceipt:
        receipt = await self._port.submit_scene(scene, render)
        self._persist(receipt)
        return receipt

    async def inspect_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        return await self._port.inspect_job(job_id)

    async def cancel_job(self, job_id: EngineJobId) -> EngineJobReceipt:
        receipt = await self._port.cancel_job(job_id)
        self._persist(receipt)
        return receipt

    async def download_artifact(
        self, job_id: EngineJobId, artifact_kind: DerivedArtifactKind
    ) -> DerivedArtifact:
        return await self._port.download_artifact(job_id, artifact_kind)

    # -- durable re-attach (worker restart) -------------------------------
    def _receipt_path(self, job_id: EngineJobId) -> Path | None:
        if self._state_dir is None:
            return None
        safe = str(job_id).replace("/", "_").replace("\\", "_")
        return self._state_dir / f"{safe}.receipt.json"

    def _persist(self, receipt: EngineJobReceipt) -> None:
        path = self._receipt_path(receipt.job_id)
        if path is not None:
            path.write_text(receipt.model_dump_json(), encoding="utf-8")

    def persisted_receipts(self) -> List[EngineJobReceipt]:
        """Receipts on disk — used by a restarted worker to reconcile state."""
        if self._state_dir is None:
            return []
        receipts: List[EngineJobReceipt] = []
        for path in sorted(self._state_dir.glob("*.receipt.json")):
            try:
                receipts.append(
                    EngineJobReceipt.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                )
            except (OSError, ValueError):
                continue
        return receipts

    def reconcile(self, job_id: EngineJobId) -> EngineJobReceipt | None:
        """Restore a job's last-known receipt from durable state, or None.

        Returning None means "no durable record" — the caller must decide
        between a fresh submit and a fail-closed outcome; it must NOT blindly
        resubmit over a job that already reached a terminal state (plan §5).
        """
        for receipt in self.persisted_receipts():
            if receipt.job_id == job_id:
                return receipt
        return None

    def has_terminal(self, job_id: EngineJobId) -> bool:
        """True when the last-known receipt is CANCELLED or FAILED."""
        receipt = self.reconcile(job_id)
        if receipt is None:
            return False
        return receipt.status in (EngineJobStatus.CANCELLED, EngineJobStatus.FAILED)


__all__ = ["ProductionEngineExecutor"]
