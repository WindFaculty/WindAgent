"""OpenAI-compatible chat completions proxy for Hermes inference routing."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from db.models import ModelProviderORM
from services.model_client import ChatMessage as ClientChatMessage

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
    model_service = request.app.state.model_service
    
    # 1. Parse model parameter (which carries the role name)
    model_val = payload.model
    role = model_val
    if model_val.startswith("role:"):
        role = model_val[len("role:"):]

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
        stmt = select(ModelProviderORM).where(ModelProviderORM.id == catalog.provider_id)
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
                        part.get("text", "") for part in content
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

    # 6. Return standard OpenAI completion response envelope
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
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
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
