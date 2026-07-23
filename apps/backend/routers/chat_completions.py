"""OpenAI-compatible chat completions proxy for Hermes inference routing."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from db.models import ModelProviderORM
from services.model_client import ChatMessage as ClientChatMessage
from services.provider_v3_flags import v3_execute_enabled

log = logging.getLogger(__name__)

router = APIRouter(tags=["completions"])


class ChatMessagePayload(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    payload: ChatCompletionRequest = Body(...),
) -> Dict[str, Any]:
    """OpenAI-compatible completions endpoint. Maps roles to LLM clients."""
    payload_dict = payload.model_dump()

    # Phase 10: use Provider V3 gateway if enabled.
    if v3_execute_enabled():
        gateway = request.app.state.provider_gateway
        if payload.stream:
            return StreamingResponse(
                gateway.chat_completion_stream(payload_dict),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return await gateway.chat_completion(payload_dict)

    model_service = request.app.state.model_service

    # 1. Parse model parameter (which carries the role name)
    model_val = payload.model
    role = model_val
    if model_val.startswith("role:"):
        role = model_val[len("role:") :]

    log.info("Completions request model=%s resolved role=%s", model_val, role)

    # 2. Resolve catalog model for role
    catalog = await model_service.routing_service.resolve_model_for_role(role)
    if not catalog:
        # Try resolving fallback chain
        catalog = await model_service.routing_service._resolve_fallback_chain([], 1000)

    if not catalog:
        raise HTTPException(
            status_code=400,
            detail=f"No healthy, enabled model config found for role '{role}' and no fallback available.",
        )

    # 3. Retrieve model provider
    async with model_service.db.session() as session:
        stmt = select(ModelProviderORM).where(
            ModelProviderORM.id == catalog.provider_id
        )
        res = await session.execute(stmt)
        provider = res.scalar_one_or_none()
        if not provider:
            raise HTTPException(
                status_code=500,
                detail=f"Provider '{catalog.provider_id}' for resolved model '{catalog.id}' not found.",
            )

    log.info("Routing request to provider=%s model=%s", provider.id, catalog.model_id)

    # 4. Get the active LLM client
    client = model_service.get_provider_client(provider)

    # 5. Call completions depending on provider type
    try:
        if provider.id == "ollama":
            client_messages = []
            for m in payload.messages:
                content = m.get("content", "")
                if isinstance(content, list):
                    # Flatten multi-part content
                    content = " ".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                client_messages.append(
                    ClientChatMessage(role=m.get("role", "user"), content=str(content))
                )

            # Call Ollama
            response_content = await client.chat(client_messages, stream=False)
        else:
            # Call Cloud Provider
            response_content = await client.chat_completion(
                model_id=catalog.model_id,
                messages=payload.messages,
                max_tokens=payload.max_tokens,
                temperature=payload.temperature or 1.0,
            )
    except Exception as e:
        log.exception("Completion failed for provider %s: %s", provider.id, e)
        raise HTTPException(
            status_code=502,
            detail=f"Model completion failed at provider {provider.id}: {e}",
        )

    # 6. Estimate token usage (approx: 1 token ≈ 4 chars) to provide a non-zero usage field
    prompt_text = " ".join(str(m.get("content", "")) for m in payload.messages)
    prompt_tokens = max(1, len(prompt_text) // 4)
    completion_text = response_content if isinstance(response_content, str) else ""
    completion_tokens = max(1, len(completion_text) // 4)

    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    # 7a. Streaming response (SSE)
    if payload.stream:

        async def _sse_generator() -> AsyncGenerator[str, None]:
            words = completion_text.split(" ")
            for i, word in enumerate(words):
                chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_val,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant" if i == 0 else None,
                                "content": word + (" " if i < len(words) - 1 else ""),
                            },
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            # Final chunk with finish_reason=stop
            final_chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_val,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _sse_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 7b. Standard non-streaming response envelope
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created,
        "model": model_val,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_content,
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
