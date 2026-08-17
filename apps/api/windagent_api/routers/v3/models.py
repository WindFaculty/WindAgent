"""
V3 Models Router — Canonical Model Infrastructure Authority (Phase 12).
Provides canonical model registry, capability matrices, context limits, and endpoint bindings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

router = APIRouter(prefix="/api/v3/models", tags=["Models V3"])


class ModelEndpointBinding(BaseModel):
    id: str
    endpoint_id: str
    provider_id: str
    provider_model_id: str
    equivalence_level: str = "exact"
    confidence: float = 1.0
    is_active: bool = True


class ModelPricing(BaseModel):
    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None


class ModelDefinitionResource(BaseModel):
    id: str
    name: str
    vendor: str
    family: str
    description: str = ""
    context_window: int = 128000
    max_output_tokens: int = 4096
    capabilities: List[str] = Field(default_factory=list)
    modalities: List[str] = Field(default_factory=list)
    is_local: bool = False
    is_active: bool = True
    pricing: Optional[ModelPricing] = None
    bindings: List[ModelEndpointBinding] = Field(default_factory=list)
    benchmarks: Dict[str, float] = Field(default_factory=dict)
    created_at: str
    updated_at: str


# In-memory Canonical Models Registry State
_CANONICAL_MODELS: Dict[str, ModelDefinitionResource] = {
    "google/gemini-1.5-pro": ModelDefinitionResource(
        id="google/gemini-1.5-pro",
        name="Gemini 1.5 Pro",
        vendor="Google",
        family="Gemini",
        description="Flagship multimodal model with 2M token context window for complex reasoning and analysis.",
        context_window=2000000,
        max_output_tokens=8192,
        capabilities=["chat", "code", "vision", "audio", "tools", "reasoning"],
        modalities=["multimodal->text"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=3.5, output_per_million=10.5),
        bindings=[
            ModelEndpointBinding(
                id="bind-gemini-pro-studio",
                endpoint_id="ep-google-ai-studio",
                provider_id="google",
                provider_model_id="gemini-1.5-pro-latest",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            ),
            ModelEndpointBinding(
                id="bind-gemini-pro-vertex",
                endpoint_id="ep-google-vertex",
                provider_id="google",
                provider_model_id="gemini-1.5-pro-002",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            ),
        ],
        benchmarks={"MMLU": 85.9, "HumanEval": 84.1, "MATH": 67.7},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "google/gemini-1.5-flash": ModelDefinitionResource(
        id="google/gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        vendor="Google",
        family="Gemini",
        description="High-frequency lightweight multimodal model optimized for speed and cost-efficiency.",
        context_window=1000000,
        max_output_tokens=8192,
        capabilities=["chat", "code", "vision", "tools"],
        modalities=["multimodal->text"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=0.075, output_per_million=0.3),
        bindings=[
            ModelEndpointBinding(
                id="bind-gemini-flash-studio",
                endpoint_id="ep-google-ai-studio",
                provider_id="google",
                provider_model_id="gemini-1.5-flash-latest",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            )
        ],
        benchmarks={"MMLU": 78.9, "HumanEval": 74.3, "MATH": 54.9},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "anthropic/claude-3-5-sonnet": ModelDefinitionResource(
        id="anthropic/claude-3-5-sonnet",
        name="Claude 3.5 Sonnet",
        vendor="Anthropic",
        family="Claude",
        description="Leading frontier intelligence for coding, nuance, and agent orchestration.",
        context_window=200000,
        max_output_tokens=8192,
        capabilities=["chat", "code", "vision", "tools", "reasoning"],
        modalities=["multimodal->text"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=3.0, output_per_million=15.0),
        bindings=[
            ModelEndpointBinding(
                id="bind-claude-sonnet-direct",
                endpoint_id="ep-anthropic-direct",
                provider_id="anthropic",
                provider_model_id="claude-3-5-sonnet-20241022",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            ),
            ModelEndpointBinding(
                id="bind-claude-sonnet-openrouter",
                endpoint_id="ep-openrouter-main",
                provider_id="openrouter",
                provider_model_id="anthropic/claude-3.5-sonnet",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            ),
        ],
        benchmarks={"MMLU": 88.7, "HumanEval": 93.7, "MATH": 78.3},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "anthropic/claude-3-haiku": ModelDefinitionResource(
        id="anthropic/claude-3-haiku",
        name="Claude 3 Haiku",
        vendor="Anthropic",
        family="Claude",
        description="Fastest, most compact model for near-instant responses.",
        context_window=200000,
        max_output_tokens=4096,
        capabilities=["chat", "code", "tools"],
        modalities=["text->text"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=0.25, output_per_million=1.25),
        bindings=[
            ModelEndpointBinding(
                id="bind-claude-haiku-direct",
                endpoint_id="ep-anthropic-direct",
                provider_id="anthropic",
                provider_model_id="claude-3-haiku-20240307",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            )
        ],
        benchmarks={"MMLU": 75.2, "HumanEval": 75.9, "MATH": 40.2},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "openai/gpt-4o": ModelDefinitionResource(
        id="openai/gpt-4o",
        name="GPT-4o",
        vendor="OpenAI",
        family="GPT-4",
        description="Omni multimodal model integrating text, vision, and audio capabilities.",
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["chat", "code", "vision", "audio", "tools"],
        modalities=["multimodal->multimodal"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=2.5, output_per_million=10.0),
        bindings=[
            ModelEndpointBinding(
                id="bind-gpt4o-direct",
                endpoint_id="ep-openai-direct",
                provider_id="openai",
                provider_model_id="gpt-4o",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            )
        ],
        benchmarks={"MMLU": 88.7, "HumanEval": 90.2, "MATH": 76.6},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "openai/gpt-4o-mini": ModelDefinitionResource(
        id="openai/gpt-4o-mini",
        name="GPT-4o mini",
        vendor="OpenAI",
        family="GPT-4",
        description="Cost-efficient small model for text and vision tasks.",
        context_window=128000,
        max_output_tokens=4096,
        capabilities=["chat", "code", "vision", "tools"],
        modalities=["multimodal->text"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=0.15, output_per_million=0.6),
        bindings=[
            ModelEndpointBinding(
                id="bind-gpt4o-mini-direct",
                endpoint_id="ep-openai-direct",
                provider_id="openai",
                provider_model_id="gpt-4o-mini",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            )
        ],
        benchmarks={"MMLU": 82.0, "HumanEval": 87.2, "MATH": 70.2},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "deepseek/deepseek-r1": ModelDefinitionResource(
        id="deepseek/deepseek-r1",
        name="DeepSeek R1",
        vendor="DeepSeek",
        family="DeepSeek",
        description="Advanced open-weights reasoning model with chain-of-thought verification.",
        context_window=128000,
        max_output_tokens=8192,
        capabilities=["chat", "code", "reasoning"],
        modalities=["text->text"],
        is_local=False,
        is_active=True,
        pricing=ModelPricing(input_per_million=0.55, output_per_million=2.19),
        bindings=[
            ModelEndpointBinding(
                id="bind-deepseek-r1-direct",
                endpoint_id="ep-deepseek-direct",
                provider_id="deepseek",
                provider_model_id="deepseek-reasoner",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            ),
            ModelEndpointBinding(
                id="bind-deepseek-r1-openrouter",
                endpoint_id="ep-openrouter-main",
                provider_id="openrouter",
                provider_model_id="deepseek/deepseek-r1",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            ),
        ],
        benchmarks={"MMLU": 90.8, "HumanEval": 92.3, "MATH": 97.3},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
    "ollama/qwen2.5-coder": ModelDefinitionResource(
        id="ollama/qwen2.5-coder",
        name="Qwen 2.5 Coder (Local)",
        vendor="Alibaba",
        family="Qwen",
        description="Local code intelligence running offline via Ollama runtime.",
        context_window=32768,
        max_output_tokens=4096,
        capabilities=["code", "chat", "tools"],
        modalities=["text->text"],
        is_local=True,
        is_active=True,
        pricing=ModelPricing(input_per_million=0.0, output_per_million=0.0),
        bindings=[
            ModelEndpointBinding(
                id="bind-ollama-qwen-coder",
                endpoint_id="ep-ollama-local",
                provider_id="ollama",
                provider_model_id="qwen2.5-coder:latest",
                equivalence_level="exact",
                confidence=1.0,
                is_active=True,
            )
        ],
        benchmarks={"MMLU": 74.5, "HumanEval": 86.4, "MATH": 62.1},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-08-16T12:00:00Z",
    ),
}


@router.get("", response_model=List[ModelDefinitionResource], operation_id="models.list")
async def list_models(
    provider: Optional[str] = Query(None, description="Filter by provider ID"),
    capability: Optional[str] = Query(None, description="Filter by capability"),
    modality: Optional[str] = Query(None, description="Filter by modality"),
    is_local: Optional[bool] = Query(None, description="Filter by local/cloud execution"),
    search: Optional[str] = Query(None, description="Search term across name, vendor, description"),
) -> List[ModelDefinitionResource]:
    """List canonical model definitions matching criteria."""
    results = list(_CANONICAL_MODELS.values())

    if provider:
        p_lower = provider.lower()
        results = [
            m for m in results
            if any(b.provider_id.lower() == p_lower for b in m.bindings) or m.vendor.lower() == p_lower
        ]

    if capability:
        cap_lower = capability.lower()
        results = [m for m in results if any(c.lower() == cap_lower for c in m.capabilities)]

    if modality:
        mod_lower = modality.lower()
        results = [m for m in results if any(mod_lower in md.lower() for md in m.modalities)]

    if is_local is not None:
        results = [m for m in results if m.is_local == is_local]

    if search:
        s_lower = search.strip().lower()
        results = [
            m for m in results
            if s_lower in m.name.lower()
            or s_lower in m.id.lower()
            or s_lower in m.vendor.lower()
            or s_lower in m.description.lower()
        ]

    return results


@router.get("/{model_id:path}", response_model=ModelDefinitionResource, operation_id="models.get")
async def get_model(model_id: str) -> ModelDefinitionResource:
    """Retrieve details for a specific canonical model by ID."""
    clean_id = model_id.strip()
    if clean_id in _CANONICAL_MODELS:
        return _CANONICAL_MODELS[clean_id]

    # Try matching without prefix
    for m in _CANONICAL_MODELS.values():
        if m.id == clean_id or m.name.lower() == clean_id.lower():
            return m

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Canonical model '{model_id}' not found in registry.",
    )
