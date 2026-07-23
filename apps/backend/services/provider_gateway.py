"""OpenAI-compatible provider gateway service phase 2."""
from __future__ import annotations

import json
import logging
import asyncio
import time
from typing import Any, Dict, List, Optional, AsyncGenerator
from sqlalchemy import select
from db.database import Database
from db.models import ModelCatalogORM, ModelProviderORM
from services.router_execution_service import RouterExecutionService
from services.provider_v3_flags import v3_execute_enabled
from services.provider_v3_coordinator import ProviderV3Coordinator

from windagent_providers.base.contracts import ProviderStreamEvent

log = logging.getLogger(__name__)


class ProviderGatewayService:
    """Gateway service translating and forwarding requests to appropriate providers."""

    def __init__(
        self,
        db: Database,
        router_service: RouterExecutionService,
        v3_coordinator: Optional[ProviderV3Coordinator] = None,
    ) -> None:
        self.db = db
        self.router_service = router_service
        self.v3_coordinator = v3_coordinator

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
        """Forward chat completion requests using router execution."""
        model_input = payload.get("model", "Planner")
        messages = payload.get("messages", [])

        # Resolve role
        role = "Planner"
        if model_input.startswith("role:"):
            role = model_input.split(":", 1)[1]
        elif model_input.startswith("auto/"):
            role = model_input.split("/", 1)[1]
        elif model_input in ("Planner", "Coder", "GUI Agent", "Researcher", "Memory Agent", "Local Chat"):
            role = model_input

        try:
            if v3_execute_enabled() and self.v3_coordinator is not None:
                content = await self.v3_coordinator.execute_chat(
                    role=role,
                    messages=messages,
                    max_tokens=payload.get("max_tokens", 1024),
                    scope_id=payload.get("scope_id"),
                )
            else:
                content = await self.router_service.execute_chat(
                    role=role,
                    messages=messages,
                    max_tokens=payload.get("max_tokens", 1024),
                )
            
            # Map response to OpenAI format
            prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
            completion_tokens = len(content.split())
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
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }
            }
        except Exception as e:
            log.exception("Chat completion gateway error")
            err_msg = str(e)
            if "Bearer" in err_msg or "key" in err_msg.lower():
                err_msg = "Provider response error (secrets scrubbed)."
            raise ValueError(f"Gateway execution failed: {err_msg}")

    async def chat_completion_stream(self, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate OpenAI-compatible SSE events stream."""
        model_input = payload.get("model", "Planner")
        messages = payload.get("messages", [])

        # Resolve role
        role = "Planner"
        if model_input.startswith("role:"):
            role = model_input.split(":", 1)[1]
        elif model_input.startswith("auto/"):
            role = model_input.split("/", 1)[1]
        elif model_input in ("Planner", "Coder", "GUI Agent", "Researcher", "Memory Agent", "Local Chat"):
            role = model_input

        try:
            if v3_execute_enabled() and self.v3_coordinator is not None:
                generator = self.v3_coordinator.execute_chat_stream(
                    role=role,
                    messages=messages,
                    max_tokens=payload.get("max_tokens", 1024),
                    scope_id=payload.get("scope_id"),
                )
                v3_content_parts: List[str] = []
                async for event in generator:
                    if event.event_type == "token":
                        v3_content_parts.append(event.delta or "")
                    elif event.event_type == "done":
                        break
                    elif event.event_type == "error":
                        raise ValueError(event.error or "V3 stream error")
                content = "".join(v3_content_parts)
                # Emit as a single SSE stream chunk for compatibility.
                model_id = model_input
                completion_id = f"chatcmpl-{int(time.time())}"
                created = int(time.time())

                chunk_size = 5
                chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

                for val in chunks:
                    chunk_data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_id,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": val},
                                "finish_reason": None
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    await asyncio.sleep(0.01)

                stop_data = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                yield f"data: {json.dumps(stop_data)}\n\n"
                yield "data: [DONE]\n\n"
                return

            generator = self.router_service.execute_chat_stream(
                role=role,
                messages=messages,
                max_tokens=payload.get("max_tokens", 1024),
            )
            async for chunk in generator:
                content = chunk["content"]
                model_id = chunk["model"]
                completion_id = chunk["id"]
                created = int(time.time())

                chunk_size = 5
                chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

                for val in chunks:
                    chunk_data = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_id,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": val},
                                "finish_reason": None
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    await asyncio.sleep(0.01)

                # Final stop chunk
                stop_data = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                yield f"data: {json.dumps(stop_data)}\n\n"
                yield "data: [DONE]\n\n"
        except Exception as e:
            log.exception("Chat completion stream gateway error")
            err_msg = str(e)
            if "Bearer" in err_msg or "key" in err_msg.lower():
                err_msg = "Provider response error (secrets scrubbed)."
            error_data = {
                "error": {
                    "message": f"Gateway execution failed: {err_msg}",
                    "type": "invalid_request_error",
                    "code": None
                }
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"
