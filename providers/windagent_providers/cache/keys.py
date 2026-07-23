"""
Cache key builders for WindAgent Provider Subsystem V3.

Keys are stable, secret-free, and include all values that affect response.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from windagent_providers.base.contracts import ProviderRequest
from windagent_providers.cache.contracts import CacheNamespace, ResponseCacheKey


def _canonical_json(value: Any) -> str:
    """Deterministic JSON used for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def build_response_cache_key(
    request: ProviderRequest,
    namespace: CacheNamespace,
    canonical_model_id: str,
    *,
    revision: Optional[str] = None,
    provider_behavior_version: str = "1",
) -> ResponseCacheKey:
    """
    Build a response cache key from a provider request.

    Only deterministic fields are hashed.  ``provider_extensions`` and raw
    payload metadata are intentionally excluded because providers map them
    internally and they may contain secrets.
    """
    messages_hash = _hash(request.messages)
    system_hash = _hash(request.system_instruction or "")
    tools_hash = _hash(request.tools)
    structured_output_hash = _hash(request.structured_output_schema or {})

    return ResponseCacheKey(
        namespace=namespace,
        canonical_model_id=canonical_model_id,
        revision=revision,
        messages_hash=messages_hash,
        system_hash=system_hash,
        tools_hash=tools_hash,
        structured_output_hash=structured_output_hash,
        temperature=request.temperature,
        top_p=request.top_p,
        seed=request.seed,
        max_output_tokens=request.max_output_tokens,
        provider_behavior_version=provider_behavior_version,
    )
