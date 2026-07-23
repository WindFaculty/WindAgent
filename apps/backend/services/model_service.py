"""Model management registry service coordinating database state and provider APIs."""
from __future__ import annotations

import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, delete

from db.database import Database
from db.models import (
    ModelProviderORM,
    ModelCatalogORM,
    ModelRuntimeStatusORM,
    ModelRoutingRuleORM,
    ModelActivityORM,
    ModelBenchmarkRunORM,
)
from services.model_catalog_seed import PROVIDERS_SEED, MODELS_SEED
from services.provider_clients.openai_compatible import OpenAICompatibleClient
from services.provider_clients.google_gemini import GoogleGeminiClient
from services.provider_clients.anthropic import AnthropicClient
from services.quota_service import QuotaService
from services.model_routing_service import ModelRoutingService

log = logging.getLogger(__name__)

class MockProviderClient:
    """Mock client used in test environments to prevent real API calls and key errors."""
    def __init__(self, provider: ModelProviderORM) -> None:
        self.provider = provider
        self.provider_id = provider.id
        from utils.encryption import decrypt
        self.api_key = decrypt(provider.api_key) if provider.api_key else "mock-key"

    def has_api_key(self) -> bool:
        if self.provider.provider_type == "cloud":
            if self.api_key != "mock-key" and self.api_key:
                return True
            if self.provider.api_key_env and os.environ.get(self.provider.api_key_env):
                return True
            return False
        return True

    async def chat(self, messages: Any, **kwargs) -> str:
        last_user = ""
        for m in reversed(messages):
            if isinstance(m, dict):
                role = m.get("role")
                content = m.get("content", "")
            else:
                role = getattr(m, "role", "")
                content = getattr(m, "content", "")
            if role == "user":
                last_user = content
                break
        
        from services.model_client import MockModelClient
        if last_user in MockModelClient.DEFAULT_RESPONSES:
            return MockModelClient.DEFAULT_RESPONSES[last_user]
            
        return json.dumps({"steps": []})

    async def chat_completion(self, model_id: str, messages: Any, **kwargs) -> str:
        return await self.chat(messages, **kwargs)

    async def list_models(self) -> List[Dict[str, Any]]:
        # If real API key is configured, use the real client to fetch the model list
        if self.provider.provider_type == "cloud" and self.api_key != "mock-key" and self.api_key:
            try:
                if self.provider.api_source == "google":
                    client = GoogleGeminiClient(
                        provider_id=self.provider_id,
                        base_url=self.provider.base_url,
                        api_key=self.api_key,
                    )
                elif self.provider.api_source == "anthropic":
                    client = AnthropicClient(
                        provider_id=self.provider_id,
                        base_url=self.provider.base_url,
                        api_key=self.api_key,
                    )
                else:
                    client = OpenAICompatibleClient(
                        provider_id=self.provider_id,
                        base_url=self.provider.base_url,
                        api_key=self.api_key,
                    )
                return await client.list_models()
            except Exception as exc:
                log.warning("MockProviderClient real fallback list_models failed: %s", exc)

        # Fallback to seeded models for this provider
        try:
            from services.model_catalog_seed import MODELS_SEED
            import json
            fallback_models = []
            for m in MODELS_SEED:
                if m.get("provider_id") == self.provider_id:
                    # Strip provider prefix from seed model ID to get API model ID if present
                    m_id = m["id"]
                    prefix = f"{self.provider_id}_"
                    if m_id.startswith(prefix):
                        m_id = m_id[len(prefix):]
                    fallback_models.append({
                        "model_id": m_id,
                        "display_name": m["display_name"],
                        "capabilities": json.loads(m["capabilities_json"]) if isinstance(m.get("capabilities_json"), str) else (m.get("capabilities") or ["chat"]),
                        "context_window": m.get("context_window", 8192),
                        "raw": {}
                    })
            if fallback_models:
                return fallback_models
        except Exception as exc:
            log.warning("MockProviderClient fallback to seeds failed: %s", exc)

        if self.provider_id == "nvidia_nim":
            return [
                {
                    "model_id": "z-ai/glm-5.2",
                    "display_name": "GLM 5.2",
                    "context_window": 128000,
                    "capabilities": ["chat", "coding", "planning", "reasoning"],
                    "raw": {}
                },
                {
                    "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "display_name": "Nemotron 3 Ultra 550B Free",
                    "context_window": 8192,
                    "capabilities": ["chat", "general"],
                    "raw": {}
                },
                {
                    "model_id": "nvidia/llama-3.1-nemotron-70b-instruct",
                    "display_name": "Llama 3.1 Nemotron 70B",
                    "context_window": 128000,
                    "capabilities": ["reasoning", "planning", "chat"],
                    "raw": {}
                },
                {
                    "model_id": "meta/llama-3.1-405b-instruct",
                    "display_name": "Llama 3.1 405B Instruct",
                    "context_window": 128000,
                    "capabilities": ["reasoning", "research", "planning"],
                    "raw": {}
                },
                {
                    "model_id": "deepseek-ai/deepseek-r1",
                    "display_name": "DeepSeek R1 (NVIDIA)",
                    "context_window": 65536,
                    "capabilities": ["reasoning", "math", "research"],
                    "raw": {}
                }
            ]
        return []

    async def get_quota(self) -> Dict[str, Any]:
        return {}


class ModelService:
    """Core Model Registry service coordinating all model configurations, health, and routing."""

    def __init__(self, db: Database, ollama_client: Any) -> None:
        self.db = db
        self.ollama_client = ollama_client
        self.quota_service = QuotaService(db)
        self.routing_service = ModelRoutingService(db, self.quota_service)
        self._provider_clients: Dict[str, Any] = {}

    def get_provider_client(self, provider: ModelProviderORM) -> Any:
        """Instantiate and cache a client for the given provider."""
        from utils.encryption import decrypt
        decrypted_key = decrypt(provider.api_key) if provider.api_key else None

        import os
        if os.environ.get("WINDAGENT_MODEL_BACKEND") == "mock":
            return MockProviderClient(provider)

        client_key = provider.id
        if client_key in self._provider_clients:
            cached_client = self._provider_clients[client_key]
            if getattr(cached_client, "api_key", None) == decrypted_key:
                return cached_client

        if provider.id == "ollama":
            client = self.ollama_client
        elif provider.api_source == "google":
            client = GoogleGeminiClient(
                provider_id=provider.id,
                base_url=provider.base_url or "https://generativelanguage.googleapis.com",
                api_key_env=provider.api_key_env,
                api_key=decrypted_key,
            )
        elif provider.api_source == "anthropic":
            client = AnthropicClient(
                provider_id=provider.id,
                base_url=provider.base_url or "https://api.anthropic.com",
                api_key_env=provider.api_key_env,
                api_key=decrypted_key,
            )
        else:
            client = OpenAICompatibleClient(
                provider_id=provider.id,
                base_url=provider.base_url or "",
                api_key_env=provider.api_key_env,
                api_key=decrypted_key,
            )
        self._provider_clients[client_key] = client
        return client

    async def init_database_seeds(self) -> None:
        """Seed default providers and catalog models into SQLite database if empty."""
        async with self.db.session() as session:
            # 1. Seed providers
            stmt = select(ModelProviderORM)
            res = await session.execute(stmt)
            existing_providers = {p.id for p in res.scalars().all()}

            for p_seed in PROVIDERS_SEED:
                if p_seed["id"] not in existing_providers:
                    provider = ModelProviderORM(
                        id=p_seed["id"],
                        site_name=p_seed["site_name"],
                        api_source=p_seed["api_source"],
                        base_url=p_seed.get("base_url"),
                        management_base_url=p_seed.get("management_base_url"),
                        api_key_env=p_seed.get("api_key_env"),
                        management_api_key_env=p_seed.get("management_api_key_env"),
                        provider_type=p_seed["provider_type"],
                        quota_mode=p_seed["quota_mode"],
                        supports_openai_compatible=p_seed.get("supports_openai_compatible", True),
                        supports_model_discovery=p_seed.get("supports_model_discovery", True),
                        models_endpoint=p_seed.get("models_endpoint"),
                        chat_endpoint=p_seed.get("chat_endpoint"),
                        enabled=p_seed["enabled"],
                        priority=p_seed.get("priority", 50),
                        notes=p_seed.get("notes"),
                    )
                    session.add(provider)
                    log.info("Seeding model provider: %s", provider.id)

            # 2. Seed models
            stmt = select(ModelCatalogORM)
            res = await session.execute(stmt)
            existing_models = {m.id for m in res.scalars().all()}

            for m_seed in MODELS_SEED:
                if m_seed["id"] not in existing_models:
                    model = ModelCatalogORM(
                        id=m_seed["id"],
                        provider_id=m_seed["provider_id"],
                        model_id=m_seed["model_id"],
                        display_name=m_seed["display_name"],
                        type=m_seed["type"],
                        billing_mode=m_seed.get("billing_mode"),
                        context_window=m_seed.get("context_window"),
                        max_output_tokens=m_seed.get("max_output_tokens"),
                        capabilities_json=json.dumps(m_seed.get("capabilities", [])),
                        tags_json=json.dumps(m_seed.get("tags", [])),
                        default_roles_json=json.dumps(m_seed.get("default_roles", [])),
                        description=m_seed.get("description"),
                        deployment=m_seed.get("deployment"),
                        quantization=m_seed.get("quantization"),
                        enabled=m_seed.get("enabled", False),
                        discovered=False,
                        source="seed",
                    )
                    session.add(model)
                    log.info("Seeding catalog model: %s", model.id)

                    # Create default runtime status
                    status = ModelRuntimeStatusORM(
                        model_id=model.id,
                        status="Offline",
                        health="Unknown",
                    )
                    session.add(status)

            # 3. Seed default routing rules if empty
            stmt = select(ModelRoutingRuleORM)
            res = await session.execute(stmt)
            existing_rules = {r.role for r in res.scalars().all()}

            default_rules = {
                "Planner": {
                    "name": "Planner → Local Chat",
                    "description": "Handles general local chat and lightweight planning requests, preferring the local model before escalating to cloud providers.",
                    "primary": "google_gemini_2.5_flash",
                    "fallback": "openrouter_free",
                    "final_fallback": "ollama_qwen",
                    "status": "Active",
                    "tags": ["Planning", "Chat", "Local First", "Fallback Enabled", "High Priority"],
                    "policy": {},
                },
                "GUI Agent": {
                    "name": "GUI Agent → UI Route",
                    "description": "Weighted balancing of layout validation tasks between local models.",
                    "primary": "google_gemini_2.5_flash",
                    "fallback": "google_gemini_2.5_flash_lite",
                    "final_fallback": None,
                    "status": "Active",
                    "tags": ["GUI", "Testing", "Weighted"],
                    "policy": {},
                },
                "Coder": {
                    "name": "Coder → Code Model",
                    "description": "Route code autocompletion and structural parsing tasks to Codestral, with Sonnet as backup.",
                    "primary": "mistral_codestral",
                    "fallback": "qwen_coder_free",
                    "final_fallback": None,
                    "status": "Active",
                    "tags": ["Coding", "Autocomplete", "Standard"],
                    "policy": {},
                },
                "Researcher": {
                    "name": "Researcher → Web Stack",
                    "description": "Route structural information gathering and parsing tasks to GPT-5.5.",
                    "primary": "nvidia_nemotron_70b",
                    "fallback": "deepseek_r1_free",
                    "final_fallback": None,
                    "status": "Active",
                    "tags": ["Research", "Scraping", "Web"],
                    "policy": {},
                },
                "Memory Agent": {
                    "name": "Memory Agent → Recall",
                    "description": "Query contextual long-term vector indexes, using Gemma 2 if local memory sizes are constrained.",
                    "primary": "google_gemini_2.5_flash_lite",
                    "fallback": "openrouter_free",
                    "final_fallback": None,
                    "status": "Active",
                    "tags": ["Context", "Recall", "Fallback"],
                    "policy": {},
                },
                "Local Chat": {
                    "name": "Local Chat Route",
                    "description": "Simple local chat endpoint.",
                    "primary": "ollama/qwen",
                    "fallback": "ollama/phi",
                    "final_fallback": None,
                    "status": "Active",
                    "tags": ["Local", "Chat"],
                    "policy": {},
                },
                "Fallback": {
                    "name": "Default Fallback Route",
                    "description": "Default routing fallback policy.",
                    "primary": "openrouter_free",
                    "fallback": None,
                    "final_fallback": None,
                    "status": "Active",
                    "tags": ["System"],
                    "policy": {},
                },
            }

            for role, mapping in default_rules.items():
                if role not in existing_rules:
                    rule = ModelRoutingRuleORM(
                        role=role,
                        name=mapping["name"],
                        description=mapping["description"],
                        primary_model_id=mapping["primary"],
                        fallback_model_id=mapping["fallback"],
                        final_fallback_model_id=mapping["final_fallback"],
                        status=mapping["status"],
                        tags_json=json.dumps(mapping["tags"]),
                        policy_json=json.dumps(mapping["policy"]),
                    )
                    session.add(rule)
                    log.info("Seeding routing rule for role: %s", role)

            await session.commit()

    async def list_models(self) -> List[Dict[str, Any]]:
        """List all models matching the frontend ModelDTO shape."""
        async with self.db.session() as session:
            stmt = (
                select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .outerjoin(ModelRuntimeStatusORM, ModelCatalogORM.id == ModelRuntimeStatusORM.model_id)
            )
            res = await session.execute(stmt)
            rows = res.all()

            result = []
            for catalog, provider, runtime in rows:
                caps = json.loads(catalog.capabilities_json)
                tags = json.loads(catalog.tags_json)
                roles = json.loads(catalog.default_roles_json)

                # Fetch quota
                quota = await self.quota_service.get_latest_quota(provider.id)
                quota_dict = {
                    "mode": provider.quota_mode,
                    "rpmLimit": quota.rpm_limit if quota else None,
                    "rpdLimit": quota.rpd_limit if quota else None,
                    "tpmLimit": quota.tpm_limit if quota else None,
                    "dailyTokenLimit": quota.daily_token_limit if quota else None,
                    "monthlyTokenLimit": quota.monthly_token_limit if quota else None,
                    "remainingRequestsToday": quota.remaining_requests_today if quota else None,
                    "remainingTokensToday": quota.remaining_tokens_today if quota else None,
                    "remainingCredit": quota.remaining_credit if quota else None,
                    "resetAt": quota.reset_at.isoformat() if quota and quota.reset_at else None,
                    "source": quota.source if quota else "manual",
                }

                status_val = runtime.status if runtime else "Offline"
                # If provider missing API key, set status Offline/Needs Key
                has_key = True
                if provider.provider_type == "cloud":
                    if not provider.api_key:
                        if provider.api_key_env:
                            import os
                            if not os.environ.get(provider.api_key_env):
                                has_key = False
                                status_val = "Offline"
                        else:
                            has_key = False
                            status_val = "Offline"

                result.append({
                    "id": catalog.id,
                    "name": catalog.display_name,
                    "provider": provider.site_name,
                    "providerId": provider.id,
                    "apiSource": provider.api_source,
                    "modelId": catalog.model_id,
                    "baseUrl": provider.base_url or "—",
                    "type": catalog.type,
                    "billingMode": provider.quota_mode,
                    "context": f"{catalog.context_window // 1000}K" if catalog.context_window else "Unknown",
                    "status": status_val,
                    "enabled": catalog.enabled,
                    "hasKey": has_key,
                    "roles": ", ".join(roles) if roles else "—",
                    "rt": f"{int(runtime.latency_p50_ms)}ms" if runtime and runtime.latency_p50_ms else "—",
                    "sr": f"{int(runtime.success_rate * 100)}%" if runtime and runtime.success_rate else "—",
                    "sparkPoints": "0,15 15,18 30,12 45,16 60,6 68,10", # default aesthetic sparkline
                    "description": catalog.description or "No description available.",
                    "deployment": catalog.deployment or "Cloud API",
                    "quantization": catalog.quantization,
                    "vram": "—",
                    "vramVal": "—",
                    "vramMax": "—",
                    "vramPct": 0,
                    "ramVal": "—",
                    "ramMax": "—",
                    "ramPct": 0,
                    "contextVal": "0",
                    "contextMax": f"{catalog.context_window // 1000}K" if catalog.context_window else "Unknown",
                    "contextPct": 0,
                    "tokensPerSec": f"{runtime.tokens_per_sec:.1f}" if runtime and runtime.tokens_per_sec else "—",
                    "latencyP50Ms": runtime.latency_p50_ms if runtime else None,
                    "latencyP90Ms": runtime.latency_p90_ms if runtime else None,
                    "successRate": runtime.success_rate if runtime else None,
                    "uptime": "30d" if catalog.type == "API" else "—",
                    "assignedRoles": [{"name": r, "type": "Candidate"} for r in roles],
                    "tags": tags,
                    "capabilities": caps,
                    "quota": quota_dict,
                })
            return result

    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        models = await self.list_models()
        for m in models:
            if m["id"] == model_id:
                return m
        return None

    async def add_model(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Manually register a model configuration."""
        async with self.db.session() as session:
            model = ModelCatalogORM(
                id=f"{config['provider_id']}_{config['model_id'].replace('/', '_').replace(':', '_')}",
                provider_id=config["provider_id"],
                model_id=config["model_id"],
                display_name=config["name"],
                type=config.get("type", "API"),
                capabilities_json=json.dumps(config.get("capabilities", ["chat"])),
                tags_json=json.dumps(config.get("tags", [])),
                default_roles_json=json.dumps(config.get("roles", [])),
                description=config.get("description", "Manually registered model."),
                deployment="Cloud API" if config.get("type", "API") == "API" else "Local",
                enabled=True,
                source="discovered",
            )
            session.add(model)
            
            status = ModelRuntimeStatusORM(
                model_id=model.id,
                status="Ready" if config.get("type") == "API" else "Offline",
                health="Healthy" if config.get("type") == "API" else "Unknown",
            )
            session.add(status)
            await session.commit()
            
            await self.log_activity(
                model_id=model.id,
                provider_id=model.provider_id,
                event_type="registered",
                message=f"Model {model.display_name} registered successfully.",
            )
            return {"id": model.id, "display_name": model.display_name}

    async def delete_model(self, model_id: str) -> Dict[str, Any]:
        """Remove a model catalog entry and its runtime status row."""
        async with self.db.session() as session:
            # Delete runtime status first (FK constraint)
            await session.execute(
                delete(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == model_id)
            )
            result = await session.execute(
                delete(ModelCatalogORM).where(ModelCatalogORM.id == model_id)
            )
            await session.commit()
            if result.rowcount == 0:
                return {"status": "error", "message": f"Model {model_id} not found"}
            await self.log_activity(
                model_id=model_id,
                provider_id="",
                event_type="deleted",
                message=f"Model {model_id} removed from registry.",
            )
            return {"status": "success", "message": f"Model {model_id} deleted"}

    async def clear_provider_api_key(self, provider_id: str) -> Dict[str, Any]:
        """Clear the stored API key for a provider (set to None)."""
        async with self.db.session() as session:
            stmt = select(ModelProviderORM).where(ModelProviderORM.id == provider_id)
            res = await session.execute(stmt)
            provider = res.scalar_one_or_none()
            if not provider:
                return {"status": "error", "message": f"Provider {provider_id} not found"}
            provider.api_key = None
            await session.commit()
            return {"status": "success", "message": f"API key cleared for provider {provider_id}"}

    async def import_model(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Stub for model import job."""
        model_name = config.get("model_name")
        await self.log_activity(
            model_id=f"ollama_{model_name}",
            provider_id="ollama",
            event_type="import_queued",
            message=f"Model import job queued for local Ollama: {model_name}",
        )
        return {"status": "queued", "model_name": model_name, "message": "Import job has been queued successfully."}

    async def start_model(self, model_id: str) -> Dict[str, Any]:
        """Load/start the model runtime."""
        async with self.db.session() as session:
            stmt = select(ModelCatalogORM).where(ModelCatalogORM.id == model_id)
            res = await session.execute(stmt)
            model = res.scalar_one_or_none()
            if not model:
                return {"status": "error", "message": "Model not found"}

            stmt = select(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == model_id)
            res = await session.execute(stmt)
            status = res.scalar_one_or_none()
            if not status:
                status = ModelRuntimeStatusORM(model_id=model_id)
                session.add(status)

            if model.type == "Local":
                # Handle local Ollama start logic
                if hasattr(self.ollama_client, "start_ollama_model"):
                    await self.ollama_client.start_ollama_model(model.model_id)
                status.status = "Running"
                status.health = "Healthy"
            else:
                # Cloud model: probe it
                status.status = "Ready"
                status.health = "Healthy"
                await self.probe_model(model_id)

            await session.commit()
            await self.log_activity(
                model_id=model_id,
                provider_id=model.provider_id,
                event_type="started",
                message=f"Model {model.display_name} started successfully.",
            )
            return {"status": "started", "model_id": model_id}

    async def stop_model(self, model_id: str) -> Dict[str, Any]:
        """Unload/stop the model runtime."""
        async with self.db.session() as session:
            stmt = select(ModelCatalogORM).where(ModelCatalogORM.id == model_id)
            res = await session.execute(stmt)
            model = res.scalar_one_or_none()
            if not model:
                return {"status": "error", "message": "Model not found"}

            stmt = select(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == model_id)
            res = await session.execute(stmt)
            status = res.scalar_one_or_none()
            if status:
                if model.type == "Local":
                    if hasattr(self.ollama_client, "stop_ollama_model"):
                        await self.ollama_client.stop_ollama_model(model.model_id)
                    status.status = "Offline"
                else:
                    # Cloud: set status Idle/Offline
                    status.status = "Idle"
                await session.commit()

            await self.log_activity(
                model_id=model_id,
                provider_id=model.provider_id,
                event_type="stopped",
                message=f"Model {model.display_name} stopped.",
            )
            return {"status": "stopped", "model_id": model_id}

    async def restart_model(self, model_id: str) -> Dict[str, Any]:
        await self.stop_model(model_id)
        await asyncio.sleep(0.5)
        return await self.start_model(model_id)

    async def set_default_model(self, model_id: str) -> Dict[str, Any]:
        """Set this model as default routing fallback."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == "Fallback")
            res = await session.execute(stmt)
            rule = res.scalar_one_or_none()
            if not rule:
                rule = ModelRoutingRuleORM(role="Fallback")
                session.add(rule)
            rule.primary_model_id = model_id
            await session.commit()

            await self.log_activity(
                model_id=model_id,
                provider_id=None,
                event_type="route_changed",
                message=f"Model {model_id} set as default routing fallback.",
            )
            return {"status": "success", "message": f"{model_id} is now default fallback."}

    async def list_activity(self) -> List[Dict[str, Any]]:
        """List recent activity logs."""
        async with self.db.session() as session:
            stmt = select(ModelActivityORM).order_by(ModelActivityORM.created_at.desc()).limit(50)
            res = await session.execute(stmt)
            activities = res.scalars().all()
            
            result = []
            for act in activities:
                # Format time: e.g. "10:21 AM"
                local_time = act.created_at.strftime("%I:%M %p")
                result.append({
                    "id": act.id,
                    "time": local_time,
                    "modelId": act.model_id,
                    "providerId": act.provider_id,
                    "eventType": act.event_type,
                    "level": act.level,
                    "message": act.message,
                    "createdAt": act.created_at.isoformat(),
                })
            return result

    async def get_logs(self, model_id: str) -> List[Dict[str, Any]]:
        """Get logs for a specific model."""
        async with self.db.session() as session:
            stmt = (
                select(ModelActivityORM)
                .where(ModelActivityORM.model_id == model_id)
                .order_by(ModelActivityORM.created_at.desc())
                .limit(20)
            )
            res = await session.execute(stmt)
            activities = res.scalars().all()
            return [{"time": a.created_at.strftime("%I:%M %p"), "message": a.message} for a in activities]

    async def list_benchmarks(self) -> Dict[str, Any]:
        """Return benchmark statistics formatted for UI charts."""
        async with self.db.session() as session:
            stmt = select(ModelBenchmarkRunORM).order_by(ModelBenchmarkRunORM.created_at.desc())
            res = await session.execute(stmt)
            runs = res.scalars().all()

            # Group by model
            model_stats = {}
            for r in runs:
                if r.model_id not in model_stats:
                    stmt_catalog = select(ModelCatalogORM.display_name, ModelCatalogORM.provider_id).where(ModelCatalogORM.id == r.model_id)
                    cat_res = await session.execute(stmt_catalog)
                    cat_row = cat_res.first()
                    display_name = cat_row[0] if cat_row else r.model_id
                    provider = cat_row[1] if cat_row else r.provider_id
                    
                    model_stats[r.model_id] = {
                        "modelId": r.model_id,
                        "name": display_name,
                        "provider": provider,
                        "latencyP50Ms": r.latency_p50_ms,
                        "latencyP90Ms": r.latency_p90_ms,
                        "tokensPerSec": r.tokens_per_sec,
                        "successRate": r.success_rate,
                        "history": [],
                    }
                model_stats[r.model_id]["history"].append({
                    "ts": r.created_at.isoformat(),
                    "value": r.latency_p50_ms,
                })

            return {
                "metric": "latency_p50_ms",
                "items": list(model_stats.values())
            }

    async def run_benchmark(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a quick benchmark test on a list of models."""
        model_ids = config.get("model_ids", [])
        prompt = config.get("prompt", "Say OK in one sentence.")
        max_tokens = config.get("max_tokens", 16)

        results = []
        for m_id in model_ids:
            start_time = time.perf_counter()
            success = False
            tokens_generated = 0
            err_msg = None
            
            try:
                # Resolve provider and client
                async with self.db.session() as session:
                    stmt = (
                        select(ModelCatalogORM, ModelProviderORM)
                        .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                        .where(ModelCatalogORM.id == m_id)
                    )
                    res = await session.execute(stmt)
                    row = res.first()
                    if row:
                        catalog, provider = row
                        client = self.get_provider_client(provider)
                        if m_id.startswith("ollama"):
                            # Handle Ollama benchmark call
                            out = await client.chat([{"role": "user", "content": prompt}])
                            success = True
                            tokens_generated = len(out.split()) # simple estimate
                        else:
                            # Cloud client call
                            out = await client.chat_completion(
                                model_id=catalog.model_id,
                                messages=[{"role": "user", "content": prompt}],
                                max_tokens=max_tokens,
                            )
                            success = True
                            tokens_generated = len(out.split())
                    else:
                        err_msg = "Model not found in catalog"
            except Exception as exc:
                err_msg = str(exc)
                log.exception("Benchmark failed for model %s: %s", m_id, err_msg)

            duration = time.perf_counter() - start_time
            latency_ms = int(duration * 1000)
            tokens_per_sec = tokens_generated / duration if duration > 0 and success else 0.0

            if success:
                async with self.db.session() as session:
                    run = ModelBenchmarkRunORM(
                        model_id=m_id,
                        provider_id=m_id.split("_")[0],
                        latency_p50_ms=latency_ms,
                        latency_p90_ms=latency_ms * 1.2, # synthetic p90
                        tokens_per_sec=tokens_per_sec,
                        success_rate=1.0,
                        prompt_tokens=len(prompt.split()),
                        completion_tokens=tokens_generated,
                        total_tokens=len(prompt.split()) + tokens_generated,
                        test_name=config.get("test_name", "smoke"),
                    )
                    session.add(run)

                    # Update runtime stats
                    stmt = select(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == m_id)
                    res = await session.execute(stmt)
                    status = res.scalar_one_or_none()
                    if not status:
                        status = ModelRuntimeStatusORM(model_id=m_id)
                        session.add(status)
                    status.latency_p50_ms = latency_ms
                    status.latency_p90_ms = latency_ms * 1.2
                    status.tokens_per_sec = tokens_per_sec
                    status.success_rate = 1.0
                    status.last_probe_at = datetime.now(timezone.utc)
                    await session.commit()

                await self.log_activity(
                    model_id=m_id,
                    provider_id=m_id.split("_")[0],
                    event_type="benchmark_completed",
                    message=f"Benchmark completed successfully: latency={latency_ms}ms, speed={tokens_per_sec:.1f} t/s",
                )
                results.append({"model_id": m_id, "success": True, "latency_ms": latency_ms})
            else:
                await self.log_activity(
                    model_id=m_id,
                    provider_id=m_id.split("_")[0],
                    level="error",
                    event_type="benchmark_failed",
                    message=f"Benchmark failed: {err_msg}",
                )
                results.append({"model_id": m_id, "success": False, "error": err_msg})

        return {"results": results}

    async def probe_model(self, model_id: str) -> Dict[str, Any]:
        """Perform a quick health probe check and update runtime metrics."""
        async with self.db.session() as session:
            stmt = (
                select(ModelCatalogORM, ModelProviderORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .where(ModelCatalogORM.id == model_id)
            )
            res = await session.execute(stmt)
            row = res.first()
            if not row:
                return {"status": "error", "message": "Model not found"}
            catalog, provider = row

        start_time = time.perf_counter()
        success = False
        error_msg = None

        try:
            client = self.get_provider_client(provider)
            if catalog.type == "Local":
                # Ollama probe
                if hasattr(self.ollama_client, "health"):
                    health = await self.ollama_client.health()
                    success = health.get("online", False)
                    error_msg = health.get("error")
                else:
                    success = True
            else:
                # Cloud probe
                if hasattr(client, "has_api_key") and not client.has_api_key():
                    error_msg = "Missing API key"
                else:
                    out = await client.chat_completion(
                        model_id=catalog.model_id,
                        messages=[{"role": "user", "content": "hello"}],
                        max_tokens=5,
                    )
                    success = bool(out)
        except Exception as exc:
            error_msg = str(exc)
            log.warning("Probe failed for model %s: %s", model_id, error_msg)

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        async with self.db.session() as session:
            stmt = select(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == model_id)
            res = await session.execute(stmt)
            status = res.scalar_one_or_none()
            if not status:
                status = ModelRuntimeStatusORM(model_id=model_id)
                session.add(status)
            
            status.status = "Ready" if success and catalog.type == "API" else ("Running" if success else "Offline")
            status.health = "Healthy" if success else "Unhealthy"
            status.last_probe_at = datetime.now(timezone.utc)
            status.last_error = error_msg
            if success:
                status.latency_p50_ms = latency_ms
                status.success_rate = 1.0
            await session.commit()

        await self.log_activity(
            model_id=model_id,
            provider_id=catalog.provider_id,
            event_type="health_probe",
            message=f"Probe complete: health={'Healthy' if success else 'Unhealthy'}, latency={latency_ms}ms" + (f", error={error_msg}" if error_msg else ""),
        )

        return {"success": success, "latency_ms": latency_ms, "error": error_msg}

    async def sync_provider_models(self, provider_id: str, selected_model_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Sync model catalog from provider API, saving only the selected models if specified."""
        async with self.db.session() as session:
            stmt = select(ModelProviderORM).where(ModelProviderORM.id == provider_id)
            res = await session.execute(stmt)
            provider = res.scalar_one_or_none()
            if not provider:
                return {"status": "error", "message": "Provider not found"}

            client = self.get_provider_client(provider)
            try:
                models = await client.list_models()
            except Exception as exc:
                log.exception("Sync failed for provider %s: %s", provider_id, exc)
                return {"status": "error", "message": f"Sync failed: {exc}"}

            # Upsert into model_catalog
            stmt_cat = select(ModelCatalogORM).where(ModelCatalogORM.provider_id == provider_id)
            res_cat = await session.execute(stmt_cat)
            existing_models = {m.model_id: m for m in res_cat.scalars().all()}

            new_count = 0
            updated_count = 0
            
            selected_set = set(selected_model_ids) if selected_model_ids is not None else None
            seen_model_ids = set()

            for m in models:
                m_id = m["model_id"]
                if m_id in seen_model_ids:
                    continue
                seen_model_ids.add(m_id)

                # Skip if we specified a selection and this model is not in it
                if selected_set is not None and m_id not in selected_set:
                    continue

                if m_id in existing_models:
                    model = existing_models[m_id]
                    model.display_name = m["display_name"]
                    model.context_window = m.get("context_window")
                    model.capabilities_json = json.dumps(m["capabilities"])
                    model.enabled = True
                    updated_count += 1
                else:
                    model = ModelCatalogORM(
                        id=f"{provider_id}_{m_id.replace('/', '_').replace(':', '_')}",
                        provider_id=provider_id,
                        model_id=m_id,
                        display_name=m["display_name"],
                        type="API" if provider.provider_type == "cloud" else "Local",
                        context_window=m.get("context_window"),
                        capabilities_json=json.dumps(m["capabilities"]),
                        tags_json=json.dumps(["Discovered"]),
                        default_roles_json=json.dumps([]),
                        description="Automatically discovered model.",
                        deployment="Cloud API" if provider.provider_type == "cloud" else "Local",
                        enabled=True,
                        discovered=True,
                        source="discovered",
                    )
                    session.add(model)
                    new_count += 1
                    
                    status = ModelRuntimeStatusORM(
                        model_id=model.id,
                        status="Ready" if provider.provider_type == "cloud" else "Offline",
                        health="Unknown",
                    )
                    session.add(status)

            # If selected_model_ids is specified, delete any existing models not in it
            deleted_count = 0
            if selected_set is not None:
                for db_m_id, model in existing_models.items():
                    if db_m_id not in selected_set:
                        await session.execute(
                            delete(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == model.id)
                        )
                        await session.delete(model)
                        deleted_count += 1

            await session.commit()
            
            total_saved = new_count + updated_count
            await self.log_activity(
                model_id=None,
                provider_id=provider_id,
                event_type="sync_completed",
                message=f"Sync completed. Saved {total_saved} models (added {new_count}, updated {updated_count}, deleted {deleted_count}).",
            )
            return {"status": "success", "added": new_count, "synced": total_saved}

    async def update_model_selection(self, provider_id: str, selected_model_ids: List[str]) -> Dict[str, Any]:
        """Update enabled/disabled state for existing models in DB, removing any that are no longer selected."""
        async with self.db.session() as session:
            stmt = select(ModelCatalogORM).where(ModelCatalogORM.provider_id == provider_id)
            res = await session.execute(stmt)
            existing_models = res.scalars().all()

            if not existing_models:
                return {"status": "error", "message": "No models found for this provider. Please sync first."}

            selected_set = set(selected_model_ids)
            deleted_count = 0
            updated_count = 0
            
            for model in existing_models:
                if model.model_id not in selected_set:
                    await session.execute(
                        delete(ModelRuntimeStatusORM).where(ModelRuntimeStatusORM.model_id == model.id)
                    )
                    await session.delete(model)
                    deleted_count += 1
                else:
                    if not model.enabled:
                        model.enabled = True
                        updated_count += 1

            await session.commit()
            await self.log_activity(
                model_id=None,
                provider_id=provider_id,
                event_type="selection_updated",
                message=f"Model selection updated: {len(selected_set)} models enabled, deleted {deleted_count} unselected models.",
            )
            return {
                "status": "success",
                "enabled": len(selected_set),
                "deleted": deleted_count,
                "updated": updated_count,
            }



    async def log_activity(
        self,
        model_id: Optional[str],
        provider_id: Optional[str],
        event_type: str,
        message: str,
        level: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new model activity log entry."""
        async with self.db.session() as session:
            act = ModelActivityORM(
                model_id=model_id,
                provider_id=provider_id,
                level=level,
                event_type=event_type,
                message=message,
                metadata_json=json.dumps(metadata or {}),
            )
            session.add(act)
            await session.commit()
            log.info("ModelActivity [%s]: %s (model=%s, provider=%s)", level.upper(), message, model_id, provider_id)
import time
