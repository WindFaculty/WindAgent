"""Model-ID normalization and equivalence classification.

EXTRACT_LOGIC of the frozen ``core/windagent_core/contracts/providers/``
``model_normalizer.py`` and ``equivalence.py``.  The algorithm is preserved
verbatim (parity oracle): vendor prefix extraction, revision/quantization/
size parsing, the canonical-name construction, and the
``vendor:family:size:revision:quantization`` equivalence fingerprint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple

_VENDOR_PREFIXES: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "google",
        "meta-llama",
        "mistralai",
        "openrouter",
        "ollama",
        "nvidia",
    }
)

_REVISION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
    re.compile(r"(\d{8})"),
    re.compile(r"v(\d+\.\d+(\.\d+)?)"),
    re.compile(r":(latest|turbo|mini|preview|exp)"),
)

_QUANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"q[0-9]_[kK]_[mMsSlL]", re.IGNORECASE),
    re.compile(r"q[0-9]_[0-9]", re.IGNORECASE),
    re.compile(r"fp16|fp32|bf16|int8|int4", re.IGNORECASE),
)

_SIZE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"([0-9]+[bB])"),
)


@dataclass(frozen=True, slots=True)
class NormalizedModelInfo:
    """Structured decomposition of one raw provider model identifier."""

    raw_model_id: str
    vendor: str
    family: str
    revision: str | None
    quantization: str | None
    parameter_size: str | None
    canonical_name: str
    equivalence_fingerprint: str


def normalize_model_id(
    raw_model_id: str, default_vendor: str = "generic"
) -> NormalizedModelInfo:
    """Normalize a raw model ID into structured info with a stable fingerprint."""
    effective_raw = raw_model_id if raw_model_id else "unknown-model"
    clean_id = effective_raw.strip()

    parts = clean_id.split("/")
    vendor = default_vendor
    if len(parts) >= 2 and parts[0].lower() in _VENDOR_PREFIXES:
        vendor = parts[0].lower()
        clean_id = "/".join(parts[1:])

    revision: str | None = None
    for pattern in _REVISION_PATTERNS:
        match = pattern.search(clean_id)
        if match:
            revision = match.group(1)
            break

    quantization: str | None = None
    for pattern in _QUANT_PATTERNS:
        match = pattern.search(clean_id)
        if match:
            quantization = match.group(0).lower()
            break

    parameter_size: str | None = None
    for pattern in _SIZE_PATTERNS:
        match = pattern.search(clean_id)
        if match:
            parameter_size = match.group(1).lower()
            break

    family_clean = clean_id.lower()
    for fragment in (revision, quantization, parameter_size):
        if fragment and fragment in family_clean:
            family_clean = family_clean.replace(fragment, "")
    family_clean = re.sub(r"[:\-_]+", "-", family_clean).strip("-")
    if not family_clean:
        family_clean = clean_id.lower()

    canonical_name = family_clean
    if parameter_size:
        canonical_name += f"-{parameter_size}"
    if revision:
        canonical_name += f"-{revision}"

    fingerprint = (
        f"{vendor}:{family_clean}:{parameter_size or 'base'}:"
        f"{revision or 'floating'}:{quantization or 'standard'}"
    )

    return NormalizedModelInfo(
        raw_model_id=effective_raw,
        vendor=vendor,
        family=family_clean,
        revision=revision,
        quantization=quantization,
        parameter_size=parameter_size,
        canonical_name=canonical_name,
        equivalence_fingerprint=fingerprint,
    )


class EquivalenceLevel(StrEnum):
    """How closely two normalized models may substitute for each other."""

    EXACT_REVISION = "exact_revision"
    EXACT_FAMILY_FLOATING_REVISION = "exact_family_floating_revision"
    COMPATIBLE_ALIAS = "compatible_alias"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class EquivalenceAssessment(NamedTuple):
    """The classification outcome, including failover eligibility."""

    level: EquivalenceLevel
    confidence: float
    reason: str
    is_failover_eligible: bool


def classify_equivalence(
    model_a: NormalizedModelInfo, model_b: NormalizedModelInfo
) -> EquivalenceAssessment:
    """Classify equivalence between two normalized model definitions.

    Preserved rules: identical fingerprints are exact and failover-eligible;
    same-family quantization or revision drift is close but explicitly NOT
    failover-eligible; a cross-vendor raw-ID match after stripping the
    ``openai/`` and ``openrouter/`` prefixes is exact.
    """
    if model_a.equivalence_fingerprint == model_b.equivalence_fingerprint:
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_REVISION,
            confidence=1.0,
            reason="Fingerprint, revision, and quantization match exactly",
            is_failover_eligible=True,
        )

    if (
        model_a.family == model_b.family
        and model_a.revision == model_b.revision
        and model_a.quantization != model_b.quantization
    ):
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION,
            confidence=0.85,
            reason=(
                f"Quantization differs ({model_a.quantization} vs {model_b.quantization})"
            ),
            is_failover_eligible=False,
        )

    if model_a.family == model_b.family and model_a.revision != model_b.revision:
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_FAMILY_FLOATING_REVISION,
            confidence=0.80,
            reason=f"Model revisions differ ({model_a.revision} vs {model_b.revision})",
            is_failover_eligible=False,
        )

    a_clean = model_a.raw_model_id.replace("openai/", "").replace("openrouter/", "")
    b_clean = model_b.raw_model_id.replace("openai/", "").replace("openrouter/", "")
    if a_clean == b_clean:
        return EquivalenceAssessment(
            level=EquivalenceLevel.EXACT_REVISION,
            confidence=1.0,
            reason="Cross-vendor exact model ID match",
            is_failover_eligible=True,
        )

    return EquivalenceAssessment(
        level=EquivalenceLevel.UNKNOWN,
        confidence=0.0,
        reason="Model families or parameters do not align",
        is_failover_eligible=False,
    )
