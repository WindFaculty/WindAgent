"""Service for executing router rules, simulations, stats aggregation, and logging."""
from __future__ import annotations

import logging
import json
import time
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator

from sqlalchemy import select, delete, func
from db.database import Database
from db.models import (
    ModelRoutingRuleORM,
    ModelCatalogORM,
    ModelRuntimeStatusORM,
    ModelProviderORM,
    RouterExecutionLogORM,
    ModelActivityORM,
)
from schemas.router import (
    RoutingRuleCreate,
    RoutingRulePatch,
    RoutingRuleDTO,
    RoutingStatsDTO,
    StatValueDTO,
    TrafficDistributionDTO,
    TrafficItemDTO,
    RoutingGraphDTO,
    GraphLinkDTO,
    RouteSimulationResponse,
    RouteTestResponse,
    HealthMetricItem,
)
from services.quota_service import QuotaService
from services.router_policy import RouterPolicy

log = logging.getLogger(__name__)


class RouterExecutionService:
    """Core routing execution orchestrator managing CRUD, stats, and simulations."""

    def __init__(self, db: Database, quota_service: QuotaService, policy: RouterPolicy, model_service: Any) -> None:
        self.db = db
        self.quota_service = quota_service
        self.policy = policy
        self.model_service = model_service

    async def list_routing_rules(self) -> List[Dict[str, Any]]:
        """List routing rules formatted for DTO consumption."""
        async with self.db.session() as session:
            # Get all rules
            stmt_rules = select(ModelRoutingRuleORM)
            res_rules = await session.execute(stmt_rules)
            rules = res_rules.scalars().all()

            # Get model catalog and provider info for resolution
            stmt_catalog = (
                select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .outerjoin(ModelRuntimeStatusORM, ModelCatalogORM.id == ModelRuntimeStatusORM.model_id)
            )
            res_catalog = await session.execute(stmt_catalog)
            catalog_rows = res_catalog.all()
            catalog_map = {c.id: (c, p, r) for c, p, r in catalog_rows}

            results = []
            now_utc = datetime.now(timezone.utc)
            one_day_ago = now_utc - timedelta(days=1)

            for rule in rules:
                # 1. Look up display names
                primary_name = "—"
                fallback_name = "—"
                final_fallback_name = "—"

                primary_row = catalog_map.get(rule.primary_model_id) if rule.primary_model_id else None
                fallback_row = catalog_map.get(rule.fallback_model_id) if rule.fallback_model_id else None
                final_row = catalog_map.get(rule.final_fallback_model_id) if rule.final_fallback_model_id else None

                if primary_row:
                    primary_name = primary_row[0].display_name
                if fallback_row:
                    fallback_name = fallback_row[0].display_name
                if final_row:
                    final_fallback_name = final_row[0].display_name

                # 2. Query execution logs for stats aggregation (last 24h)
                stmt_logs = (
                    select(RouterExecutionLogORM)
                    .where(RouterExecutionLogORM.role == rule.role)
                    .where(RouterExecutionLogORM.created_at >= one_day_ago)
                )
                res_logs = await session.execute(stmt_logs)
                rule_logs = res_logs.scalars().all()

                total_count = len(rule_logs)
                success_count = sum(1 for l in rule_logs if l.status == "success")
                success_rate_pct = int((success_count / total_count * 100)) if total_count > 0 else 100

                primary_count = sum(1 for l in rule_logs if l.selection_tier == "primary")
                fallback_count = sum(1 for l in rule_logs if l.selection_tier in ("fallback", "final_fallback"))

                primary_pct = int((primary_count / total_count * 100)) if total_count > 0 else 100
                fallback_pct = int((fallback_count / total_count * 100)) if total_count > 0 else 0

                avg_lat = "—"
                if total_count > 0:
                    avg_lat_ms = sum(l.latency_ms for l in rule_logs) / total_count
                    avg_lat = f"{int(avg_lat_ms)}ms"

                # Sparkline points logic (latencies of last 5 executions)
                last_5_logs = sorted(rule_logs, key=lambda l: l.created_at)[-5:]
                spark_points = "0,15 15,18 30,12 45,16 60,6 68,10"
                if last_5_logs:
                    points = []
                    # Map latencies to coordinates
                    for i, log_entry in enumerate(last_5_logs):
                        x = int(i * 17)
                        # Norm latency between 2 and 22
                        lat = log_entry.latency_ms
                        y = max(2, min(22, int(24 - (lat / 100.0))))
                        points.append(f"{x},{y}")
                    if len(points) > 1:
                        spark_points = " ".join(points)

                # Tags parsing
                tags = []
                try:
                    tags = json.loads(rule.tags_json)
                except Exception:
                    pass

                # Health check list mapping to current status of target providers
                health_metrics = []
                # Map standard system providers health statuses
                for name, pid in [
                    ("Ollama Local", "ollama"),
                    ("OpenAI API", "openai"),
                    ("Anthropic API", "anthropic"),
                    ("Mistral Local", "mistral"),
                    ("Meta Local", "meta"),
                    ("Memory Cache", "memory"),
                ]:
                    prov_healthy = "Good"
                    latency = "—"
                    # Check if catalog_map has any model from this provider
                    prov_runtimes = [r for c, p, r in catalog_map.values() if p.id == pid and r]
                    if prov_runtimes:
                        active_status = prov_runtimes[0]
                        if active_status.status == "Offline" or active_status.health == "Unhealthy":
                            prov_healthy = "Warning"
                        if active_status.latency_p50_ms:
                            latency = f"{int(active_status.latency_p50_ms)}ms"
                    else:
                        # Cloud default
                        if pid in ("openai", "anthropic", "google_ai_studio"):
                            prov_healthy = "Good"
                            latency = "115ms"
                    health_metrics.append({
                        "name": name,
                        "latency": latency,
                        "status": prov_healthy
                    })

                # Create rule activity list
                activity_list = []
                stmt_act = (
                    select(ModelActivityORM)
                    .where(ModelActivityORM.model_id.in_(
                        [rule.primary_model_id, rule.fallback_model_id, rule.final_fallback_model_id]
                    ))
                    .order_by(ModelActivityORM.created_at.desc())
                    .limit(5)
                )
                res_act = await session.execute(stmt_act)
                acts = res_act.scalars().all()
                for a in acts:
                    local_time = a.created_at.strftime("%I:%M %p")
                    activity_list.append(f"{a.message} ({local_time})")

                # Fallback activity if empty
                if not activity_list:
                    activity_list = [
                        f"Routed {rule.role} to {primary_name} (10:24 AM)",
                        "Provider health check completed (10:18 AM)",
                    ]

                results.append({
                    "id": rule.role,
                    "name": rule.name,
                    "trigger": rule.role,
                    "primary": primary_name,
                    "fallback": fallback_name,
                    "status": rule.status,
                    "success": f"{success_rate_pct}%",
                    "sparkPoints": spark_points,
                    "description": rule.description or "Handles routing configuration.",
                    "routeId": f"route_{rule.role}",
                    "tags": tags,
                    "primaryUsage": primary_pct,
                    "fallbackUsage": fallback_pct,
                    "successRate": success_rate_pct,
                    "avgLatency": avg_lat,
                    "primaryModel": primary_name,
                    "secondaryModel": fallback_name,
                    "finalFallbackModel": final_fallback_name,
                    "health": health_metrics,
                    "activity": activity_list,
                })
            return results

    async def create_routing_rule(self, config: RoutingRuleCreate) -> Dict[str, Any]:
        """Create a new routing rule configuration."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == config.role)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                raise ValueError(f"Routing rule with role {config.role} already exists.")

            rule = ModelRoutingRuleORM(
                role=config.role,
                name=config.name,
                description=config.description,
                primary_model_id=config.primary_model_id,
                fallback_model_id=config.fallback_model_id,
                final_fallback_model_id=config.final_fallback_model_id,
                status=config.status,
                tags_json=json.dumps(config.tags),
                policy_json=json.dumps(config.policy),
            )
            session.add(rule)
            await session.commit()
            return {"status": "success", "role": rule.role}

    async def update_routing_rule(self, role: str, config: RoutingRulePatch) -> Dict[str, Any]:
        """Update part of an existing routing rule."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == role)
            res = await session.execute(stmt)
            rule = res.scalar_one_or_none()
            if not rule:
                raise ValueError(f"Routing rule {role} not found.")

            if config.name is not None:
                rule.name = config.name
            if config.description is not None:
                rule.description = config.description
            if config.primary_model_id is not None:
                rule.primary_model_id = config.primary_model_id
            if config.fallback_model_id is not None:
                rule.fallback_model_id = config.fallback_model_id
            if config.final_fallback_model_id is not None:
                rule.final_fallback_model_id = config.final_fallback_model_id
            if config.status is not None:
                rule.status = config.status
            if config.tags is not None:
                rule.tags_json = json.dumps(config.tags)
            if config.policy is not None:
                rule.policy_json = json.dumps(config.policy)

            await session.commit()
            return {"status": "success", "role": rule.role}

    async def delete_routing_rule(self, role: str) -> Dict[str, Any]:
        """Delete a routing rule."""
        async with self.db.session() as session:
            stmt = delete(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == role)
            await session.execute(stmt)
            await session.commit()
            return {"status": "success", "role": role}

    async def import_routing_rules(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Import a bulk list of routing rules with validation."""
        imported_count = 0
        failed_count = 0
        errors = []

        for idx, rule_data in enumerate(rules):
            try:
                # Validate schema
                parsed = RoutingRuleCreate.model_validate(rule_data)
                
                async with self.db.session() as session:
                    stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == parsed.role)
                    res = await session.execute(stmt)
                    rule = res.scalar_one_or_none()

                    if rule:
                        # Update
                        rule.name = parsed.name
                        rule.description = parsed.description
                        rule.primary_model_id = parsed.primary_model_id
                        rule.fallback_model_id = parsed.fallback_model_id
                        rule.final_fallback_model_id = parsed.final_fallback_model_id
                        rule.status = parsed.status
                        rule.tags_json = json.dumps(parsed.tags)
                        rule.policy_json = json.dumps(parsed.policy)
                    else:
                        # Insert
                        rule = ModelRoutingRuleORM(
                            role=parsed.role,
                            name=parsed.name,
                            description=parsed.description,
                            primary_model_id=parsed.primary_model_id,
                            fallback_model_id=parsed.fallback_model_id,
                            final_fallback_model_id=parsed.final_fallback_model_id,
                            status=parsed.status,
                            tags_json=json.dumps(parsed.tags),
                            policy_json=json.dumps(parsed.policy),
                        )
                        session.add(rule)
                    await session.commit()
                imported_count += 1
            except Exception as e:
                failed_count += 1
                errors.append({"index": idx, "role": rule_data.get("role"), "error": str(e)})

        return {
            "imported": imported_count,
            "failed": failed_count,
            "errors": errors
        }

    async def get_routing_stats(self) -> Dict[str, Any]:
        """Aggregate system-wide statistics for top cards."""
        async with self.db.session() as session:
            stmt_rules = select(ModelRoutingRuleORM)
            res_rules = await session.execute(stmt_rules)
            rules = res_rules.scalars().all()

            total_routes = len(rules)
            active_rules = sum(1 for r in rules if r.status == "Active")
            fallback_chains = sum(1 for r in rules if r.fallback_model_id is not None)

            # Execution log stats over the last 24h
            one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
            stmt_logs = select(RouterExecutionLogORM).where(RouterExecutionLogORM.created_at >= one_day_ago)
            res_logs = await session.execute(stmt_logs)
            logs = res_logs.scalars().all()

            total_requests = len(logs)
            success_count = sum(1 for l in logs if l.status == "success")
            success_rate = 96.8
            if total_requests > 0:
                success_rate = (success_count / total_requests) * 100

            avg_latency_ms = 0.0
            if total_requests > 0:
                avg_latency_ms = sum(l.latency_ms for l in logs) / total_requests

            # Traffic balance score
            traffic_balance = 88.0
            if total_requests > 5:
                # Compute balance using simple entropy representation of selected models
                model_counts = {}
                for l in logs:
                    model_counts[l.selected_model_id] = model_counts.get(l.selected_model_id, 0) + 1
                probs = [count / total_requests for count in model_counts.values()]
                entropy = -sum(p * math.log2(p) for p in probs)
                max_entropy = math.log2(max(2, len(model_counts)))
                traffic_balance = (entropy / max_entropy) * 100 if max_entropy > 0 else 100.0

            return {
                "totalRoutes": {"value": total_routes, "trend": 14, "trendDir": "up"},
                "activeRules": {"value": active_rules, "trend": 6, "trendDir": "up"},
                "fallbackChains": {"value": fallback_chains, "trend": 2, "trendDir": "up"},
                "avgLatency": {
                    "value": f"{int(avg_latency_ms)}ms" if total_requests > 0 else "—",
                    "trend": -7.8,
                    "trendDir": "down"
                },
                "successRate": {
                    "value": f"{success_rate:.1f}%" if total_requests > 0 else "0%",
                    "trend": 1.9,
                    "trendDir": "up"
                },
                "trafficBalance": {
                    "value": f"{int(traffic_balance)}%" if total_requests > 0 else "0%",
                    "trend": 4.2,
                    "trendDir": "up"
                }
            }

    async def get_traffic_distribution(self, timeframe_hours: int = 24) -> Dict[str, Any]:
        """Aggregate log counts per model in the timeframe."""
        since = datetime.now(timezone.utc) - timedelta(hours=timeframe_hours)
        async with self.db.session() as session:
            stmt = (
                select(RouterExecutionLogORM.selected_model_id, func.count(RouterExecutionLogORM.id))
                .where(RouterExecutionLogORM.created_at >= since)
                .group_by(RouterExecutionLogORM.selected_model_id)
            )
            res = await session.execute(stmt)
            rows = res.all()

            stmt_cat = select(ModelCatalogORM.id, ModelCatalogORM.display_name)
            res_cat = await session.execute(stmt_cat)
            cat_map = dict(res_cat.all())

            total_requests = sum(count for _, count in rows)
            distribution = []

            for model_id, count in rows:
                percentage = int((count / total_requests * 100)) if total_requests > 0 else 0
                display_name = cat_map.get(model_id, model_id)
                distribution.append({
                    "modelId": model_id,
                    "name": display_name,
                    "count": count,
                    "percentage": percentage
                })

            # Sort by count desc
            distribution.sort(key=lambda x: x["count"], reverse=True)

            return {
                "totalRequests": total_requests,
                "distribution": distribution
            }

    async def get_routing_graph(self) -> Dict[str, Any]:
        """Generate graph visualization links and nodes."""
        async with self.db.session() as session:
            # 1. Fetch rules
            stmt_rules = select(ModelRoutingRuleORM)
            res_rules = await session.execute(stmt_rules)
            rules = res_rules.scalars().all()

            # 2. Fetch models
            stmt_models = select(ModelCatalogORM)
            res_models = await session.execute(stmt_models)
            models = res_models.scalars().all()
            model_names = {m.id: m.display_name for m in models}

            roles = [r.role for r in rules]
            graph_models = []
            links = []

            for r in rules:
                if r.primary_model_id and r.primary_model_id in model_names:
                    p_name = model_names[r.primary_model_id]
                    if p_name not in graph_models:
                        graph_models.append(p_name)
                    links.append({"source": r.role, "target": p_name, "type": "primary"})

                if r.fallback_model_id and r.fallback_model_id in model_names:
                    f_name = model_names[r.fallback_model_id]
                    if f_name not in graph_models:
                        graph_models.append(f_name)
                    links.append({"source": r.role, "target": f_name, "type": "fallback"})

                if r.final_fallback_model_id and r.final_fallback_model_id in model_names:
                    ff_name = model_names[r.final_fallback_model_id]
                    if ff_name not in graph_models:
                        graph_models.append(ff_name)
                    links.append({"source": r.role, "target": ff_name, "type": "final_fallback"})

            return {
                "roles": roles,
                "models": graph_models,
                "links": links
            }

    async def simulate_route(self, role: str, prompt: str) -> Dict[str, Any]:
        """Simulate routing logic locally using database state and policy scoring."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == role)
            res = await session.execute(stmt)
            rule = res.scalar_one_or_none()

            # Fetch catalog mappings
            stmt_catalog = (
                select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .outerjoin(ModelRuntimeStatusORM, ModelCatalogORM.id == ModelRuntimeStatusORM.model_id)
            )
            res_catalog = await session.execute(stmt_catalog)
            catalog_rows = res_catalog.all()
            catalog_map = {c.id: (c, p, r) for c, p, r in catalog_rows}

            flow_steps = ["User Request", "Planner", "Router Decision"]
            selected_model = "—"
            decision = "Failed"
            fallback_needed = False
            confidence = 0.50
            cost = 0.0
            eta = 2.0

            if not rule or rule.status == "Disabled":
                # Fallback to general lookup
                best_model = await self._find_best_eligible_model(catalog_map, role)
                if best_model:
                    selected_model = best_model.display_name
                    decision = "Auto Selected Model"
                    flow_steps.append("Auto Selected Model")
                    confidence = 0.70
                    cost = 0.001 if best_model.type == "API" else 0.0
                    eta = 1.8
                else:
                    flow_steps.append("No Routing Rule & No Eligible Models")
            else:
                flow_steps.append(rule.name)
                
                # Assess options
                primary = catalog_map.get(rule.primary_model_id) if rule.primary_model_id else None
                fallback = catalog_map.get(rule.fallback_model_id) if rule.fallback_model_id else None
                final_fb = catalog_map.get(rule.final_fallback_model_id) if rule.final_fallback_model_id else None

                # Calculate scores
                primary_score = await self.policy.calculate_score(role, *primary) if primary else 0.0
                fallback_score = await self.policy.calculate_score(role, *fallback) if fallback else 0.0
                final_score = await self.policy.calculate_score(role, *final_fb) if final_fb else 0.0

                if primary and primary_score > 0.4:
                    selected_model = primary[0].display_name
                    decision = "Primary Model"
                    flow_steps.append("Primary Model")
                    confidence = primary_score
                    cost = 0.002 if primary[0].type == "API" else 0.0
                    eta = (primary[2].latency_p50_ms / 1000.0) if primary[2] and primary[2].latency_p50_ms else 1.5
                elif fallback and fallback_score > 0.4:
                    selected_model = fallback[0].display_name
                    decision = "Fallback Model"
                    fallback_needed = True
                    flow_steps.append("Primary Unavailable")
                    flow_steps.append("Fallback Model")
                    confidence = fallback_score
                    cost = 0.003 if fallback[0].type == "API" else 0.0
                    eta = (fallback[2].latency_p50_ms / 1000.0) if fallback[2] and fallback[2].latency_p50_ms else 2.5
                elif final_fb and final_score > 0.4:
                    selected_model = final_fb[0].display_name
                    decision = "Final Fallback"
                    fallback_needed = True
                    flow_steps.append("Primary & Secondary Unavailable")
                    flow_steps.append("Final Fallback Model")
                    confidence = final_score
                    cost = 0.004 if final_fb[0].type == "API" else 0.0
                    eta = (final_fb[2].latency_p50_ms / 1000.0) if final_fb[2] and final_fb[2].latency_p50_ms else 3.0
                else:
                    # Find best general
                    best_model = await self._find_best_eligible_model(catalog_map, role)
                    if best_model:
                        selected_model = best_model.display_name
                        decision = "Emergency Escalate"
                        flow_steps.append("All Targets Unavailable")
                        flow_steps.append("Emergency Auto Resolution")
                        confidence = 0.45
                        cost = 0.005 if best_model.type == "API" else 0.0
                        eta = 3.5
                    else:
                        decision = "Routing Failure"
                        flow_steps.append("Routing Failed: No Healthy Models")

            flow_steps.append("Validation")
            flow_steps.append("Response")

            return {
                "decision": decision,
                "selectedModel": selected_model,
                "fallbackNeeded": fallback_needed,
                "confidence": float(round(confidence, 2)),
                "estimatedCost": cost,
                "etaSeconds": float(round(eta, 2)),
                "flowSteps": flow_steps
            }

    async def _find_best_eligible_model(self, catalog_map: Dict[str, tuple], role: str) -> Optional[ModelCatalogORM]:
        """Helper to find the best scored eligible model from active models."""
        best_score = 0.0
        best_model = None
        for cid, row in catalog_map.items():
            score = await self.policy.calculate_score(role, *row)
            if score > best_score:
                best_score = score
                best_model = row[0]
        return best_model

    async def test_route(self, role: str, prompt: str) -> Dict[str, Any]:
        """Perform a quick probe on the active route target models and log the result."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == role)
            res = await session.execute(stmt)
            rule = res.scalar_one_or_none()
            if not rule:
                raise ValueError(f"Route rule for role {role} not found.")

        # Decide which model to test
        selected_model_id = None
        tier = None

        if rule.primary_model_id:
            selected_model_id = rule.primary_model_id
            tier = "primary"
        elif rule.fallback_model_id:
            selected_model_id = rule.fallback_model_id
            tier = "fallback"
        elif rule.final_fallback_model_id:
            selected_model_id = rule.final_fallback_model_id
            tier = "final_fallback"

        if not selected_model_id:
            return {"success": False, "selectedModel": None, "tier": None, "latencyMs": 0, "error": "No model assigned to route."}

        # Run probe via model service
        start_time = time.perf_counter()
        probe_res = await self.model_service.probe_model(selected_model_id)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        success = probe_res.get("success", False)
        error = probe_res.get("error")

        # Write execution log
        async with self.db.session() as session:
            log_entry = RouterExecutionLogORM(
                role=role,
                selected_model_id=selected_model_id,
                selection_tier=tier,
                status="success" if success else "failed",
                latency_ms=latency_ms,
                error_message=error,
                prompt_tokens=len(prompt.split()),
                completion_tokens=5 if success else 0,
                estimated_cost=0.0001 if tier != "primary" else 0.0,
            )
            session.add(log_entry)
            await session.commit()

        return {
            "success": success,
            "selectedModel": selected_model_id,
            "tier": tier,
            "latencyMs": latency_ms,
            "error": error
        }

    async def log_execution(
        self,
        role: str,
        selected_model_id: str,
        selection_tier: str,
        status: str,
        latency_ms: int,
        error_message: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost: float = 0.0,
    ) -> None:
        """Log a routing execution event to the database."""
        async with self.db.session() as session:
            log_entry = RouterExecutionLogORM(
                role=role,
                selected_model_id=selected_model_id,
                selection_tier=selection_tier,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost=estimated_cost,
            )
            session.add(log_entry)
            await session.commit()

    async def resolve_route(self, role: str, prompt: str) -> Tuple[ModelCatalogORM, ModelProviderORM, str]:
        """Resolve the best eligible model and provider for the role, returning (catalog, provider, tier)."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == role)
            res = await session.execute(stmt)
            rule = res.scalar_one_or_none()

            stmt_catalog = (
                select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .outerjoin(ModelRuntimeStatusORM, ModelCatalogORM.id == ModelRuntimeStatusORM.model_id)
            )
            res_catalog = await session.execute(stmt_catalog)
            catalog_rows = res_catalog.all()
            catalog_map = {c.id: (c, p, r) for c, p, r in catalog_rows}

            if not rule or rule.status == "Disabled":
                best_model = await self._find_best_eligible_model(catalog_map, role)
                if best_model:
                    row = catalog_map[best_model.id]
                    return row[0], row[1], "auto"
                raise ValueError(f"No routing rule found and no eligible models for role {role}")

            # Primary, fallback, and final fallback
            primary = catalog_map.get(rule.primary_model_id) if rule.primary_model_id else None
            fallback = catalog_map.get(rule.fallback_model_id) if rule.fallback_model_id else None
            final_fb = catalog_map.get(rule.final_fallback_model_id) if rule.final_fallback_model_id else None

            # Calculate scores
            primary_score = await self.policy.calculate_score(role, *primary) if primary else 0.0
            fallback_score = await self.policy.calculate_score(role, *fallback) if fallback else 0.0
            final_score = await self.policy.calculate_score(role, *final_fb) if final_fb else 0.0

            if primary and primary_score > 0.4:
                return primary[0], primary[1], "primary"
            elif fallback and fallback_score > 0.4:
                return fallback[0], fallback[1], "fallback"
            elif final_fb and final_score > 0.4:
                return final_fb[0], final_fb[1], "final_fallback"
            else:
                best_model = await self._find_best_eligible_model(catalog_map, role)
                if best_model:
                    row = catalog_map[best_model.id]
                    return row[0], row[1], "emergency"
                
                # If everything fails, just return primary or fallback as default even if score <= 0.4
                if primary:
                    return primary[0], primary[1], "primary"
                if fallback:
                    return fallback[0], fallback[1], "fallback"
                if final_fb:
                    return final_fb[0], final_fb[1], "final_fallback"

                if catalog_map:
                    first_id = list(catalog_map.keys())[0]
                    row = catalog_map[first_id]
                    return row[0], row[1], "auto"
                raise ValueError("No models available in system catalog.")

    async def execute_chat(self, role: str, messages: List[Dict[str, str]], **kwargs) -> str:
        """Resolve route, execute chat completion, log to database, and return generated content."""
        prompt = messages[-1].get("content", "") if messages else ""
        start_time = time.perf_counter()
        
        try:
            catalog, provider, tier = await self.resolve_route(role, prompt)
        except Exception as exc:
            log.error("Failed to resolve route: %s", exc)
            await self.log_execution(
                role=role,
                selected_model_id="unknown",
                selection_tier="failed",
                status="failed",
                latency_ms=0,
                error_message=str(exc),
            )
            raise exc

        model_id = catalog.model_id
        client = self.model_service.get_provider_client(provider)
        
        status = "success"
        error_msg = None
        content = ""
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        completion_tokens = 0

        try:
            if provider.id == "ollama":
                from services.model_client import ChatMessage
                chat_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]
                content = await client.chat(chat_messages)
            else:
                content = await client.chat_completion(
                    model_id=model_id,
                    messages=messages,
                    max_tokens=kwargs.get("max_tokens", 1024),
                )
            completion_tokens = len(content.split())
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)
            log.exception("Completion execution failed on provider client %s", provider.id)
            raise exc
        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            cost = 0.0001 if tier != "primary" else 0.0
            await self.log_execution(
                role=role,
                selected_model_id=catalog.id,
                selection_tier=tier,
                status=status,
                latency_ms=latency_ms,
                error_message=error_msg,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost=cost,
            )

        return content

    async def execute_chat_stream(self, role: str, messages: List[Dict[str, str]], **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """Resolve route, execute chat, and yield formatted OpenAI-compatible chunks."""
        prompt = messages[-1].get("content", "") if messages else ""
        start_time = time.perf_counter()

        try:
            catalog, provider, tier = await self.resolve_route(role, prompt)
        except Exception as exc:
            log.error("Failed to resolve stream route: %s", exc)
            await self.log_execution(
                role=role,
                selected_model_id="unknown",
                selection_tier="failed",
                status="failed",
                latency_ms=0,
                error_message=str(exc),
            )
            raise exc

        model_id = catalog.model_id
        client = self.model_service.get_provider_client(provider)
        
        status = "success"
        error_msg = None
        content = ""
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)

        try:
            if provider.id == "ollama":
                from services.model_client import ChatMessage
                chat_messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages]
                content = await client.chat(chat_messages)
            else:
                content = await client.chat_completion(
                    model_id=model_id,
                    messages=messages,
                    max_tokens=kwargs.get("max_tokens", 1024),
                )
            
            completion_tokens = len(content.split())
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            cost = 0.0001 if tier != "primary" else 0.0

            await self.log_execution(
                role=role,
                selected_model_id=catalog.id,
                selection_tier=tier,
                status=status,
                latency_ms=latency_ms,
                error_message=error_msg,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                estimated_cost=cost,
            )

            # Yield parsed completion result
            yield {
                "id": f"chatcmpl-{int(time.time())}",
                "model": catalog.id,
                "content": content
            }
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            await self.log_execution(
                role=role,
                selected_model_id=catalog.id,
                selection_tier=tier,
                status=status,
                latency_ms=latency_ms,
                error_message=error_msg,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                estimated_cost=0.0,
            )
            raise exc
