"""OpenAI-compatible provider gateway service phase 1."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from db.database import Database
from db.models import ModelCatalogORM, ModelProviderORM
from services.router_execution_service import RouterExecutionService

log = logging.getLogger(__name__)


class ProviderGatewayService:
    """Gateway service translating and forwarding requests to appropriate providers."""

    def __init__(self, db: Database, router_service: RouterExecutionService) -> None:
        self.db = db
        self.router_service = router_service

    async def list_models(self) -> List[Dict[str, Any]]:
        """List enabled models in OpenAI-compatible format."""
        async with self.db.session() as session:
            stmt = (
                select(ModelCatalogORM, ModelProviderORM)
                .join(ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id)
                .where(ModelCatalogORM.enabled == True)
            )
            res = await session.execute(stmt)
            rows = res.all()

            data = []
            for catalog, provider in rows:
                data.append({
                    "id": f"{provider.id}/{catalog.model_id}",
                    "object": "model",
                    "created": int(catalog.created_at.timestamp()),
                    "owned_by": provider.id,
                })
            return data

    async def chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Minimal mock/pass-through chat completions endpoint."""
        model_input = payload.get("model", "Planner")
        messages = payload.get("messages", [])
        stream = payload.get("stream", False)

        if stream:
            # We don't support streaming yet in this gateway skeletal endpoint
            raise NotImplementedError("Streaming is not supported in the Phase 1 skeletal gateway.")

        # Resolve model using simulation / routing rules if model is a role or contains prefix
        role = "Planner"
        if model_input.startswith("role:"):
            role = model_input.split(":", 1)[1]
        elif model_input.startswith("auto/"):
            role = model_input.split("/", 1)[1]
        elif model_input in ("Planner", "Coder", "GUI Agent", "Researcher", "Memory Agent", "Local Chat"):
            role = model_input

        # Resolve via router service
        sim = await self.router_service.simulate_route(role, messages[-1].get("content", ""))
        selected_model_display = sim.get("selectedModel")
        
        # Look up selected model's details
        async with self.db.session() as session:
            stmt = select(ModelCatalogORM).where(ModelCatalogORM.display_name == selected_model_display)
            res = await session.execute(stmt)
            catalog = res.scalar_one_or_none()

        if not catalog:
            raise ValueError(f"Could not resolve model for role {role}")

        # Call client via model service if available
        model_service = self.router_service.model_service
        try:
            # Resolve provider client
            stmt_prov = select(ModelProviderORM).where(ModelProviderORM.id == catalog.provider_id)
            async with self.db.session() as session:
                res_prov = await session.execute(stmt_prov)
                provider = res_prov.scalar_one_or_none()

            if not provider:
                raise ValueError("Provider not found")

            client = model_service.get_provider_client(provider)
            
            # Record execution log start
            start_time = time.perf_counter()
            content = ""
            
            if provider.id == "ollama":
                # Ollama client call
                content = await client.chat(messages)
            else:
                # Cloud provider call
                content = await client.chat_completion(
                    model_id=catalog.model_id,
                    messages=messages,
                    max_tokens=payload.get("max_tokens", 1024),
                )
            
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Log success
            await self.router_service.log_execution(
                role=role,
                selected_model_id=catalog.id,
                selection_tier="primary" if not sim.get("fallbackNeeded") else "fallback",
                status="success",
                latency_ms=duration_ms,
                prompt_tokens=sum(len(m.get("content", "").split()) for m in messages),
                completion_tokens=len(content.split()),
            )

            # Map response to OpenAI format
            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_input,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": sum(len(m.get("content", "").split()) for m in messages),
                    "completion_tokens": len(content.split()),
                    "total_tokens": sum(len(m.get("content", "").split()) for m in messages) + len(content.split()),
                }
            }
        except Exception as e:
            log.exception("Chat completion gateway error")
            # Scrub secrets if any
            err_msg = str(e)
            if "Bearer" in err_msg or "key" in err_msg.lower():
                err_msg = "Provider response error (secrets scrubbed)."
            raise NotImplementedError(f"Gateway execution failed: {err_msg}")

import time
