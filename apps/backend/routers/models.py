"""Models router — registry, routing, activity, benchmarks, and lifecycle control."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel

from services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["models"])


class ModelCreate(BaseModel):
    name: str
    provider_id: str
    model_id: str
    type: str = "API"
    base_url: Optional[str] = None
    capabilities: List[str] = ["chat"]
    tags: List[str] = []
    roles: List[str] = []


class ImportRequest(BaseModel):
    source: str
    model_name: str


class BenchmarkRequest(BaseModel):
    model_ids: List[str]
    test_name: str = "smoke"
    prompt: str = "Say OK in one sentence."
    max_tokens: int = 16


def _service(request: Request) -> ModelService:
    return request.app.state.model_service


# Keep existing GET /health for backward compatibility
@router.get("/health")
async def models_health(request: Request) -> Dict[str, Any]:
    """Probe the configured model provider (compatibility path)."""
    planner = request.app.state.planner_service
    return await planner.health()


@router.get("")
async def list_models(request: Request) -> List[Dict[str, Any]]:
    """List all registered models with their current runtime statuses and quota details."""
    service = _service(request)
    return await service.list_models()


@router.post("")
async def add_model(request: Request, config: ModelCreate) -> Dict[str, Any]:
    """Register a new model configuration."""
    service = _service(request)
    return await service.add_model(config.model_dump())


@router.post("/import")
async def import_model(request: Request, config: ImportRequest) -> Dict[str, Any]:
    """Queue an import job for a model (e.g. Ollama pull)."""
    service = _service(request)
    return await service.import_model(config.model_dump())


@router.post("/{model_id}/start")
async def start_model(request: Request, model_id: str) -> Dict[str, Any]:
    """Load/start running the model."""
    service = _service(request)
    res = await service.start_model(model_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@router.post("/{model_id}/stop")
async def stop_model(request: Request, model_id: str) -> Dict[str, Any]:
    """Unload/stop running the model."""
    service = _service(request)
    res = await service.stop_model(model_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@router.post("/{model_id}/restart")
async def restart_model(request: Request, model_id: str) -> Dict[str, Any]:
    """Restart the model."""
    service = _service(request)
    res = await service.restart_model(model_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@router.get("/routing")
async def list_routing(request: Request) -> Dict[str, Any]:
    """Get all model routing rules."""
    service = _service(request)
    return await service.routing_service.get_routing_rules()


@router.patch("/routing")
async def update_routing(
    request: Request,
    payload: Dict[str, Dict[str, Optional[str]]] = Body(...),
) -> Dict[str, Any]:
    """Update model routing rules."""
    service = _service(request)
    await service.routing_service.update_routing_rules(payload)
    return {"status": "success", "message": "Routing rules updated successfully."}


@router.post("/{model_id}/set-default")
async def set_default_model(request: Request, model_id: str) -> Dict[str, Any]:
    """Set the default model fallback."""
    service = _service(request)
    return await service.set_default_model(model_id)


@router.get("/{model_id}/logs")
async def get_logs(request: Request, model_id: str) -> List[Dict[str, Any]]:
    """Retrieve logs/activity history for a specific model."""
    service = _service(request)
    return await service.get_logs(model_id)


@router.get("/benchmarks")
async def list_benchmarks(request: Request) -> Dict[str, Any]:
    """Get benchmark metrics formatted for comparison charts."""
    service = _service(request)
    return await service.list_benchmarks()


@router.post("/benchmarks/run")
async def run_benchmark(request: Request, config: BenchmarkRequest) -> Dict[str, Any]:
    """Execute benchmark run for target models."""
    service = _service(request)
    return await service.run_benchmark(config.model_dump())


@router.get("/activity")
async def list_activity(request: Request) -> List[Dict[str, Any]]:
    """List recent activity logs."""
    service = _service(request)
    return await service.list_activity()


@router.get("/providers")
async def list_providers(request: Request) -> List[Dict[str, Any]]:
    """List all providers and their key configuration status."""
    service = _service(request)
    async with service.db.session() as session:
        from sqlalchemy import select
        from db.models import ModelProviderORM
        stmt = select(ModelProviderORM)
        res = await session.execute(stmt)
        providers = res.scalars().all()
        
        result = []
        for p in providers:
            has_key = False
            if p.provider_type == "cloud" and p.api_key_env:
                has_key = bool(os.environ.get(p.api_key_env))
            elif p.provider_type == "local":
                has_key = True

            result.append({
                "id": p.id,
                "name": p.site_name,
                "apiSource": p.api_source,
                "providerType": p.provider_type,
                "quotaMode": p.quota_mode,
                "enabled": p.enabled,
                "hasKey": has_key,
                "notes": p.notes,
            })
        return result


@router.post("/providers/{provider_id}/sync")
async def sync_provider(request: Request, provider_id: str) -> Dict[str, Any]:
    """Sync model catalog from the target provider."""
    service = _service(request)
    res = await service.sync_provider_models(provider_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.get("/providers/{provider_id}/quota")
async def get_quota(request: Request, provider_id: str) -> Dict[str, Any]:
    """Get the latest quota snapshot for a provider."""
    service = _service(request)
    snapshot = await service.quota_service.get_latest_quota(provider_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No quota snapshot found")
    return {
        "provider_id": snapshot.provider_id,
        "quota_mode": snapshot.quota_mode,
        "rpm_limit": snapshot.rpm_limit,
        "rpd_limit": snapshot.rpd_limit,
        "tpm_limit": snapshot.tpm_limit,
        "remaining_requests_today": snapshot.remaining_requests_today,
        "remaining_tokens_today": snapshot.remaining_tokens_today,
        "remaining_credit": snapshot.remaining_credit,
        "reset_at": snapshot.reset_at.isoformat() if snapshot.reset_at else None,
        "source": snapshot.source,
    }


@router.post("/{model_id}/probe")
async def probe_model(request: Request, model_id: str) -> Dict[str, Any]:
    """Execute health probe on model."""
    service = _service(request)
    return await service.probe_model(model_id)


class ModelUpdate(BaseModel):
    model_id: Optional[str] = None
    display_name: Optional[str] = None


class ProviderUpdate(BaseModel):
    api_key: Optional[str] = None


@router.patch("/{id}")
async def update_model_catalog(request: Request, id: str, payload: ModelUpdate) -> Dict[str, Any]:
    """Update model details in catalog."""
    service = _service(request)
    async with service.db.session() as session:
        from sqlalchemy import select
        from db.models import ModelCatalogORM
        stmt = select(ModelCatalogORM).where(ModelCatalogORM.id == id)
        res = await session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise HTTPException(status_code=404, detail="Model not found in catalog")
        
        data = payload.model_dump(exclude_unset=True)
        if "model_id" in data and data["model_id"]:
            model.model_id = data["model_id"]
        if "display_name" in data and data["display_name"]:
            model.display_name = data["display_name"]
            
        await session.commit()
        return {"status": "success", "message": "Model updated successfully."}


@router.patch("/providers/{provider_id}")
async def update_provider(request: Request, provider_id: str, payload: ProviderUpdate) -> Dict[str, Any]:
    """Update provider configuration details."""
    service = _service(request)
    async with service.db.session() as session:
        from sqlalchemy import select
        from db.models import ModelProviderORM
        stmt = select(ModelProviderORM).where(ModelProviderORM.id == provider_id)
        res = await session.execute(stmt)
        provider = res.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        if payload.api_key is not None:
            provider.api_key = payload.api_key
            
        await session.commit()
        return {"status": "success", "message": "Provider updated successfully."}