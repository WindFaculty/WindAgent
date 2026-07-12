"""FastAPI Router for OpenAI-compatible model lists and chat completions."""
from __future__ import annotations

import logging
from typing import Any, Dict
from fastapi import APIRouter, Request, Body, HTTPException
from fastapi.responses import StreamingResponse

from services.provider_gateway import ProviderGatewayService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


def _gateway(request: Request) -> ProviderGatewayService:
    return request.app.state.provider_gateway


@router.get("/models")
async def list_models(request: Request) -> Dict[str, Any]:
    """List available models in OpenAI-compatible format."""
    gateway = _gateway(request)
    models = await gateway.list_models()
    return {
        "object": "list",
        "data": models
    }


@router.post("/chat/completions")
async def chat_completions(request: Request, payload: Dict[str, Any] = Body(...)):
    """Forward chat completions requests to resolved backend models."""
    gateway = _gateway(request)
    stream = payload.get("stream", False)
    
    if stream:
        try:
            return StreamingResponse(
                gateway.chat_completion_stream(payload),
                media_type="text/event-stream"
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        try:
            return await gateway.chat_completion(payload)
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
