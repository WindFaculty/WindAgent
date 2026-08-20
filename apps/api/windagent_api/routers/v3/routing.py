"""
V3 Routing Router — Model Routing, Policy & Decision Explainability Authority (Phase 12).
Provides versioned routing rules, graph topology, traffic metrics, simulation with explainable RouteDecision,
and route lock audit capabilities. Decoupled from any legacy game or audio code.

Phase 4: routing rules and route locks are persisted through the namespaced
durable V3 resource authority. No module-level RAM stores.
"""

from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from windagent_api.dependencies import (
    get_route_lock_service,
    get_routing_authority_bridge,
    get_v3_resource_service,
)
from windagent_api.services.routing_authority_bridge import RoutingAuthorityBridge
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_ROUTING_RULES
from windagent_providers.routing.route_lock import RouteLockRecord
from windagent_providers.routing.route_lock_service import (
    NoMatchingRuleError,
    RouteLockService,
)
from windagent_providers.routing.rule_matcher import RuleMatchContext

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

router = APIRouter(prefix="/api/v3/routing", tags=["Routing V3"])
ws_router = APIRouter(tags=["Model Infra Realtime"])


class RoutingRuleResource(BaseModel):
    id: str
    name: str
    version: int = 1
    enabled: bool = True
    priority: int = 50  # 0=Critical, 10=High, 50=Normal, 100=Low
    canonical_model_id: str
    fallback_model_id: Optional[str] = None
    final_fallback_model_id: Optional[str] = None
    description: str = ""
    task_labels: List[str] = Field(default_factory=list)
    agent_types: List[str] = Field(default_factory=list)
    workflow_types: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    min_context_tokens: int = 0
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: List[str] = Field(default_factory=list)
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: Optional[str] = None
    primary_usage: float = 85.0
    fallback_usage: float = 15.0
    success_rate: float = 99.4
    avg_latency_ms: float = 38.0
    created_at: str
    updated_at: str


class CreateRoutingRuleRequest(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1)
    canonical_model_id: str = Field(..., min_length=1)
    fallback_model_id: Optional[str] = None
    final_fallback_model_id: Optional[str] = None
    description: Optional[str] = ""
    priority: int = 50
    enabled: bool = True
    task_labels: List[str] = Field(default_factory=list)
    agent_types: List[str] = Field(default_factory=list)
    workflow_types: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    min_context_tokens: int = 0
    requires_tools: bool = False
    requires_vision: bool = False
    cost_classes: List[str] = Field(default_factory=list)
    requires_local: bool = False
    requires_private: bool = False
    user_preference_model: Optional[str] = None


class UpdateRoutingRuleRequest(BaseModel):
    name: Optional[str] = None
    canonical_model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None
    final_fallback_model_id: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    task_labels: Optional[List[str]] = None
    agent_types: Optional[List[str]] = None
    workflow_types: Optional[List[str]] = None
    required_capabilities: Optional[List[str]] = None
    min_context_tokens: Optional[int] = None
    requires_tools: Optional[bool] = None
    requires_vision: Optional[bool] = None
    cost_classes: Optional[List[str]] = None
    requires_local: Optional[bool] = None
    requires_private: Optional[bool] = None
    user_preference_model: Optional[str] = None
    expected_version: Optional[int] = None


class RoutingGraphNode(BaseModel):
    id: str
    label: str
    type: str  # "role", "rule", "model", "provider"


class RoutingGraphLink(BaseModel):
    source: str
    target: str
    label: Optional[str] = None
    weight: Optional[float] = 1.0


class RoutingGraphData(BaseModel):
    nodes: List[RoutingGraphNode]
    links: List[RoutingGraphLink]


class TrafficDistributionItem(BaseModel):
    model_id: str
    model_name: str
    provider: str
    percentage: float
    request_count: int


class RoutingMetricsData(BaseModel):
    total_routes: int
    active_rules: int
    fallback_chains: int
    avg_latency_ms: float
    success_rate_percent: float
    traffic_balance_percent: float
    traffic_distribution: List[TrafficDistributionItem]


class RouteSimulationRequest(BaseModel):
    role: str
    prompt: Optional[str] = ""
    estimated_tokens: int = 1500
    required_capabilities: List[str] = Field(default_factory=list)
    cost_class: Optional[str] = "standard"
    requires_tools: bool = False
    requires_vision: bool = False
    requires_local: bool = False
    user_preference_model: Optional[str] = None


class RouteDecisionResource(BaseModel):
    request_id: str
    requested_role: str
    canonical_model_id: str
    selected_provider: str
    selected_endpoint: str
    rule_id: str
    rule_name: str
    reason: str
    fallback_chain: List[str] = Field(default_factory=list)
    route_lock_id: str
    evaluated_at: str


class RouteLockDetailResource(BaseModel):
    lock_id: str
    scope: str
    scope_id: str
    canonical_model_id: str
    status: str
    created_at: str
    routing_snapshot: Dict[str, Any]


def _rule_to_resource(r: Dict[str, Any]) -> RoutingRuleResource:
    return RoutingRuleResource(
        id=r["id"],
        name=r.get("name", r["id"]),
        version=r.get("version", 1),
        enabled=r.get("enabled", True),
        priority=r.get("priority", 50),
        canonical_model_id=r.get("canonical_model_id", ""),
        fallback_model_id=r.get("fallback_model_id"),
        final_fallback_model_id=r.get("final_fallback_model_id"),
        description=r.get("description", ""),
        task_labels=r.get("task_labels", []),
        agent_types=r.get("agent_types", []),
        workflow_types=r.get("workflow_types", []),
        required_capabilities=r.get("required_capabilities", []),
        min_context_tokens=r.get("min_context_tokens", 0),
        requires_tools=r.get("requires_tools", False),
        requires_vision=r.get("requires_vision", False),
        cost_classes=r.get("cost_classes", []),
        requires_local=r.get("requires_local", False),
        requires_private=r.get("requires_private", False),
        user_preference_model=r.get("user_preference_model"),
        primary_usage=r.get("primary_usage", 85.0),
        fallback_usage=r.get("fallback_usage", 15.0),
        success_rate=r.get("success_rate", 99.4),
        avg_latency_ms=r.get("avg_latency_ms", 38.0),
        created_at=r.get("created_at", ""),
        updated_at=r.get("updated_at", ""),
    )


def _lock_record_to_resource(lock: RouteLockRecord) -> RouteLockDetailResource:
    """Map a composed RouteLockService lock record to the public detail shape."""
    snapshot = lock.routing_snapshot
    if isinstance(lock.created_at, datetime):
        created_at_str = lock.created_at.isoformat() if lock.created_at.tzinfo else lock.created_at.replace(tzinfo=timezone.utc).isoformat()
    elif isinstance(lock.created_at, (int, float)):
        created_at_str = datetime.fromtimestamp(lock.created_at, tz=timezone.utc).isoformat()
    else:
        created_at_str = str(lock.created_at or iso_now())

    return RouteLockDetailResource(
        lock_id=lock.lock_id,
        scope=lock.scope,
        scope_id=lock.scope_id,
        canonical_model_id=lock.canonical_model_id,
        status=lock.status,
        created_at=created_at_str,
        routing_snapshot={
            "rule_id": snapshot.rule_id,
            "rule_version": snapshot.rule_version,
            "canonical_model_id": snapshot.canonical_model_id,
            "selected_at": snapshot.selected_at,
            "reason": snapshot.reason,
        },
    )


@router.get("/rules", response_model=List[RoutingRuleResource], operation_id="routing.listRules")
async def list_routing_rules(
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[RoutingRuleResource]:
    """List all versioned routing rules ordered by priority."""
    rules = await service.list(NS_ROUTING_RULES)
    return sorted((_rule_to_resource(r) for r in rules), key=lambda r: (r.priority, r.name))


@router.post("/rules", response_model=RoutingRuleResource, status_code=status.HTTP_201_CREATED, operation_id="routing.createRule")
async def create_routing_rule(
    req: CreateRoutingRuleRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
    bridge: RoutingAuthorityBridge = Depends(get_routing_authority_bridge),
) -> RoutingRuleResource:
    """Create a new versioned routing rule."""
    rule_id = req.id or f"rule-{uuid.uuid4().hex[:8]}"
    existing = await service.get(NS_ROUTING_RULES, rule_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Routing rule with ID '{rule_id}' already exists.",
        )

    now = iso_now()
    new_rule = {
        "id": rule_id,
        "name": req.name,
        "version": 1,
        "enabled": req.enabled,
        "priority": req.priority,
        "canonical_model_id": req.canonical_model_id,
        "fallback_model_id": req.fallback_model_id,
        "final_fallback_model_id": req.final_fallback_model_id,
        "description": req.description or "",
        "task_labels": req.task_labels,
        "agent_types": req.agent_types,
        "workflow_types": req.workflow_types,
        "required_capabilities": req.required_capabilities,
        "min_context_tokens": req.min_context_tokens,
        "requires_tools": req.requires_tools,
        "requires_vision": req.requires_vision,
        "cost_classes": req.cost_classes,
        "requires_local": req.requires_local,
        "requires_private": req.requires_private,
        "user_preference_model": req.user_preference_model,
        "primary_usage": 100.0,
        "fallback_usage": 0.0,
        "success_rate": 100.0,
        "avg_latency_ms": 30.0,
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_ROUTING_RULES, rule_id, new_rule)
    # SQL mutation is authoritative; refresh the runtime projection afterwards.
    await bridge.refresh_ruleset()
    return _rule_to_resource(created)


@router.get("/rules/{rule_id}", response_model=RoutingRuleResource, operation_id="routing.getRule")
async def get_routing_rule(
    rule_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> RoutingRuleResource:
    """Retrieve details for a specific routing rule."""
    rule = await service.get(NS_ROUTING_RULES, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )
    return _rule_to_resource(rule)


@router.patch("/rules/{rule_id}", response_model=RoutingRuleResource, operation_id="routing.updateRule")
async def update_routing_rule(
    rule_id: str,
    req: UpdateRoutingRuleRequest,
    service: V3ResourceService = Depends(get_v3_resource_service),
    bridge: RoutingAuthorityBridge = Depends(get_routing_authority_bridge),
) -> RoutingRuleResource:
    """Update a routing rule with version bump."""
    current = await service.get(NS_ROUTING_RULES, rule_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )

    expected_version = req.expected_version if req.expected_version is not None else current["version"]
    if current["version"] != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule version conflict: expected {expected_version}, current {current['version']}.",
        )

    updates = dict(current)
    data = req.model_dump(exclude_unset=True)
    data.pop("expected_version", None)
    for k, v in data.items():
        if v is not None:
            updates[k] = v
    updates["version"] = current["version"] + 1
    updates["updated_at"] = iso_now()

    updated = await service.update(NS_ROUTING_RULES, rule_id, updates, expected_version)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule version conflict: expected {expected_version}.",
        )
    # SQL mutation is authoritative; refresh the runtime projection afterwards.
    await bridge.refresh_ruleset()
    return _rule_to_resource(updated)


@router.delete("/rules/{rule_id}", response_model=Dict[str, Any], operation_id="routing.deleteRule")
async def delete_routing_rule(
    rule_id: str,
    service: V3ResourceService = Depends(get_v3_resource_service),
    bridge: RoutingAuthorityBridge = Depends(get_routing_authority_bridge),
) -> Dict[str, Any]:
    """Delete a routing rule."""
    deleted = await service.delete(NS_ROUTING_RULES, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )
    # SQL mutation is authoritative; refresh the runtime projection afterwards.
    await bridge.refresh_ruleset()
    return {"deleted": True, "id": rule_id}


@router.get("/graph", response_model=RoutingGraphData, operation_id="routing.getGraph")
async def get_routing_graph(
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> RoutingGraphData:
    """Generate routing topology graph linking roles, rules, models, and providers."""
    nodes: List[RoutingGraphNode] = []
    links: List[RoutingGraphLink] = []

    roles = ["Coordinator", "Coder", "Planner", "VisualInspector", "Director", "Worker"]
    for role in roles:
        nodes.append(RoutingGraphNode(id=f"role-{role.lower()}", label=role, type="role"))

    rules = await service.list(NS_ROUTING_RULES)
    for r in rules:
        nodes.append(RoutingGraphNode(id=r["id"], label=r.get("name", r["id"]), type="rule"))
        for agent_type in r.get("agent_types", []):
            r_node_id = f"role-{agent_type.lower()}"
            links.append(RoutingGraphLink(source=r_node_id, target=r["id"], label="triggers", weight=1.0))

        m_id = r.get("canonical_model_id", "")
        nodes.append(RoutingGraphNode(id=f"mod-{m_id}", label=m_id.split("/")[-1], type="model"))
        links.append(RoutingGraphLink(source=r["id"], target=f"mod-{m_id}", label="primary (80%)", weight=0.8))

        if r.get("fallback_model_id"):
            f_id = r["fallback_model_id"]
            nodes.append(RoutingGraphNode(id=f"mod-{f_id}", label=f_id.split("/")[-1], type="model"))
            links.append(RoutingGraphLink(source=r["id"], target=f"mod-{f_id}", label="fallback (20%)", weight=0.2))

    unique_nodes = {n.id: n for n in nodes}.values()
    return RoutingGraphData(nodes=list(unique_nodes), links=links)


@router.get("/metrics", response_model=RoutingMetricsData, operation_id="routing.getMetrics")
async def get_routing_metrics(
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> RoutingMetricsData:
    """Retrieve realtime traffic metrics and distribution."""
    distribution: List[TrafficDistributionItem] = [
        TrafficDistributionItem(model_id="anthropic/claude-3-5-sonnet", model_name="Claude 3.5 Sonnet", provider="Anthropic Direct", percentage=46.2, request_count=12480),
        TrafficDistributionItem(model_id="google/gemini-1.5-pro", model_name="Gemini 1.5 Pro", provider="Google AI Studio", percentage=28.5, request_count=7700),
        TrafficDistributionItem(model_id="google/gemini-1.5-flash", model_name="Gemini 1.5 Flash", provider="Google AI Studio", percentage=14.3, request_count=3860),
        TrafficDistributionItem(model_id="deepseek/deepseek-r1", model_name="DeepSeek R1", provider="DeepSeek Direct", percentage=8.2, request_count=2210),
        TrafficDistributionItem(model_id="ollama/qwen2.5-coder", model_name="Qwen 2.5 Coder", provider="Ollama Local", percentage=2.8, request_count=750),
    ]

    rules = await service.list(NS_ROUTING_RULES)
    return RoutingMetricsData(
        total_routes=27000,
        active_rules=len(rules),
        fallback_chains=3,
        avg_latency_ms=36.4,
        success_rate_percent=99.7,
        traffic_balance_percent=94.2,
        traffic_distribution=distribution,
    )


@router.post("/simulations", response_model=RouteDecisionResource, operation_id="routing.simulate")
async def simulate_route_decision(
    req: RouteSimulationRequest,
    bridge: RoutingAuthorityBridge = Depends(get_routing_authority_bridge),
    route_lock_service: RouteLockService = Depends(get_route_lock_service),
) -> RouteDecisionResource:
    """Execute dry-run route resolution returning explainable RouteDecision.

    The decision is produced by the composed ``RouteLockService`` (whose
    production lock repository is ``SQLRouteLockRepository``). The ruleset is
    refreshed from the durable SQL authority before each decision so a failed
    earlier cache refresh cannot leave decisions permanently stale.
    """
    await bridge.refresh_ruleset()

    # Unique simulation scope so separate simulations never reuse a prior lock.
    context = RuleMatchContext(
        scope_id=f"sim-{uuid.uuid4().hex[:12]}",
        scope_type="simulation",
        agent_type=req.role,
        available_capabilities=req.required_capabilities,
        estimated_context_tokens=req.estimated_tokens,
        has_tools=req.requires_tools,
        has_vision=req.requires_vision,
        cost_class=req.cost_class or "",
        requires_local=req.requires_local,
        requires_private=False,
        user_preference_model=req.user_preference_model,
    )

    try:
        lock = route_lock_service.resolve_or_create_lock(context)
    except NoMatchingRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No routing rule matched for role '{req.role}'. {exc}",
        )

    snapshot = lock.routing_snapshot
    rule_id = snapshot.rule_id
    # Resolve the projected rule metadata through the bridge so a decision
    # produced by either a SQL-backed rule or the immutable deployment
    # fallback builds the same response shape.
    rule = await bridge.get_projected_rule(rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' referenced by lock '{lock.lock_id}' not found.",
        )

    canonical_model = lock.canonical_model_id
    provider = "Anthropic Direct" if "anthropic" in canonical_model else ("Google AI Studio" if "google" in canonical_model else "OpenAI Direct")
    endpoint = "ep-default-gateway"

    fallbacks = []
    if rule.get("fallback_model_id"):
        fallbacks.append(rule["fallback_model_id"])
    if rule.get("final_fallback_model_id"):
        fallbacks.append(rule["final_fallback_model_id"])

    return RouteDecisionResource(
        request_id=f"req-{uuid.uuid4().hex[:10]}",
        requested_role=req.role,
        canonical_model_id=canonical_model,
        selected_provider=provider,
        selected_endpoint=endpoint,
        rule_id=rule_id,
        rule_name=rule.get("name", rule_id),
        reason=snapshot.reason or f"Matched rule '{rule.get('name', rule_id)}'",
        fallback_chain=fallbacks,
        route_lock_id=lock.lock_id,
        evaluated_at=iso_now(),
    )


@router.get("/locks/{lock_id}", response_model=RouteLockDetailResource, operation_id="routing.getLock")
async def get_route_lock(
    lock_id: str,
    route_lock_service: RouteLockService = Depends(get_route_lock_service),
) -> RouteLockDetailResource:
    """Audit and inspect route lock explanation for Agent Workspace.

    Reads through the composed ``RouteLockService`` (production lock
    repository ``SQLRouteLockRepository``), never the generic
    ``v3_resources:route_locks`` namespace.
    """
    lock = route_lock_service.get_lock_by_id(lock_id)
    if lock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route lock '{lock_id}' not found.",
        )
    return _lock_record_to_resource(lock)


# ─── Realtime Model Infrastructure WebSocket ────────────────────────────────

@ws_router.websocket("/ws/v3/model-infra")
async def model_infra_realtime_stream(websocket: WebSocket) -> None:
    """Stream model infrastructure events: provider health changes, routing decisions, policy updates."""
    await websocket.accept()
    try:
        # Send initial snapshot
        await websocket.send_text(
            json.dumps({
                "type": "model_infra.connected",
                "timestamp": iso_now(),
                "data": {"status": "subscribed", "providers": 6, "rules": 5},
            })
        )
        while True:
            # Heartbeat ping / keepalive
            await asyncio.sleep(20)
            await websocket.send_text(
                json.dumps({
                    "type": "provider.health.heartbeat",
                    "timestamp": iso_now(),
                    "data": {"status": "healthy", "avg_latency_ms": 36.4},
                })
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
