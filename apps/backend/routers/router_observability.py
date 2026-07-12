"""Phase 6 — Router runtime observability endpoints.

Exposes:
  GET /router/runtime/summary     — aggregate stats across all agents/providers
  GET /router/runtime/executions  — last N execution log entries
  GET /router/runtime/providers/health — per-provider health status
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from db.models import (
    ModelCatalogORM,
    ModelProviderORM,
    ModelRuntimeStatusORM,
    RouterExecutionLogORM,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/router/runtime", tags=["router-observability"])


# ---------------------------------------------------------------------------
# Summary endpoint
# ---------------------------------------------------------------------------


@router.get("/summary")
async def get_runtime_summary(request: Request) -> Dict[str, Any]:
    """Aggregate runtime statistics — request counts, latency, error rate, quota.

    Returns an empty-safe response even when the database is empty.
    Never exposes secrets or API keys.
    """
    db = request.app.state.db
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)

    async with db.session() as session:
        # Fetch all execution logs from last 24h
        stmt = select(RouterExecutionLogORM).where(
            RouterExecutionLogORM.created_at >= one_day_ago
        )
        res = await session.execute(stmt)
        logs = res.scalars().all()

        # Counts by agent role
        request_count_by_agent: Dict[str, int] = {}
        request_count_by_model: Dict[str, int] = {}
        total_latency_ms = 0
        error_count = 0
        fallback_count = 0

        for entry in logs:
            request_count_by_agent[entry.role] = (
                request_count_by_agent.get(entry.role, 0) + 1
            )
            request_count_by_model[entry.selected_model_id] = (
                request_count_by_model.get(entry.selected_model_id, 0) + 1
            )
            total_latency_ms += entry.latency_ms
            if entry.status != "success":
                error_count += 1
            if entry.selection_tier in ("fallback", "final_fallback", "emergency"):
                fallback_count += 1

        total = len(logs)
        avg_latency_ms = total_latency_ms / total if total > 0 else 0.0
        error_rate = error_count / total if total > 0 else 0.0

        # Quota usage — delegate to quota service if available
        quota_usage: Dict[str, Any] = {}
        try:
            quota_svc = getattr(request.app.state, "quota_service", None)
            if quota_svc is None:
                model_svc = getattr(request.app.state, "model_service", None)
                quota_svc = getattr(model_svc, "quota_service", None)
            if quota_svc is not None:
                for provider_id in ("openai", "anthropic", "google_ai_studio", "openrouter"):
                    snap = await quota_svc.get_latest_quota(provider_id)
                    if snap:
                        quota_usage[provider_id] = {
                            "remaining_requests_today": snap.remaining_requests_today,
                            "remaining_tokens_today": snap.remaining_tokens_today,
                            # Do NOT expose API keys or raw credentials
                        }
        except Exception:
            log.warning("Could not fetch quota snapshots for summary", exc_info=True)

        # Last 10 executions (abbreviated)
        last_logs = sorted(logs, key=lambda l: l.created_at, reverse=True)[:10]
        last_executions = [
            {
                "id": l.id,
                "role": l.role,
                "model": l.selected_model_id,
                "tier": l.selection_tier,
                "status": l.status,
                "latency_ms": l.latency_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in last_logs
        ]

        return {
            "request_count_by_agent": request_count_by_agent,
            "request_count_by_model": request_count_by_model,
            "avg_latency_ms": round(avg_latency_ms, 2),
            "error_rate": round(error_rate, 4),
            "fallback_count": fallback_count,
            "quota_usage": quota_usage,
            "last_executions": last_executions,
            "degraded_providers": [],  # Populated when provider health monitoring is wired up
            "total_requests_24h": total,
        }


# ---------------------------------------------------------------------------
# Executions endpoint
# ---------------------------------------------------------------------------


@router.get("/executions")
async def get_executions(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Return the last N router execution log entries.

    Safe for display — secrets are never stored in execution logs.
    """
    db = request.app.state.db

    async with db.session() as session:
        stmt = (
            select(RouterExecutionLogORM)
            .order_by(RouterExecutionLogORM.created_at.desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        entries = res.scalars().all()

        return [
            {
                "id": e.id,
                "role": e.role,
                "selected_model_id": e.selected_model_id,
                "selection_tier": e.selection_tier,
                "status": e.status,
                "latency_ms": e.latency_ms,
                "prompt_tokens": e.prompt_tokens,
                "completion_tokens": e.completion_tokens,
                "estimated_cost": e.estimated_cost,
                "error_message": e.error_message,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]


# ---------------------------------------------------------------------------
# Provider health endpoint
# ---------------------------------------------------------------------------


@router.get("/providers/health")
async def get_providers_health(request: Request) -> List[Dict[str, Any]]:
    """Return per-provider health status derived from runtime status table.

    Falls back to empty list if no runtime data is available.
    Never exposes API keys.
    """
    db = request.app.state.db

    async with db.session() as session:
        stmt = (
            select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
            .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
            .outerjoin(
                ModelRuntimeStatusORM,
                ModelCatalogORM.id == ModelRuntimeStatusORM.model_id,
            )
        )
        res = await session.execute(stmt)
        rows = res.all()

        # Aggregate by provider
        provider_status: Dict[str, Dict[str, Any]] = {}
        for catalog, provider, runtime in rows:
            pid = provider.id
            if pid not in provider_status:
                provider_status[pid] = {
                    "provider_id": pid,
                    "provider_name": provider.display_name if hasattr(provider, "display_name") else pid,
                    "status": "Unknown",
                    "latency_p50_ms": None,
                    "healthy_models": 0,
                    "total_models": 0,
                }
            provider_status[pid]["total_models"] += 1
            if runtime:
                if runtime.status == "Online" or runtime.health == "Healthy":
                    provider_status[pid]["healthy_models"] += 1
                    provider_status[pid]["status"] = "Healthy"
                elif runtime.status == "Offline" or runtime.health == "Unhealthy":
                    provider_status[pid]["status"] = "Unhealthy"
                if runtime.latency_p50_ms:
                    existing = provider_status[pid]["latency_p50_ms"]
                    if existing is None:
                        provider_status[pid]["latency_p50_ms"] = runtime.latency_p50_ms
                    else:
                        provider_status[pid]["latency_p50_ms"] = (
                            existing + runtime.latency_p50_ms
                        ) / 2

        return list(provider_status.values())
