"""
V3 Models Router — Canonical Model Infrastructure Authority (Phase 12).
Provides canonical model registry, capability matrices, context limits, and endpoint bindings.

Phase 4: model catalog reads are DERIVED from the durable namespaced V3
resource authority (seeded in non-production). No module-level RAM stores.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_MODELS

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

router = APIRouter(prefix="/api/v3/models", tags=["Models V3"])


class ModelEndpointBinding(BaseModel):
    id: str
    endpoint_id: str
    provider_id: str
    provider_model_id: str
    equivalence_level: str = "exact"
    confidence: float = 1.0
    is_active: bool = True


class ModelPricing(BaseModel):
    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None


class ModelDefinitionResource(BaseModel):
    id: str
    name: str
    vendor: str
    family: str
    description: str = ""
    context_window: int = 128000
    max_output_tokens: int = 4096
    capabilities: List[str] = Field(default_factory=list)
    modalities: List[str] = Field(default_factory=list)
    is_local: bool = False
    is_active: bool = True
    pricing: Optional[ModelPricing] = None
    bindings: List[ModelEndpointBinding] = Field(default_factory=list)
    benchmarks: Dict[str, float] = Field(default_factory=dict)
    created_at: str
    updated_at: str


def _model_to_resource(m: Dict[str, Any]) -> ModelDefinitionResource:
    pricing = m.get("pricing")
    return ModelDefinitionResource(
        id=m["id"],
        name=m.get("name", m["id"]),
        vendor=m.get("vendor", ""),
        family=m.get("family", ""),
        description=m.get("description", ""),
        context_window=m.get("context_window", 128000),
        max_output_tokens=m.get("max_output_tokens", 4096),
        capabilities=m.get("capabilities", []),
        modalities=m.get("modalities", []),
        is_local=m.get("is_local", False),
        is_active=m.get("is_active", True),
        pricing=ModelPricing(**pricing) if pricing else None,
        bindings=[ModelEndpointBinding(**b) for b in m.get("bindings", [])],
        benchmarks=m.get("benchmarks", {}),
        created_at=m.get("created_at", ""),
        updated_at=m.get("updated_at", ""),
    )


@router.get("", response_model=List[ModelDefinitionResource], operation_id="models.list")
async def list_models(
    provider: Optional[str] = Query(None, description="Filter by provider ID"),
    capability: Optional[str] = Query(None, description="Filter by capability"),
    modality: Optional[str] = Query(None, description="Filter by modality"),
    is_local: Optional[bool] = Query(None, description="Filter by local/cloud execution"),
    search: Optional[str] = Query(None, description="Search term across name, vendor, description"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[ModelDefinitionResource]:
    """List canonical model definitions matching criteria."""
    results = await service.list(NS_MODELS)

    if provider:
        p_lower = provider.lower()
        results = [
            m for m in results
            if any(b.get("provider_id", "").lower() == p_lower for b in m.get("bindings", [])) or m.get("vendor", "").lower() == p_lower
        ]

    if capability:
        cap_lower = capability.lower()
        results = [m for m in results if any(c.lower() == cap_lower for c in m.get("capabilities", []))]

    if modality:
        mod_lower = modality.lower()
        results = [m for m in results if any(mod_lower in md.lower() for md in m.get("modalities", []))]

    if is_local is not None:
        results = [m for m in results if m.get("is_local") == is_local]

    if search:
        s_lower = search.strip().lower()
        results = [
            m for m in results
            if s_lower in m.get("name", "").lower()
            or s_lower in m["id"].lower()
            or s_lower in m.get("vendor", "").lower()
            or s_lower in m.get("description", "").lower()
        ]

    return [_model_to_resource(m) for m in results]


@router.get("/{model_id:path}", response_model=ModelDefinitionResource, operation_id="models.get")
async def get_model(
    model_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> ModelDefinitionResource:
    """Retrieve details for a specific canonical model by ID."""
    clean_id = model_id.strip()
    model = await service.get(NS_MODELS, clean_id)
    if model is not None:
        return _model_to_resource(model)

    # Try matching without prefix
    models = await service.list(NS_MODELS)
    for m in models:
        if m["id"] == clean_id or m.get("name", "").lower() == clean_id.lower():
            return _model_to_resource(m)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Canonical model '{model_id}' not found in registry.",
    )
