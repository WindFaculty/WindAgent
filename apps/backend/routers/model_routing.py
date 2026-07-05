"""FastAPI Router for OmniRoute-inspired model routing administration and simulation."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, Body, HTTPException, Query
from pydantic import BaseModel

from schemas.router import (
    RoutingRuleCreate,
    RoutingRulePatch,
    RoutingRuleDTO,
    RoutingStatsDTO,
    TrafficDistributionDTO,
    RoutingGraphDTO,
    RouteSimulationRequest,
    RouteSimulationResponse,
    RouteTestRequest,
    RouteTestResponse,
)
from services.router_execution_service import RouterExecutionService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/models/routing", tags=["routing"])


def _service(request: Request) -> RouterExecutionService:
    return request.app.state.router_service


@router.get("/rules", response_model=List[RoutingRuleDTO])
async def list_rules(request: Request) -> List[Dict[str, Any]]:
    """List all routing rules with 24h usage/performance statistics."""
    service = _service(request)
    return await service.list_routing_rules()


@router.post("/rules", status_code=201)
async def create_rule(request: Request, config: RoutingRuleCreate) -> Dict[str, Any]:
    """Create a new model routing rule."""
    service = _service(request)
    try:
        return await service.create_routing_rule(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/rules/{role}")
async def update_rule(request: Request, role: str, config: RoutingRulePatch) -> Dict[str, Any]:
    """Update an existing model routing rule."""
    service = _service(request)
    try:
        return await service.update_routing_rule(role, config)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/rules/{role}")
async def delete_rule(request: Request, role: str) -> Dict[str, Any]:
    """Delete a model routing rule."""
    service = _service(request)
    return await service.delete_routing_rule(role)


class ImportRulesPayload(BaseModel):
    rules: List[Dict[str, Any]]


@router.post("/import")
async def import_rules(request: Request, payload: ImportRulesPayload) -> Dict[str, Any]:
    """Bulk import a list of routing rules, handling partial failures gracefully."""
    service = _service(request)
    return await service.import_routing_rules(payload.rules)


@router.get("/stats", response_model=RoutingStatsDTO)
async def get_stats(request: Request) -> Dict[str, Any]:
    """Get aggregated router statistics for the top dashboard cards."""
    service = _service(request)
    return await service.get_routing_stats()


@router.get("/traffic", response_model=TrafficDistributionDTO)
async def get_traffic(request: Request, timeframe: int = Query(24, description="Timeframe in hours")) -> Dict[str, Any]:
    """Get request counts and percentages per model for the donut chart."""
    service = _service(request)
    return await service.get_traffic_distribution(timeframe)


@router.get("/graph", response_model=RoutingGraphDTO)
async def get_graph(request: Request) -> Dict[str, Any]:
    """Get nodes and links connecting roles/triggers to active models for the graph visualizer."""
    service = _service(request)
    return await service.get_routing_graph()


@router.post("/simulate", response_model=RouteSimulationResponse)
async def simulate_route(request: Request, config: RouteSimulationRequest) -> Dict[str, Any]:
    """Run an in-memory route selection simulation based on prompt characteristics."""
    service = _service(request)
    return await service.simulate_route(config.role, config.prompt)


@router.post("/rules/{role}/test", response_model=RouteTestResponse)
async def test_route(request: Request, role: str, payload: Optional[RouteTestRequest] = None) -> Dict[str, Any]:
    """Perform a live probe test on a specific route, logging the execution results."""
    service = _service(request)
    prompt = payload.prompt if payload else "hello"
    try:
        return await service.test_route(role, prompt)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
