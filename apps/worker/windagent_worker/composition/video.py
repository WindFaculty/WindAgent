"""Guarded Blender/video production composition for Worker."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from windagent_worker.composition.settings import WorkerRuntimeSettings

logger = logging.getLogger("windagent.worker.composition.video")


def _load_ir_document(artifact_root: str, revision_id: str):
    """Load engine-neutral IR or fail closed when it is absent/invalid."""
    from windagent_core.domain.video_production.production_ir import (
        ProductionIrDocument,
    )

    path = os.path.join(
        artifact_root, "video_production_3d", "ir", f"{revision_id}.ir.json"
    )
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return ProductionIrDocument.model_validate(json.load(fh))
    except (OSError, ValueError) as exc:
        logger.warning("Failed to load IR for revision %s: %s", revision_id, exc)
        return None


@dataclass(frozen=True)
class VideoBundle:
    production_engine: Any | None = None
    production_executor: Any | None = None
    production_step_executor: Any | None = None
    production_workflow: Any | None = None


class VideoComposer:
    """Compose the guarded Blender production pipeline."""

    @staticmethod
    def compose(settings: WorkerRuntimeSettings) -> VideoBundle:
        if not settings.blender_engine:
            return VideoBundle()

        from windagent_orchestration.production import (
            ProductionEngineExecutor,
            ProductionRunStore,
            ProductionStepExecutor,
            ProductionWorkflowEngine,
        )
        from windagent_tools.production_engines.blender import (
            create_blender_engine_adapter,
        )
        from windagent_workflows.video_production.definition import (
            build_production_step_nodes,
        )

        artifact_root = settings.artifact_root
        production_engine = create_blender_engine_adapter(
            artifact_root=artifact_root,
            state_dir=os.path.join(
                artifact_root, "video_production_3d", "blender_state"
            ),
        )
        production_executor = ProductionEngineExecutor(
            port=production_engine,
            state_dir=os.path.join(
                artifact_root, "video_production_3d", "executor_state"
            ),
        )
        production_step_executor = ProductionStepExecutor(
            engine=production_executor,
            ir_source=lambda revision_id: _load_ir_document(
                artifact_root, revision_id
            ),
        )
        production_workflow = ProductionWorkflowEngine(
            store=ProductionRunStore(
                os.path.join(artifact_root, "video_production_3d", "runs")
            ),
            executor=production_step_executor,
            step_nodes=build_production_step_nodes(),
        )
        logger.warning(
            "DEPRECATED AUTHORITY: ProductionWorkflowEngine is composed only "
            "for VP3D paths and rejects Studio story steps."
        )
        return VideoBundle(
            production_engine=production_engine,
            production_executor=production_executor,
            production_step_executor=production_step_executor,
            production_workflow=production_workflow,
        )


__all__ = ["VideoBundle", "VideoComposer", "_load_ir_document"]
