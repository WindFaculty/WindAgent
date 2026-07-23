"""
API V2 Model Providers endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/providers", tags=["Providers V2"])


class ModelProviderInfo(BaseModel):
    name: str
    status: str
    models: List[str]


@router.get("", response_model=List[ModelProviderInfo])
async def list_providers() -> List[ModelProviderInfo]:
    return [
        ModelProviderInfo(name="openai", status="HEALTHY", models=["gpt-4o", "gpt-4o-mini", "o1-mini"]),
        ModelProviderInfo(name="anthropic", status="HEALTHY", models=["claude-3-5-sonnet", "claude-3-haiku"]),
        ModelProviderInfo(name="google", status="HEALTHY", models=["gemini-1.5-pro", "gemini-1.5-flash"]),
        ModelProviderInfo(name="ollama", status="LOCAL", models=["llama3:8b", "qwen2.5-coder"]),
    ]


@router.get("/health")
async def check_providers_health() -> Dict[str, str]:
    return {
        "openai": "ok",
        "anthropic": "ok",
        "google": "ok",
        "ollama": "ok"
    }
