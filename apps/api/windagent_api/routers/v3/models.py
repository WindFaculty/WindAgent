"""
V3 Models Router — Canonical Model Infrastructure Authority (Phase 12 / P0.2).
Serves the DURABLE discovered-model registry (provider sync authority) merged
with the demo catalog under the explicit demo profile. Supports server-side
FREE/PAID/UNKNOWN pricing classification — never guessed, only what providers
advertise.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_api.dependencies import (
    get_provider_management_service,
    get_v3_resource_service,
)
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_MODELS
from windagent_providers.management import ProviderManagementService

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
    availability: str = "active"
    pricing_class: str = "UNKNOWN"
    input_price: Optional[float] = None
    output_price: Optional[float] = None
    currency: Optional[str] = None
    last_discovered_at: Optional[str] = None


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
    pricing_class: str = "UNKNOWN"
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
        pricing_class=m.get("pricing_class", "UNKNOWN"),
        pricing=ModelPricing(**pricing) if pricing else None,
        bindings=[ModelEndpointBinding(**b) for b in m.get("bindings", [])],
        benchmarks=m.get("benchmarks", {}),
        created_at=m.get("created_at", ""),
        updated_at=m.get("updated_at", ""),
    )


def _merged_catalog(
    durable: List[Dict[str, Any]], demo: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Durable discovered registry wins on id collision; demo fills the rest."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for m in demo:
        by_id[m["id"]] = m
    for m in durable:
        by_id[m["id"]] = m
    return list(by_id.values())


@router.get("", response_model=List[ModelDefinitionResource], operation_id="models.list")
async def list_models(
    provider: Optional[str] = Query(None, description="Filter by provider ID"),
    capability: Optional[str] = Query(None, description="Filter by capability"),
    modality: Optional[str] = Query(None, description="Filter by modality"),
    is_local: Optional[bool] = Query(None, description="Filter by local/cloud execution"),
    pricing: Optional[str] = Query(None, description="Filter by pricing class: FREE | PAID | UNKNOWN"),
    search: Optional[str] = Query(None, description="Search term across name, vendor, description"),
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> List[ModelDefinitionResource]:
    """List canonical model definitions matching criteria.

    P0.2.2/P0.2.3: the primary source is the durable discovered registry fed
    by provider Sync Models; the demo catalog only appears under the explicit
    demo profile. ``pricing`` filters strictly by the advertised class.
    """
    pricing_filter = pricing.strip().upper() if pricing else None
    if pricing_filter not in (None, "FREE", "PAID", "UNKNOWN"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pricing must be one of: FREE, PAID, UNKNOWN.",
        )

    results = _merged_catalog(
        management.list_all_discovered_models(),
        await service.list(NS_MODELS) if os.getenv("WINDAGENT_PROFILE", "").strip().lower() == "demo" else [],
    )

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

    if pricing_filter:
        results = [m for m in results if m.get("pricing_class", "UNKNOWN") == pricing_filter]

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
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> ModelDefinitionResource:
    """Retrieve details for a specific canonical model by ID."""
    clean_id = model_id.strip()

    for model in management.list_all_discovered_models():
        if model["id"] == clean_id or model.get("name", "").lower() == clean_id.lower():
            return _model_to_resource(model)

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
