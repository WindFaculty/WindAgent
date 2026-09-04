"""Job handlers for Production (executed by the worker runtime)."""

from __future__ import annotations

from collections.abc import Mapping

from windagent.kernel.types.json import JSONValue

from ..application.runtime import ProductionServices


class _BaseProductionJobHandler:
    def __init__(self, services: ProductionServices | None = None) -> None:
        self._services = services


class ProductionRenderJobHandler(_BaseProductionJobHandler):
    job_type = "production.render.execute"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        edl_data = payload.get("edl_data") if isinstance(payload, dict) else None
        output_path = payload.get("output_path") if isinstance(payload, dict) else None

        if isinstance(edl_data, dict) and output_path:
            from pathlib import Path
            from ..render import RenderJobState, RenderService

            resolver = {}
            if "asset_resolver" in payload and isinstance(payload["asset_resolver"], dict):
                resolver = {k: Path(str(v)) for k, v in payload["asset_resolver"].items()}

            service = RenderService()
            state, validation, err = await service.execute_render_job(
                job_id=job_id,
                edl_data=edl_data,
                output_path=Path(str(output_path)),
                asset_resolver=resolver,
            )

            if state != RenderJobState.READY:
                raise RuntimeError(f"Production render failed for job '{job_id}': {err}")

            return {
                "job_id": job_id,
                "status": state.value,
                "output_file": str(output_path),
                "validation": validation.to_dict() if validation else None,
            }

        return {"job_id": job_id, "status": "COMPLETED"}


class ProductionPostprocessJobHandler(_BaseProductionJobHandler):
    job_type = "production.postprocess.assemble"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        return {"job_id": job_id, "status": "COMPLETED"}


class ProductionAssetNormalizeJobHandler(_BaseProductionJobHandler):
    job_type = "production.asset.normalize"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        return {"job_id": job_id, "status": "COMPLETED"}


class ProductionCodeVideoVerifyJobHandler(_BaseProductionJobHandler):
    job_type = "production.code_video.verify"

    async def handle(self, payload: Mapping[str, JSONValue]) -> object:
        job_id = str(payload.get("job_id", "")) if isinstance(payload, dict) else ""
        return {"job_id": job_id, "status": "COMPLETED"}


# Compatibility function aliases for direct JobRegistration use (if needed)
async def handle_production_render(payload: Mapping[str, JSONValue]) -> object:
    return await ProductionRenderJobHandler().handle(payload)


async def handle_production_postprocess(payload: Mapping[str, JSONValue]) -> object:
    return await ProductionPostprocessJobHandler().handle(payload)


async def handle_production_asset_normalize(payload: Mapping[str, JSONValue]) -> object:
    return await ProductionAssetNormalizeJobHandler().handle(payload)


async def handle_production_code_video_verify(payload: Mapping[str, JSONValue]) -> object:
    return await ProductionCodeVideoVerifyJobHandler().handle(payload)
