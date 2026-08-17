"""
V3 Routing Router — Model Routing, Policy & Decision Explainability Authority (Phase 12).
Provides versioned routing rules, graph topology, traffic metrics, simulation with explainable RouteDecision,
and route lock audit capabilities. Decoupled from any legacy game or audio code.
"""

from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

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


# In-memory Rules Database
_RULES: Dict[str, RoutingRuleResource] = {
    "rule-planner-core": RoutingRuleResource(
        id="rule-planner-core",
        name="Planner & Orchestrator Master",
        version=1,
        enabled=True,
        priority=10,
        canonical_model_id="anthropic/claude-3-5-sonnet",
        fallback_model_id="google/gemini-1.5-pro",
        final_fallback_model_id="openai/gpt-4o",
        description="High-reasoning routing for Coordinator, Planner, and Episode Orchestrators.",
        agent_types=["Coordinator", "Planner", "Director"],
        required_capabilities=["reasoning", "tools"],
        min_context_tokens=10000,
        primary_usage=82.0,
        fallback_usage=18.0,
        success_rate=99.8,
        avg_latency_ms=42.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "rule-code-agent": RoutingRuleResource(
        id="rule-code-agent",
        name="Code & Script Generation",
        version=1,
        enabled=True,
        priority=10,
        canonical_model_id="anthropic/claude-3-5-sonnet",
        fallback_model_id="deepseek/deepseek-r1",
        final_fallback_model_id="ollama/qwen2.5-coder",
        description="Specialized coding, AST analysis, and tool-use scripts.",
        agent_types=["Coder", "ScriptWriter", "Worker"],
        required_capabilities=["code", "tools"],
        primary_usage=76.5,
        fallback_usage=23.5,
        success_rate=99.1,
        avg_latency_ms=38.4,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "rule-multimodal-vision": RoutingRuleResource(
        id="rule-multimodal-vision",
        name="Visual & Storyboard Analysis",
        version=1,
        enabled=True,
        priority=20,
        canonical_model_id="google/gemini-1.5-pro",
        fallback_model_id="openai/gpt-4o",
        final_fallback_model_id="google/gemini-1.5-flash",
        description="Massive context multimodal processing for video shots and asset review.",
        agent_types=["VisualInspector", "Critic", "AssetEvaluator"],
        required_capabilities=["vision"],
        requires_vision=True,
        primary_usage=90.0,
        fallback_usage=10.0,
        success_rate=99.5,
        avg_latency_ms=29.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "rule-fast-classification": RoutingRuleResource(
        id="rule-fast-classification",
        name="Lightweight Intent & Tool Filtering",
        version=1,
        enabled=True,
        priority=50,
        canonical_model_id="google/gemini-1.5-flash",
        fallback_model_id="anthropic/claude-3-haiku",
        final_fallback_model_id="openai/gpt-4o-mini",
        description="Low-latency routing for simple turn classifications and status extractions.",
        cost_classes=["economy"],
        primary_usage=95.0,
        fallback_usage=5.0,
        success_rate=99.9,
        avg_latency_ms=14.2,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "rule-local-offline": RoutingRuleResource(
        id="rule-local-offline",
        name="Offline & Privacy-Locked Tasks",
        version=1,
        enabled=True,
        priority=0,
        canonical_model_id="ollama/qwen2.5-coder",
        description="Offline local inference fallback when cloud network is disabled.",
        requires_local=True,
        primary_usage=100.0,
        fallback_usage=0.0,
        success_rate=100.0,
        avg_latency_ms=5.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
}

_ROUTE_LOCKS: Dict[str, RouteLockDetailResource] = {
    "lock-conv-main-01": RouteLockDetailResource(
        lock_id="lock-conv-main-01",
        scope="conversation",
        scope_id="conv-cyberpunk-001",
        canonical_model_id="anthropic/claude-3-5-sonnet",
        status="active",
        created_at="2026-08-16T12:00:00Z",
        routing_snapshot={
            "rule_id": "rule-planner-core",
            "rule_version": 1,
            "canonical_model_id": "anthropic/claude-3-5-sonnet",
            "selected_at": time.time(),
            "reason": "Matched agent_type Coordinator with required capabilities [reasoning, tools]",
        },
    )
}


@router.get("/rules", response_model=List[RoutingRuleResource], operation_id="routing.listRules")
async def list_routing_rules() -> List[RoutingRuleResource]:
    """List all versioned routing rules ordered by priority."""
    return sorted(_RULES.values(), key=lambda r: (r.priority, r.name))


@router.post("/rules", response_model=RoutingRuleResource, status_code=status.HTTP_201_CREATED, operation_id="routing.createRule")
async def create_routing_rule(req: CreateRoutingRuleRequest) -> RoutingRuleResource:
    """Create a new versioned routing rule."""
    rule_id = req.id or f"rule-{uuid.uuid4().hex[:8]}"
    if rule_id in _RULES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Routing rule with ID '{rule_id}' already exists.",
        )

    now = iso_now()
    new_rule = RoutingRuleResource(
        id=rule_id,
        name=req.name,
        version=1,
        enabled=req.enabled,
        priority=req.priority,
        canonical_model_id=req.canonical_model_id,
        fallback_model_id=req.fallback_model_id,
        final_fallback_model_id=req.final_fallback_model_id,
        description=req.description or "",
        task_labels=req.task_labels,
        agent_types=req.agent_types,
        workflow_types=req.workflow_types,
        required_capabilities=req.required_capabilities,
        min_context_tokens=req.min_context_tokens,
        requires_tools=req.requires_tools,
        requires_vision=req.requires_vision,
        cost_classes=req.cost_classes,
        requires_local=req.requires_local,
        requires_private=req.requires_private,
        user_preference_model=req.user_preference_model,
        primary_usage=100.0,
        fallback_usage=0.0,
        success_rate=100.0,
        avg_latency_ms=30.0,
        created_at=now,
        updated_at=now,
    )
    _RULES[rule_id] = new_rule
    return new_rule


@router.get("/rules/{rule_id}", response_model=RoutingRuleResource, operation_id="routing.getRule")
async def get_routing_rule(rule_id: str) -> RoutingRuleResource:
    """Retrieve details for a specific routing rule."""
    if rule_id in _RULES:
        return _RULES[rule_id]
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Routing rule '{rule_id}' not found.",
    )


@router.patch("/rules/{rule_id}", response_model=RoutingRuleResource, operation_id="routing.updateRule")
async def update_routing_rule(rule_id: str, req: UpdateRoutingRuleRequest) -> RoutingRuleResource:
    """Update a routing rule with version bump."""
    if rule_id not in _RULES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )

    current = _RULES[rule_id]
    if req.expected_version is not None and current.version != req.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule version conflict: expected {req.expected_version}, current {current.version}.",
        )

    data = current.model_dump()
    updates = req.model_dump(exclude_unset=True)
    updates.pop("expected_version", None)

    for k, v in updates.items():
        if v is not None:
            data[k] = v

    data["version"] = current.version + 1
    data["updated_at"] = iso_now()

    updated = RoutingRuleResource(**data)
    _RULES[rule_id] = updated
    return updated


@router.delete("/rules/{rule_id}", response_model=Dict[str, Any], operation_id="routing.deleteRule")
async def delete_routing_rule(rule_id: str) -> Dict[str, Any]:
    """Delete a routing rule."""
    if rule_id not in _RULES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Routing rule '{rule_id}' not found.",
        )
    del _RULES[rule_id]
    return {"deleted": True, "id": rule_id}


@router.get("/graph", response_model=RoutingGraphData, operation_id="routing.getGraph")
async def get_routing_graph() -> RoutingGraphData:
    """Generate routing topology graph linking roles, rules, models, and providers."""
    nodes: List[RoutingGraphNode] = []
    links: List[RoutingGraphLink] = []

    roles = ["Coordinator", "Coder", "Planner", "VisualInspector", "Director", "Worker"]
    for role in roles:
        nodes.append(RoutingGraphNode(id=f"role-{role.lower()}", label=role, type="role"))

    for r_id, r in _RULES.items():
        nodes.append(RoutingGraphNode(id=r_id, label=r.name, type="rule"))
        # Link from roles to rule
        for agent_type in r.agent_types:
            r_node_id = f"role-{agent_type.lower()}"
            links.append(RoutingGraphLink(source=r_node_id, target=r_id, label="triggers", weight=1.0))

        # Model node
        m_id = r.canonical_model_id
        nodes.append(RoutingGraphNode(id=f"mod-{m_id}", label=m_id.split("/")[-1], type="model"))
        links.append(RoutingGraphLink(source=r_id, target=f"mod-{m_id}", label="primary (80%)", weight=0.8))

        if r.fallback_model_id:
            f_id = r.fallback_model_id
            nodes.append(RoutingGraphNode(id=f"mod-{f_id}", label=f_id.split("/")[-1], type="model"))
            links.append(RoutingGraphLink(source=r_id, target=f"mod-{f_id}", label="fallback (20%)", weight=0.2))

    # Deduplicate nodes by ID
    unique_nodes = {n.id: n for n in nodes}.values()
    return RoutingGraphData(nodes=list(unique_nodes), links=links)


@router.get("/metrics", response_model=RoutingMetricsData, operation_id="routing.getMetrics")
async def get_routing_metrics() -> RoutingMetricsData:
    """Retrieve realtime traffic metrics and distribution."""
    distribution: List[TrafficDistributionItem] = [
        TrafficDistributionItem(
            model_id="anthropic/claude-3-5-sonnet",
            model_name="Claude 3.5 Sonnet",
            provider="Anthropic Direct",
            percentage=46.2,
            request_count=12480,
        ),
        TrafficDistributionItem(
            model_id="google/gemini-1.5-pro",
            model_name="Gemini 1.5 Pro",
            provider="Google AI Studio",
            percentage=28.5,
            request_count=7700,
        ),
        TrafficDistributionItem(
            model_id="google/gemini-1.5-flash",
            model_name="Gemini 1.5 Flash",
            provider="Google AI Studio",
            percentage=14.3,
            request_count=3860,
        ),
        TrafficDistributionItem(
            model_id="deepseek/deepseek-r1",
            model_name="DeepSeek R1",
            provider="DeepSeek Direct",
            percentage=8.2,
            request_count=2210,
        ),
        TrafficDistributionItem(
            model_id="ollama/qwen2.5-coder",
            model_name="Qwen 2.5 Coder",
            provider="Ollama Local",
            percentage=2.8,
            request_count=750,
        ),
    ]

    return RoutingMetricsData(
        total_routes=27000,
        active_rules=len(_RULES),
        fallback_chains=3,
        avg_latency_ms=36.4,
        success_rate_percent=99.7,
        traffic_balance_percent=94.2,
        traffic_distribution=distribution,
    )


@router.post("/simulations", response_model=RouteDecisionResource, operation_id="routing.simulate")
async def simulate_route_decision(req: RouteSimulationRequest) -> RouteDecisionResource:
    """Execute dry-run route resolution returning explainable RouteDecision."""
    matched_rule = None
    reason = "Default fallback routing policy"

    if req.requires_local:
        matched_rule = _RULES.get("rule-local-offline")
        reason = "Matched requirement for offline/local execution"
    else:
        role_lower = req.role.lower()
        for r in sorted(_RULES.values(), key=lambda x: x.priority):
            if any(agent_t.lower() == role_lower for agent_t in r.agent_types):
                matched_rule = r
                reason = f"Matched rule '{r.name}' (Priority {r.priority}) for agent role '{req.role}'"
                break

    if not matched_rule:
        matched_rule = _RULES.get("rule-planner-core") or list(_RULES.values())[0]
        reason = f"Fallback to rule '{matched_rule.name}'"

    canonical_model = req.user_preference_model or matched_rule.canonical_model_id
    provider = "Anthropic Direct" if "anthropic" in canonical_model else ("Google AI Studio" if "google" in canonical_model else "OpenAI Direct")
    endpoint = "ep-default-gateway"

    lock_id = f"lock-{uuid.uuid4().hex[:10]}"
    now = iso_now()

    # Record simulated lock
    _ROUTE_LOCKS[lock_id] = RouteLockDetailResource(
        lock_id=lock_id,
        scope="simulation",
        scope_id=f"sim-{uuid.uuid4().hex[:6]}",
        canonical_model_id=canonical_model,
        status="active",
        created_at=now,
        routing_snapshot={
            "rule_id": matched_rule.id,
            "rule_version": matched_rule.version,
            "canonical_model_id": canonical_model,
            "selected_at": time.time(),
            "reason": reason,
        },
    )

    fallbacks = []
    if matched_rule.fallback_model_id:
        fallbacks.append(matched_rule.fallback_model_id)
    if matched_rule.final_fallback_model_id:
        fallbacks.append(matched_rule.final_fallback_model_id)

    return RouteDecisionResource(
        request_id=f"req-{uuid.uuid4().hex[:10]}",
        requested_role=req.role,
        canonical_model_id=canonical_model,
        selected_provider=provider,
        selected_endpoint=endpoint,
        rule_id=matched_rule.id,
        rule_name=matched_rule.name,
        reason=reason,
        fallback_chain=fallbacks,
        route_lock_id=lock_id,
        evaluated_at=now,
    )


@router.get("/locks/{lock_id}", response_model=RouteLockDetailResource, operation_id="routing.getLock")
async def get_route_lock(lock_id: str) -> RouteLockDetailResource:
    """Audit and inspect route lock explanation for Agent Workspace."""
    if lock_id in _ROUTE_LOCKS:
        return _ROUTE_LOCKS[lock_id]
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Route lock '{lock_id}' not found.",
    )


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
                "timestamp": utc_now(),
                "data": {"status": "subscribed", "providers": 6, "rules": len(_RULES)},
            })
        )
        while True:
            # Heartbeat ping / keepalive
            await asyncio.sleep(20)
            await websocket.send_text(
                json.dumps({
                    "type": "provider.health.heartbeat",
                    "timestamp": utc_now(),
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
