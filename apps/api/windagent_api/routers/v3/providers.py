"""
V3 Providers Router — Physical Provider & Endpoint Registry Authority (Phase 12 / Phase 10).
Provides provider registries, physical endpoint health, connection testing, and secure credential status.
Raw API keys are NEVER exposed to the frontend.

Phase 4: provider catalog reads are DERIVED from the durable namespaced V3
resource authority (seeded in non-production). No module-level RAM stores.

Phase 10: a durable ``POST /api/v3/providers`` registers a provider into the
dedicated provider SQL authority (vendor + optional credential + endpoint) with
the raw credential encrypted at rest. ``test-connection`` performs a REAL
adapter network call + model discovery for providers registered in the
dedicated SQL authority; demo-only providers (seeded in non-production) fall
back to the demo catalog so legacy contract tests remain green. A durable
per-role model-rule assignment endpoint is provided.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from windagent_api.dependencies import (
    get_provider_management_service,
    get_provider_probe_service,
    get_v3_resource_service,
)
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_PROVIDERS
from windagent_core.contracts.studio.story_roles import normalize_story_role
from windagent_providers.management import (
    ModelProbeReceipt,
    ModelSyncResult,
    ProviderAlreadyExistsError,
    ProviderInUseError,
    ProviderManagementService,
    ProviderNotFoundError,
    ProviderProbeService,
    ProviderVendorNotFoundError,
)

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

router = APIRouter(prefix="/api/v3/providers", tags=["Providers V3"])


class ProviderEndpointResource(BaseModel):
    id: str
    provider_id: str
    name: str
    base_url: str
    status: str = "healthy"  # "healthy", "degraded", "offline", "unconfigured"
    latency_ms: float = 35.0
    rate_limit_rpm: int = 600
    rate_limit_tpm: int = 200000
    credential_reference: str = ""
    is_configured: bool = True
    credential_label: Optional[str] = None
    credential_updated_at: Optional[str] = None
    models_count: int = 2
    last_checked_at: str


class ProviderResource(BaseModel):
    id: str
    display_name: str
    type: str  # "anthropic", "openai", "google", "deepseek", "mistral", "ollama", "openrouter", "custom"
    status: str = "healthy"
    enabled: bool = True
    capabilities: List[str] = Field(default_factory=list)
    website_url: Optional[str] = None
    endpoints: List[ProviderEndpointResource] = Field(default_factory=list)
    models_count: int = 0
    has_credentials: bool = True
    created_at: str
    updated_at: str


class AddProviderRequest(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    type: str = "custom"  # cloud | local | custom
    base_url: str = Field(..., min_length=1)
    protocol_mode: str = "openai"  # openai | anthropic | gemini | ollama
    api_key: Optional[str] = None
    credential_label: Optional[str] = None
    endpoint_id: Optional[str] = None
    supports_model_discovery: bool = True
    supports_openai_compatible: bool = True


class TestConnectionRequest(BaseModel):
    endpoint_id: Optional[str] = None


class ProviderConnectionTestResult(BaseModel):
    test_id: str
    provider_id: str
    endpoint_id: str
    reachable: bool
    latency_ms: float
    auth_valid: bool
    model_discovery: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    message: str
    completed_at: str


class AssignModelRuleRequest(BaseModel):
    role: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    primary_canonical_model_id: str = Field(..., min_length=1)
    fallback_canonical_model_id: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 1


class ModelRuleResource(BaseModel):
    role: str
    name: str
    description: Optional[str] = None
    primary_canonical_model_id: str
    fallback_canonical_model_id: Optional[str] = None
    enabled: bool
    priority: int
    created_at: str
    updated_at: str


class UpdateProviderRequest(BaseModel):
    """Partial provider edit. Secrets are NEVER editable through this route."""

    name: Optional[str] = Field(default=None, min_length=1)
    base_url: Optional[str] = Field(default=None, min_length=1)
    protocol_mode: Optional[str] = Field(default=None, pattern="^(openai|anthropic|gemini|ollama)$")
    enabled: Optional[bool] = None
    supports_model_discovery: Optional[bool] = None
    supports_openai_compatible: Optional[bool] = None


class CredentialPutRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    label: Optional[str] = None


class CredentialStatusResource(BaseModel):
    """Credential state WITHOUT any secret material."""

    provider_id: str
    configured: bool
    credential_reference: str = ""
    label: Optional[str] = None
    secret_version: int = 0
    updated_at: str = ""


class DeleteProviderResult(BaseModel):
    provider_id: str
    deleted: bool
    removed_endpoints: int = 0
    removed_credentials: int = 0
    removed_bindings: int = 0
    disabled_rule_roles: List[str] = Field(default_factory=list)


class SyncModelsRequest(BaseModel):
    endpoint_id: Optional[str] = None


class SyncModelsResult(BaseModel):
    """P0.2.1/P0.2.4 — explicit Sync Models operation receipt."""

    provider_id: str
    endpoint_id: str
    ok: bool
    added: List[str] = Field(default_factory=list)
    updated: List[str] = Field(default_factory=list)
    unchanged: List[str] = Field(default_factory=list)
    unavailable: List[str] = Field(default_factory=list)
    discovered_count: int = 0
    error_code: Optional[str] = None
    message: str
    completed_at: str


class TestModelRequest(BaseModel):
    """Canonical model id to verify with one tiny real inference."""

    model_id: str = Field(..., min_length=1)


class ModelProbeReceiptResource(BaseModel):
    provider_id: str
    endpoint_id: str
    canonical_model_id: str
    provider_model_id: str
    ok: bool
    latency_ms: float
    finish_reason: Optional[str] = None
    error_code: Optional[str] = None
    message: str
    completed_at: str


def _provider_to_resource(p: Dict[str, Any]) -> ProviderResource:
    return ProviderResource(
        id=p["id"],
        display_name=p.get("display_name", p["id"]),
        type=p.get("type", "custom"),
        status=p.get("status", "healthy"),
        enabled=p.get("enabled", True),
        capabilities=p.get("capabilities", []),
        website_url=p.get("website_url"),
        endpoints=[ProviderEndpointResource(**ep) for ep in p.get("endpoints", [])],
        models_count=p.get("models_count", 0),
        has_credentials=p.get("has_credentials", True),
        created_at=p.get("created_at", ""),
        updated_at=p.get("updated_at", ""),
    )


@router.get("", response_model=List[ProviderResource], operation_id="providers.list")
async def list_providers(
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> List[ProviderResource]:
    """Retrieve all configured AI model providers with physical endpoints.

    Durable providers registered via ``POST /api/v3/providers`` are merged with
    the demo catalog (non-production) so both authorities surface.
    """
    durable = management.list_providers()
    demo = await service.list(NS_PROVIDERS)
    by_id: Dict[str, Dict[str, Any]] = {}
    for p in demo:
        by_id[p["id"]] = p
    for p in durable:
        by_id[p["id"]] = p  # durable authority wins on id collision
    return [_provider_to_resource(p) for p in by_id.values()]


@router.post("", response_model=ProviderResource, status_code=status.HTTP_201_CREATED, operation_id="providers.create")
async def create_provider(
    req: AddProviderRequest,
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> ProviderResource:
    """Durably register a provider (vendor + optional credential + endpoint).

    The raw ``api_key`` is encrypted at rest and never returned. The provider
    is stored in the dedicated provider SQL authority.
    """
    try:
        provider = management.add_provider(
            vendor_id=req.id,
            name=req.name,
            vendor_type=req.type,
            base_url=req.base_url,
            protocol_mode=req.protocol_mode,
            credential_secret=req.api_key,
            credential_label=req.credential_label,
            endpoint_id=req.endpoint_id,
            supports_model_discovery=req.supports_model_discovery,
            supports_openai_compatible=req.supports_openai_compatible,
        )
    except ProviderAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Provider '{exc.vendor_id}' already exists.",
        )
    return _provider_to_resource(provider)


@router.patch("/{provider_id}", response_model=ProviderResource, operation_id="providers.update")
async def update_provider(
    provider_id: str,
    req: UpdateProviderRequest,
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> ProviderResource:
    """Edit provider display name, endpoint configuration and enabled state.

    Catalog-only (demo) providers cannot be edited — register a durable
    provider first. The API key is never part of an update payload; rotate it
    through ``PUT /{provider_id}/credential`` instead.
    """
    clean_id = provider_id.strip().lower()
    try:
        provider = management.update_provider(
            clean_id,
            name=req.name,
            base_url=req.base_url,
            protocol_mode=req.protocol_mode,
            enabled=req.enabled,
            supports_model_discovery=req.supports_model_discovery,
            supports_openai_compatible=req.supports_openai_compatible,
            actor="api",
        )
    except ProviderVendorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider '{provider_id}' is not registered in the durable "
                "provider authority."
            ),
        ) from exc
    return _provider_to_resource(provider)


@router.delete("/{provider_id}", response_model=DeleteProviderResult, operation_id="providers.delete")
async def delete_provider(
    provider_id: str,
    allow_disabling_rules: bool = False,
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> DeleteProviderResult:
    """Delete a durable provider (vendor + endpoints + credentials + bindings).

    Fails with 409 while any ENABLED routing rule still references one of the
    provider's bound canonical models. Pass ``allow_disabling_rules=true`` to
    explicitly disable those conflicting rules first — never a silent cascade.
    """
    clean_id = provider_id.strip().lower()
    try:
        result = management.delete_provider(
            clean_id,
            allow_disabling_rules=allow_disabling_rules,
            actor="api",
        )
    except ProviderVendorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider '{provider_id}' is not registered in the durable "
                "provider authority."
            ),
        ) from exc
    except ProviderInUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "blocking_rules": exc.blocking_rules,
                "resolution": (
                    "Delete or re-point these routing rules first, or retry "
                    "with allow_disabling_rules=true to disable them explicitly."
                ),
            },
        ) from exc
    return DeleteProviderResult(**result)


@router.put("/{provider_id}/credential", response_model=CredentialStatusResource, operation_id="providers.rotateCredential")
async def rotate_provider_credential(
    provider_id: str,
    req: CredentialPutRequest,
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> CredentialStatusResource:
    """Rotate (or first-configure) the provider credential.

    The raw key is encrypted at rest and never returned, logged, or audited.
    """
    clean_id = provider_id.strip().lower()
    try:
        result = management.rotate_credential(
            clean_id, req.api_key, req.label, actor="api"
        )
    except ProviderVendorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        ) from exc
    return CredentialStatusResource(**result)


@router.delete("/{provider_id}/credential", response_model=CredentialStatusResource, operation_id="providers.removeCredential")
async def remove_provider_credential(
    provider_id: str,
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> CredentialStatusResource:
    """Remove the provider credential. Endpoints become unconfigured."""
    clean_id = provider_id.strip().lower()
    try:
        result = management.remove_credential(clean_id, actor="api")
    except ProviderVendorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        ) from exc
    return CredentialStatusResource(**result)


@router.get("/health", response_model=Dict[str, Any], operation_id="providers.health")
async def get_all_providers_health(
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> Dict[str, Any]:
    """Retrieve operational health map for all providers and endpoints."""
    providers = management.list_providers()
    if os.getenv("WINDAGENT_PROFILE", "").strip().lower() == "demo":
        demo_by_id = {p["id"]: p for p in await service.list(NS_PROVIDERS)}
        demo_by_id.update({p["id"]: p for p in providers})
        providers = list(demo_by_id.values())
    health_map: Dict[str, Any] = {}
    for p in providers:
        endpoints = p.get("endpoints", [])
        healthy_endpoints = sum(1 for ep in endpoints if ep.get("status") == "healthy")
        avg_lat = sum(ep.get("latency_ms", 0) for ep in endpoints) / max(1, len(endpoints))
        health_map[p["id"]] = {
            "status": p.get("status", "healthy"),
            "avg_latency_ms": round(avg_lat, 1),
            "endpoints_healthy": healthy_endpoints,
            "endpoints_total": len(endpoints),
        }
    return health_map


@router.post("/rules", response_model=ModelRuleResource, status_code=status.HTTP_201_CREATED, operation_id="providers.assignRule")
async def assign_model_rule(
    req: AssignModelRuleRequest,
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> ModelRuleResource:
    """Durably assign one independent ModelRule per role/model mapping.

    The rule is persisted in the dedicated ``model_routing_rules_v3`` authority
    and is loaded by the Worker at bootstrap (authoritative when no env override
    is supplied).
    """
    try:
        rule = management.upsert_model_rule(
            role=normalize_story_role(req.role),
            name=req.name,
            primary_canonical_model_id=req.primary_canonical_model_id,
            fallback_canonical_model_id=req.fallback_canonical_model_id,
            description=req.description,
            enabled=req.enabled,
            priority=req.priority,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return ModelRuleResource(**rule)


@router.get("/rules", response_model=List[ModelRuleResource], operation_id="providers.listRules")
async def list_model_rules(
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> List[ModelRuleResource]:
    """List enabled durable per-role model rules."""
    return [ModelRuleResource(**r) for r in management.list_enabled_model_rules()]


@router.get("/{provider_id}", response_model=ProviderResource, operation_id="providers.get")
async def get_provider(
    provider_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> ProviderResource:
    """Retrieve details for a specific provider by ID."""
    clean_id = provider_id.strip().lower()
    durable = management.get_provider(clean_id)
    if durable is not None:
        return _provider_to_resource(durable)
    provider = await service.get(NS_PROVIDERS, clean_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        )
    return _provider_to_resource(provider)


@router.get("/{provider_id}/models", response_model=List[Dict[str, Any]], operation_id="providers.getModels")
async def get_provider_models(
    provider_id: str,
    pricing: Optional[str] = Query(None, description="Filter by pricing class: FREE | PAID | UNKNOWN"),
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> List[Dict[str, Any]]:
    """Retrieve models registered and available on this provider.

    P0.2.3 — server-side FREE/PAID/UNKNOWN filter over the durable registry.
    """
    from windagent_api.services.v3_demo_seed import NS_MODELS

    clean_id = provider_id.strip().lower()
    pricing_filter = pricing.strip().upper() if pricing else None
    if pricing_filter not in (None, "FREE", "PAID", "UNKNOWN"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pricing must be one of: FREE, PAID, UNKNOWN.",
        )
    durable = management.get_provider(clean_id)
    if durable is not None:
        models = management.list_discovered_models(clean_id)
        if pricing_filter:
            models = [m for m in models if m.get("pricing_class") == pricing_filter]
        return models
    provider = await service.get(NS_PROVIDERS, clean_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        )

    models = await service.list(NS_MODELS)
    matched = []
    for m in models:
        if any(b.get("provider_id", "").lower() == clean_id for b in m.get("bindings", [])) or m.get("vendor", "").lower() == clean_id:
            matched.append(m)
    return matched


@router.get("/{provider_id}/endpoints", response_model=List[ProviderEndpointResource], operation_id="providers.getEndpoints")
async def get_provider_endpoints(
    provider_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> List[ProviderEndpointResource]:
    """Retrieve physical network endpoints for this provider."""
    clean_id = provider_id.strip().lower()
    durable = management.get_provider(clean_id)
    if durable is not None:
        return [ProviderEndpointResource(**ep) for ep in durable.get("endpoints", [])]
    provider = await service.get(NS_PROVIDERS, clean_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        )
    return [ProviderEndpointResource(**ep) for ep in provider.get("endpoints", [])]


@router.get("/{provider_id}/health", response_model=str, operation_id="providers.getProviderHealth")
async def get_provider_health(
    provider_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
) -> str:
    """Retrieve operational health status string for a provider."""
    clean_id = provider_id.strip().lower()
    durable = management.get_provider(clean_id)
    if durable is not None:
        return durable.get("status", "healthy")
    provider = await service.get(NS_PROVIDERS, clean_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        )
    return provider.get("status", "healthy")


def _resolve_durable_endpoint(
    management: ProviderManagementService,
    provider_id: str,
    requested_endpoint_id: Optional[str],
) -> Dict[str, Any]:
    """Resolve the target endpoint of a DURABLE provider (404 otherwise)."""
    durable = management.get_provider(provider_id)
    if durable is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider '{provider_id}' is not registered in the durable "
                "provider authority."
            ),
        )
    endpoints = durable.get("endpoints", [])
    target_endpoint = endpoints[0] if endpoints else None
    if requested_endpoint_id:
        target_endpoint = None
        for ep in endpoints:
            if ep.get("id") == requested_endpoint_id:
                target_endpoint = ep
                break
        if target_endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint '{requested_endpoint_id}' not found.",
            )
    if target_endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' has no endpoint to operate on.",
        )
    return target_endpoint


@router.post("/{provider_id}/test-connection", response_model=ProviderConnectionTestResult, operation_id="providers.testConnection")
async def test_provider_connection(
    provider_id: str,
    req: Optional[TestConnectionRequest] = None,
    service: V3ResourceService = Depends(get_v3_resource_service),
    management: ProviderManagementService = Depends(get_provider_management_service),
    probe: ProviderProbeService = Depends(get_provider_probe_service),
) -> ProviderConnectionTestResult:
    """Perform a REAL server-side connection handshake (connectivity/auth).

    P0.2.1: this operation NO LONGER discovers models — catalog refresh is the
    explicit ``POST /{provider_id}/sync-models`` operation. Demo-only providers
    (seeded in non-production) fall back to the demo catalog so legacy contract
    tests remain green.
    """
    clean_id = provider_id.strip().lower()
    if management.get_provider(clean_id) is not None:
        target_endpoint = _resolve_durable_endpoint(
            management, clean_id, req.endpoint_id if req else None
        )
        try:
            result = await probe.test_connection(target_endpoint["id"])
        except ProviderNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint '{exc.endpoint_id}' not found.",
            )
        return ProviderConnectionTestResult(
            test_id=f"test-{uuid.uuid4().hex[:10]}",
            provider_id=clean_id,
            endpoint_id=result.endpoint_id,
            reachable=result.reachable,
            latency_ms=round(result.latency_ms, 1),
            auth_valid=result.auth_valid,
            model_discovery=[],
            error_code=result.error_code,
            message=result.message,
            completed_at=result.completed_at.isoformat(),
        )

    # The legacy always-success receipt is isolated to the explicit demo
    # profile. Default/development/production fail closed instead of turning a
    # read-only catalog row into connection authority.
    if os.getenv("WINDAGENT_PROFILE", "").strip().lower() != "demo":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Provider '{provider_id}' is catalog-only. Register a durable "
                "endpoint before testing its connection."
            ),
        )

    # Explicit demo-profile compatibility for legacy sample-data contracts.
    provider = await service.get(NS_PROVIDERS, clean_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_id}' not found.",
        )

    endpoints = provider.get("endpoints", [])
    target_endpoint = endpoints[0] if endpoints else None
    if req and req.endpoint_id:
        for ep in endpoints:
            if ep.get("id") == req.endpoint_id:
                target_endpoint = ep
                break

    ep_id = target_endpoint.get("id", "ep-default") if target_endpoint else "ep-default"
    latency = target_endpoint.get("latency_ms", 32.5) if target_endpoint else 32.5

    discovered_map = {
        "google": ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest", "gemini-2.0-flash-exp"],
        "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
        "openai": ["gpt-4o", "gpt-4o-mini", "o1-mini", "text-embedding-3-small"],
        "deepseek": ["deepseek-chat", "deepseek-reasoner"],
        "openrouter": ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "deepseek/deepseek-r1"],
        "ollama": ["qwen2.5-coder:latest", "llama3.1:8b"],
    }

    return ProviderConnectionTestResult(
        test_id=f"test-{uuid.uuid4().hex[:10]}",
        provider_id=clean_id,
        endpoint_id=ep_id,
        reachable=True,
        latency_ms=latency,
        auth_valid=True,
        model_discovery=discovered_map.get(clean_id, ["default-model-v1"]),
        message=f"Successfully authenticated and reachable via endpoint '{ep_id}' ({latency}ms).",
        completed_at=iso_now(),
    )


@router.post("/{provider_id}/sync-models", response_model=SyncModelsResult, operation_id="providers.syncModels")
async def sync_provider_models(
    provider_id: str,
    req: Optional[SyncModelsRequest] = None,
    management: ProviderManagementService = Depends(get_provider_management_service),
    probe: ProviderProbeService = Depends(get_provider_probe_service),
) -> SyncModelsResult:
    """Explicitly discover + durably reconcile this provider's model catalog.

    P0.2.1/P0.2.4: independent from Test Connection. One pass classifies every
    binding as ADDED / UPDATED / UNCHANGED / UNAVAILABLE — nothing is deleted
    just because one discovery pass missed it.
    """
    clean_id = provider_id.strip().lower()
    target_endpoint = _resolve_durable_endpoint(
        management, clean_id, req.endpoint_id if req else None
    )
    try:
        result: ModelSyncResult = await probe.sync_models(target_endpoint["id"])
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint '{exc.endpoint_id}' not found.",
        )
    return SyncModelsResult(
        provider_id=clean_id,
        endpoint_id=result.endpoint_id,
        ok=result.ok,
        added=result.added,
        updated=result.updated,
        unchanged=result.unchanged,
        unavailable=result.unavailable,
        discovered_count=len(result.discovered),
        error_code=result.error_code,
        message=result.message,
        completed_at=result.completed_at.isoformat(),
    )


@router.post("/{provider_id}/models/test", response_model=ModelProbeReceiptResource, operation_id="providers.testModel")
async def test_provider_model(
    provider_id: str,
    req: TestModelRequest,
    management: ProviderManagementService = Depends(get_provider_management_service),
    probe: ProviderProbeService = Depends(get_provider_probe_service),
) -> ModelProbeReceiptResource:
    """P0.2.5 — verify one bound model with a tiny REAL inference.

    Verifies endpoint, credential, model id, protocol, and response path.
    Never used for quality benchmarking; returns no quality metrics.
    """
    clean_id = provider_id.strip().lower()
    target_endpoint = _resolve_durable_endpoint(management, clean_id, None)
    try:
        receipt: ModelProbeReceipt = await probe.probe_model(
            target_endpoint["id"], req.model_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint '{exc.endpoint_id}' not found.",
        )
    return ModelProbeReceiptResource(
        provider_id=clean_id,
        endpoint_id=receipt.endpoint_id,
        canonical_model_id=receipt.canonical_model_id,
        provider_model_id=receipt.provider_model_id,
        ok=receipt.ok,
        latency_ms=receipt.latency_ms,
        finish_reason=receipt.finish_reason,
        error_code=receipt.error_code,
        message=receipt.message,
        completed_at=receipt.completed_at.isoformat(),
    )
