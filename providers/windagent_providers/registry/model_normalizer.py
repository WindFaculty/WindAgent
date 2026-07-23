"""
Model ID Parser & Normalizer for WindAgent Provider Subsystem V3.
Extracts vendor, family, revision, quantization, and context limits from raw model identifiers.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NormalizedModelInfo:
    raw_model_id: str
    vendor: str
    family: str
    revision: Optional[str]
    quantization: Optional[str]
    parameter_size: Optional[str]
    canonical_name: str
    equivalence_fingerprint: str


_REVISION_PATTERNS = [
    re.compile(r"(\d{4}-\d{2}-\d{2})"),  # e.g. 2024-05-13
    re.compile(r"(\d{8})"),  # e.g. 20241022
    re.compile(r"v(\d+\.\d+(\.\d+)?)"),  # e.g. v1.5, v0.2
    re.compile(r":(latest|turbo|mini|preview|exp)"),
]

_QUANT_PATTERNS = [
    re.compile(r"q[0-9]_[kK]_[mMsSlL]", re.IGNORECASE),
    re.compile(r"q[0-9]_[0-9]", re.IGNORECASE),
    re.compile(r"fp16|fp32|bf16|int8|int4", re.IGNORECASE),
]

_SIZE_PATTERNS = [
    re.compile(r"([0-9]+[bB])"),  # e.g. 8b, 70b, 405b
]


def normalize_model_id(
    raw_model_id: str, default_vendor: str = "generic"
) -> NormalizedModelInfo:
    """Normalizes raw model ID into structured info with deterministic equivalence fingerprint."""
    if not raw_model_id:
        raw_model_id = "unknown-model"

    clean_id = raw_model_id.strip()

    # Strip vendor prefixes if present (e.g. "openai/gpt-4o", "meta-llama/llama-3.1-8b")
    parts = clean_id.split("/")
    vendor = default_vendor
    if len(parts) >= 2:
        vendor_candidate = parts[0].lower()
        if vendor_candidate in (
            "openai",
            "anthropic",
            "google",
            "meta-llama",
            "mistralai",
            "openrouter",
            "ollama",
            "nvidia",
        ):
            vendor = vendor_candidate
            clean_id = "/".join(parts[1:])

    # Extract revision
    revision = None
    for pat in _REVISION_PATTERNS:
        match = pat.search(clean_id)
        if match:
            revision = match.group(1)
            break

    # Extract quantization
    quantization = None
    for pat in _QUANT_PATTERNS:
        match = pat.search(clean_id)
        if match:
            quantization = match.group(0).lower()
            break

    # Extract parameter size
    param_size = None
    for pat in _SIZE_PATTERNS:
        match = pat.search(clean_id)
        if match:
            param_size = match.group(1).lower()
            break

    # Determine base family
    family_clean = clean_id.lower()
    for s in [revision, quantization, param_size]:
        if s and s in family_clean:
            family_clean = family_clean.replace(s, "")
    family_clean = re.sub(r"[:\-_]+", "-", family_clean).strip("-")
    if not family_clean:
        family_clean = clean_id.lower()

    canonical_name = f"{family_clean}"
    if param_size:
        canonical_name += f"-{param_size}"
    if revision:
        canonical_name += f"-{revision}"

    fingerprint = f"{vendor}:{family_clean}:{param_size or 'base'}:{revision or 'floating'}:{quantization or 'standard'}"

    return NormalizedModelInfo(
        raw_model_id=raw_model_id,
        vendor=vendor,
        family=family_clean,
        revision=revision,
        quantization=quantization,
        parameter_size=param_size,
        canonical_name=canonical_name,
        equivalence_fingerprint=fingerprint,
    )
