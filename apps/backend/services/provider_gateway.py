"""OpenAI-compatible provider gateway service phase 2."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import select

from db.database import Database
from db.models import ModelCatalogORM, ModelProviderORM
from services.provider_v3_coordinator import ProviderV3Coordinator
from services.provider_v3_flags import v3_execute_enabled
from services.router_execution_service import RouterExecutionService

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
                .join(
                    ModelProviderORM, ModelCatalogORM.provider_id == ModelProviderORM.id
                )
                .where(ModelCatalogORM.enabled.is_(True))
            )
            res = await session.execute(stmt)
            rows = res.all()

            data = []
            for catalog, provider in rows:
                data.append(
                    {
                        "id": f"{provider.id}/{catalog.model_id}",
                        "object": "model",
                        "created": int(catalog.created_at.timestamp()),
                        "owned_by": provider.id,
                    }
                )
            return data

    async def chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Forward chat completion requests using router execution."""
        model_input, role, messages = self._resolve_payload(payload)
        max_tokens = payload.get("max_tokens", 1024)
        tools = payload.get("tools", [])
        tool_choice = payload.get("tool_choice", "auto")

        try:
            if v3_execute_enabled() and self.v3_coordinator is not None:
                if tools:
                    v3_response = await self.v3_coordinator.execute_chat_with_tools(
                        role=role,
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        max_tokens=max_tokens,
                        scope_id=payload.get("scope_id"),
                    )
                    return self._map_v3_response_to_openai(model_input, v3_response, messages)
                content = await self.v3_coordinator.execute_chat(
                    role=role,
                    messages=messages,
                    max_tokens=max_tokens,
                    scope_id=payload.get("scope_id"),
                )
            else:
                content = await self.router_service.execute_chat(
                    role=role,
                    messages=messages,
                    max_tokens=max_tokens,
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
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
        except Exception as e:
            log.exception("Chat completion gateway error")
            err_msg = str(e)
            if "Bearer" in err_msg or "key" in err_msg.lower():
                err_msg = "Provider response error (secrets scrubbed)."
            raise ValueError(f"Gateway execution failed: {err_msg}")

    async def chat_completion_stream(
        self, payload: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Generate OpenAI-compatible SSE events stream."""
        model_input, role, messages = self._resolve_payload(payload)
        max_tokens = payload.get("max_tokens", 1024)
        scope_id = payload.get("scope_id")

        try:
            if v3_execute_enabled() and self.v3_coordinator is not None:
                content = ""
                tool_calls: List[Dict[str, Any]] = []
                finish_reason = "stop"
                async for event in self.v3_coordinator.execute_chat_stream(
                    role=role,
                    messages=messages,
                    max_tokens=max_tokens,
                    scope_id=scope_id,
                ):
                    if event.event_type == "token":
                        content += event.delta or ""
                    elif event.event_type == "tool_call_delta":
                        tc = event.tool_call_delta
                        if tc:
                            tool_calls.append(tc)
                    elif event.event_type == "done":
                        finish_reason = event.finish_reason or "stop"
                        break
                    elif event.event_type == "error":
                        raise ValueError(event.error or "V3 stream error")
            else:
                generator = self.router_service.execute_chat_stream(
                    role=role,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                parts = []
                async for chunk in generator:
                    parts.append(chunk["content"])
                content = "".join(parts)
                tool_calls = []
                finish_reason = "stop"

            async for sse in self._sse_chunks(model_input, content, tool_calls=tool_calls or None, finish_reason=finish_reason):
                yield sse
        except Exception as e:
            log.exception("Chat completion stream gateway error")
            err_msg = str(e)
            if "Bearer" in err_msg or "key" in err_msg.lower():
                err_msg = "Provider response error (secrets scrubbed)."
            error_data = {
                "error": {
                    "message": f"Gateway execution failed: {err_msg}",
                    "type": "invalid_request_error",
                    "code": None,
                }
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            yield "data: [DONE]\n\n"

    def _map_v3_response_to_openai(
        self, model_input: str, response: Any, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        completion_tokens = len((response.text or "").split()) + len(response.tool_calls)
        message: Dict[str, Any] = {"role": "assistant", "content": response.text}
        if response.tool_calls:
            message["tool_calls"] = response.tool_calls
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_input,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": response.finish_reason or "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    def _resolve_payload(
        self, payload: Dict[str, Any]
    ) -> tuple[str, str, List[Dict[str, Any]]]:
        model_input = payload.get("model", "Planner")
        messages = payload.get("messages", [])

        role = "Planner"
        if model_input.startswith("role:"):
            role = model_input.split(":", 1)[1]
        elif model_input.startswith("auto/"):
            role = model_input.split("/", 1)[1]
        elif model_input in (
            "Planner",
            "Coder",
            "GUI Agent",
            "Researcher",
            "Memory Agent",
            "Local Chat",
        ):
            role = model_input

        return model_input, role, messages

    async def _sse_chunks(
        self,
        model_input: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        finish_reason: str = "stop",
    ) -> AsyncGenerator[str, None]:
        completion_id = f"chatcmpl-{int(time.time())}"
        created = int(time.time())

        if tool_calls:
            chunk_data = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_input,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "tool_calls": tool_calls},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"

        chunk_size = 5
        chunks = [
            content[i : i + chunk_size] for i in range(0, len(content), chunk_size)
        ] or [""]

        for val in chunks:
            chunk_data = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_input,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": val} if val else {},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"
            await asyncio.sleep(0.01)

        stop_data = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_input,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": finish_reason,
                }
            ],
        }
        yield f"data: {json.dumps(stop_data)}\n\n"
        yield "data: [DONE]\n\n"
