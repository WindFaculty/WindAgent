"""Service to resolve model routing based on role, capability, and quota availability."""
from __future__ import annotations

import logging
import json
from typing import Dict, List, Optional
from sqlalchemy import select
from db.database import Database
from db.models import ModelRoutingRuleORM, ModelCatalogORM, ModelRuntimeStatusORM, ModelProviderORM
from services.quota_service import QuotaService

log = logging.getLogger(__name__)


class ModelRoutingService:
    """Resolves routing policies from roles/capabilities to active, healthy models."""

    def __init__(self, db: Database, quota_service: QuotaService) -> None:
        self.db = db
        self.quota_service = quota_service

    async def get_routing_rules(self) -> Dict[str, Dict[str, Optional[str]]]:
        """Fetch all routing mappings."""
        async with self.db.session() as session:
            stmt = select(ModelRoutingRuleORM)
            res = await session.execute(stmt)
            rules = res.scalars().all()
            
            result = {}
            for r in rules:
                result[r.role] = {
                    "primary": r.primary_model_id,
                    "fallback": r.fallback_model_id,
                }
            return result

    async def update_routing_rules(self, rules: Dict[str, Dict[str, Optional[str]]]) -> None:
        """Update or insert routing mappings."""
        async with self.db.session() as session:
            for role, mapping in rules.items():
                stmt = select(ModelRoutingRuleORM).where(ModelRoutingRuleORM.role == role)
                res = await session.execute(stmt)
                rule = res.scalar_one_or_none()
                if not rule:
                    rule = ModelRoutingRuleORM(role=role, name=f"{role} Route")
                    session.add(rule)
                rule.primary_model_id = mapping.get("primary")
                rule.fallback_model_id = mapping.get("fallback")
                rule.policy_json = json.dumps(mapping.get("policy", {}))
            await session.commit()

    async def resolve_model_for_role(
        self,
        role: str,
        required_capabilities: Optional[List[str]] = None,
        estimated_tokens: int = 1000,
    ) -> Optional[ModelCatalogORM]:
        """Determine which model to run for a given role, checking status and quota."""
        if required_capabilities is None:
            required_capabilities = []

        rules = await self.get_routing_rules()
        mapping = rules.get(role)

        if mapping:
            # Try primary model first
            primary_id = mapping.get("primary")
            if primary_id:
                model = await self._verify_and_get_model(primary_id, required_capabilities, estimated_tokens)
                if model:
                    return model
                log.warning("Primary model %s for role %s is unavailable or out of quota. Trying fallback.", primary_id, role)

            # Try fallback model
            fallback_id = mapping.get("fallback")
            if fallback_id:
                model = await self._verify_and_get_model(fallback_id, required_capabilities, estimated_tokens)
                if model:
                    return model
                log.warning("Fallback model %s for role %s is also unavailable.", fallback_id, role)

        # No routing rule matched or both primary/fallback failed. Find any eligible model.
        log.warning("Resolving default model for role %s with capabilities %s", role, required_capabilities)
        return await self._resolve_fallback_chain(required_capabilities, estimated_tokens)

    async def _verify_and_get_model(
        self,
        model_id: str,
        required_capabilities: List[str],
        estimated_tokens: int,
    ) -> Optional[ModelCatalogORM]:
        """Fetch model and verify if it's healthy, enabled, has key, and has quota."""
        import os
        _mock_mode = os.environ.get("WINDAGENT_MODEL_BACKEND") == "mock"

        async with self.db.session() as session:
            # Query catalog, provider, and runtime status
            stmt = (
                select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .outerjoin(ModelRuntimeStatusORM, ModelCatalogORM.id == ModelRuntimeStatusORM.model_id)
                .where(ModelCatalogORM.id == model_id)
            )
            res = await session.execute(stmt)
            row = res.first()
            if not row:
                return None

            catalog, provider, runtime = row

            # In mock mode, skip all status/key/quota checks — MockProviderClient always works.
            if _mock_mode:
                return catalog

            # 1. Check if model is enabled in database
            if not catalog.enabled:
                return None

            # 2. Check if provider is enabled
            if not provider.enabled:
                return None

            # 3. Check if provider API key exists (for cloud models).
            if provider.provider_type == "cloud" and provider.api_key_env:
                if not os.environ.get(provider.api_key_env):
                    log.warning("API key missing for provider %s", provider.id)
                    return None

            # 4. Check if runtime status is offline
            if runtime and runtime.status == "Offline":
                return None

            # 5. Check capabilities
            caps = json.loads(catalog.capabilities_json)
            if not all(c in caps for c in required_capabilities):
                return None

            # 6. Check quota
            quota_allowed = await self.quota_service.should_route(provider.id, estimated_tokens)
            if not quota_allowed:
                return None

            return catalog

    async def _resolve_fallback_chain(
        self,
        required_capabilities: List[str],
        estimated_tokens: int,
    ) -> Optional[ModelCatalogORM]:
        """Find the best available model prioritizing Local -> Free cloud -> Paid cloud."""
        import os
        _mock_mode = os.environ.get("WINDAGENT_MODEL_BACKEND") == "mock"

        async with self.db.session() as session:
            stmt = (
                select(ModelCatalogORM, ModelProviderORM, ModelRuntimeStatusORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .outerjoin(ModelRuntimeStatusORM, ModelCatalogORM.id == ModelRuntimeStatusORM.model_id)
                .order_by(ModelProviderORM.priority.desc())  # Local has 100, others 80, 70, etc.
            )
            if not _mock_mode:
                # In production, only consider enabled models from enabled providers
                stmt = stmt.where(ModelCatalogORM.enabled == True).where(ModelProviderORM.enabled == True)
            res = await session.execute(stmt)
            rows = res.all()

            for catalog, provider, runtime in rows:
                # In mock mode, skip all checks — return first model found.
                if _mock_mode:
                    return catalog

                # Filter offline
                if runtime and runtime.status == "Offline":
                    continue

                # Check API Key
                if provider.provider_type == "cloud" and provider.api_key_env:
                    if not os.environ.get(provider.api_key_env):
                        continue

                # Check capabilities
                caps = json.loads(catalog.capabilities_json)
                if not all(c in caps for c in required_capabilities):
                    continue

                # Check quota
                quota_allowed = await self.quota_service.should_route(provider.id, estimated_tokens)
                if not quota_allowed:
                    continue

                return catalog

            return None
