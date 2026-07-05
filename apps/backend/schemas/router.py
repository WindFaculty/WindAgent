"""Schemas for Model Router rules, logs, stats, graph, and simulation."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class RoutingRuleCreate(BaseModel):
    role: str = Field(..., max_length=64)
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    primary_model_id: Optional[str] = Field(None, max_length=128)
    fallback_model_id: Optional[str] = Field(None, max_length=128)
    final_fallback_model_id: Optional[str] = Field(None, max_length=128)
    status: Literal["Active", "Weighted", "Fallback", "Disabled"] = "Active"
    tags: List[str] = []
    policy: Dict[str, Any] = {}


class RoutingRulePatch(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    primary_model_id: Optional[str] = Field(None, max_length=128)
    fallback_model_id: Optional[str] = Field(None, max_length=128)
    final_fallback_model_id: Optional[str] = Field(None, max_length=128)
    status: Optional[Literal["Active", "Weighted", "Fallback", "Disabled"]] = None
    tags: Optional[List[str]] = None
    policy: Optional[Dict[str, Any]] = None


class HealthMetricItem(BaseModel):
    name: str
    latency: str
    status: Literal["Good", "Warning"]


class RoutingRuleDTO(BaseModel):
    id: str  # role
    name: str
    trigger: str  # role
    primary: str  # display name
    fallback: str  # display name
    status: str
    success: str
    sparkPoints: str
    description: str
    routeId: str
    tags: List[str]
    primaryUsage: int
    fallbackUsage: int
    successRate: int
    avgLatency: str
    primaryModel: str
    secondaryModel: str
    finalFallbackModel: str
    health: List[HealthMetricItem]
    activity: List[str]


class StatValueDTO(BaseModel):
    value: Any
    trend: float
    trendDir: Literal["up", "down", "stable"]


class RoutingStatsDTO(BaseModel):
    totalRoutes: StatValueDTO
    activeRules: StatValueDTO
    fallbackChains: StatValueDTO
    avgLatency: StatValueDTO
    successRate: StatValueDTO
    trafficBalance: StatValueDTO


class TrafficItemDTO(BaseModel):
    modelId: str
    name: str
    count: int
    percentage: int


class TrafficDistributionDTO(BaseModel):
    totalRequests: int
    distribution: List[TrafficItemDTO]


class GraphLinkDTO(BaseModel):
    source: str
    target: str
    type: Literal["primary", "fallback", "final_fallback"]


class RoutingGraphDTO(BaseModel):
    roles: List[str]
    models: List[str]
    links: List[GraphLinkDTO]


class RouteSimulationRequest(BaseModel):
    prompt: str
    role: str


class RouteSimulationResponse(BaseModel):
    decision: str
    selectedModel: str
    fallbackNeeded: bool
    confidence: float
    estimatedCost: float
    etaSeconds: float
    flowSteps: List[str]


class RouteTestRequest(BaseModel):
    prompt: Optional[str] = "hello"


class RouteTestResponse(BaseModel):
    success: bool
    selectedModel: Optional[str]
    tier: Optional[str]
    latencyMs: int
    error: Optional[str] = None


class RouterExecutionLogDTO(BaseModel):
    id: int
    role: str
    selected_model_id: str
    selection_tier: str
    status: str
    latency_ms: int
    error_message: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float
    created_at: datetime
