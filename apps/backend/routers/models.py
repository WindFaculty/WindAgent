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


@router.delete("/{model_id}")
async def delete_model(request: Request, model_id: str) -> Dict[str, Any]:
    """Remove a model from the registry entirely."""
    service = _service(request)
    res = await service.delete_model(model_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@router.delete("/providers/{provider_id}/api-key")
async def clear_provider_api_key(request: Request, provider_id: str) -> Dict[str, Any]:
    """Clear the API key stored for a provider."""
    service = _service(request)
    res = await service.clear_provider_api_key(provider_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


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
            masked_key = ""
            if p.provider_type == "cloud":
                if p.api_key:
                    has_key = True
                    from utils.encryption import decrypt, mask_api_key
                    try:
                        dec_key = decrypt(p.api_key)
                        masked_key = mask_api_key(dec_key)
                    except Exception:
                        masked_key = "••••••••••••"
                elif p.api_key_env:
                    val = os.environ.get(p.api_key_env)
                    has_key = bool(val)
                    if val:
                        from utils.encryption import mask_api_key
                        masked_key = mask_api_key(val)
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
                "apiKey": masked_key,
                "baseUrl": p.base_url,
                "notes": p.notes,
            })
        return result


@router.get("/providers/{provider_id}/api-key")
async def get_provider_api_key(request: Request, provider_id: str) -> Dict[str, Any]:
    """Retrieve the decrypted API key for a provider."""
    service = _service(request)
    async with service.db.session() as session:
        from sqlalchemy import select
        from db.models import ModelProviderORM
        stmt = select(ModelProviderORM).where(ModelProviderORM.id == provider_id)
        res = await session.execute(stmt)
        provider = res.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        decrypted_key = ""
        if provider.api_key:
            from utils.encryption import decrypt
            try:
                decrypted_key = decrypt(provider.api_key)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to decrypt key: {exc}")
        elif provider.api_key_env:
            decrypted_key = os.environ.get(provider.api_key_env, "")
            
        return {"api_key": decrypted_key}



@router.post("/providers/{provider_id}/sync")
async def sync_provider(
    request: Request,
    provider_id: str,
    payload: Optional[Dict[str, Any]] = Body(None)
) -> Dict[str, Any]:
    """Sync model catalog from the target provider, optionally enabling only selected model IDs."""
    service = _service(request)
    selected_model_ids = None
    if payload and "selected_models" in payload:
        selected_model_ids = payload["selected_models"]
        
    res = await service.sync_provider_models(provider_id, selected_model_ids)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.patch("/providers/{provider_id}/models/selection")
async def update_model_selection(
    request: Request,
    provider_id: str,
    payload: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Update which models are enabled/disabled for a provider without re-fetching from API.
    
    Body: { "selected_models": ["model-id-1", "model-id-2", ...] }
    All models in the list are enabled; all others are disabled.
    """
    service = _service(request)
    selected_model_ids: List[str] = payload.get("selected_models", [])
    res = await service.update_model_selection(provider_id, selected_model_ids)
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


class ProviderCreate(BaseModel):
    id: str
    name: str
    api_source: str  # "openai" or "anthropic" or "google" etc.
    base_url: str
    api_key: Optional[str] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    api_source: Optional[str] = None
    base_url: Optional[str] = None
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


@router.post("/providers")
async def create_provider(request: Request, payload: ProviderCreate) -> Dict[str, Any]:
    """Create a new custom provider configuration."""
    service = _service(request)
    async with service.db.session() as session:
        from sqlalchemy import select
        from db.models import ModelProviderORM
        stmt = select(ModelProviderORM).where(ModelProviderORM.id == payload.id)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Provider with this ID already exists.")
        
        provider = ModelProviderORM(
            id=payload.id,
            site_name=payload.name,
            api_source=payload.api_source,
            base_url=payload.base_url,
            api_key=payload.api_key,
            provider_type="cloud",
            quota_mode="RPM_RPD",
            supports_openai_compatible=True if payload.api_source != "google" else False,
            supports_model_discovery=True,
            enabled=True,
        )
        session.add(provider)
        await session.commit()
        return {"status": "success", "message": f"Provider {provider.site_name} created successfully."}


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
        
        if payload.name is not None:
            provider.site_name = payload.name
        if payload.api_source is not None:
            provider.api_source = payload.api_source
        if payload.base_url is not None:
            provider.base_url = payload.base_url
        if payload.api_key is not None:
            provider.api_key = payload.api_key
            
        await session.commit()
        return {"status": "success", "message": "Provider updated successfully."}


class ProviderTestRequest(BaseModel):
    api_source: str
    base_url: str
    api_key: Optional[str] = None


@router.post("/providers/test-connection")
async def test_provider_connection(request: Request, payload: ProviderTestRequest) -> Dict[str, Any]:
    """Test connection to a provider and retrieve available models."""
    service = _service(request)
    
    # Determine api_source format
    if payload.api_source == "google":
        from services.provider_clients.google_gemini import GoogleGeminiClient
        client = GoogleGeminiClient(
            provider_id="temp_test",
            base_url=payload.base_url,
            api_key=payload.api_key,
        )
    elif payload.api_source == "anthropic":
        from services.provider_clients.anthropic import AnthropicClient
        client = AnthropicClient(
            provider_id="temp_test",
            base_url=payload.base_url,
            api_key=payload.api_key,
        )
    else:
        from services.provider_clients.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(
            provider_id="temp_test",
            base_url=payload.base_url,
            api_key=payload.api_key,
        )
        
    try:
        models_list = await client.list_models()
        # Format list for frontend
        formatted_models = []
        for m in models_list:
            formatted_models.append({
                "model_id": m["model_id"],
                "display_name": m["display_name"],
                "capabilities": m["capabilities"],
            })
        return {
            "status": "success",
            "message": f"Endpoint OK - Đã lấy {len(formatted_models)} models từ endpoint",
            "models": formatted_models
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(exc)}")


@router.delete("/providers/{provider_id}")
async def delete_provider(request: Request, provider_id: str) -> Dict[str, Any]:
    """Delete a provider entirely from database along with its registered models."""
    service = _service(request)
    async with service.db.session() as session:
        from sqlalchemy import select, delete
        from db.models import ModelProviderORM, ModelCatalogORM, ModelRuntimeStatusORM
        # 1. Fetch provider
        stmt = select(ModelProviderORM).where(ModelProviderORM.id == provider_id)
        res = await session.execute(stmt)
        provider = res.scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        
        # 2. Find and delete its models' runtime status first
        stmt_models = select(ModelCatalogORM.id).where(ModelCatalogORM.provider_id == provider_id)
        res_models = await session.execute(stmt_models)
        model_ids = res_models.scalars().all()
        
        if model_ids:
            await session.execute(
                delete(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id.in_(model_ids))
            )
            await session.execute(
                delete(ModelCatalogORM).where(ModelCatalogORM.provider_id == provider_id)
            )
            
        # 3. Delete provider
        await session.execute(
            delete(ModelProviderORM).where(ModelProviderORM.id == provider_id)
        )
        await session.commit()
        
        await service.log_activity(
            model_id=None,
            provider_id=provider_id,
            event_type="deleted",
            message=f"Provider {provider.site_name} deleted.",
        )
        return {"status": "success", "message": f"Provider {provider_id} deleted successfully."}