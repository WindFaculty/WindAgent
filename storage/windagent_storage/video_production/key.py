"""
Content-addressed artifact key (plan 05 §13, gate VP18_ARTIFACT_INVALIDATION_VERIFIED).

The artifact key is:

    SHA256(canonical_input + prompt_version + reference_hashes + model
           + generation_mode + generation_parameters)

Canonicalization and the key algorithm are PINNED by `ARTIFACT_KEY_VERSION`.
Changing the algorithm, canonicalization, or the input set requires a NEW key
version; old keys are NEVER reinterpreted under the new version (§13).

The key is computed over intent/inputs — NOT over file bytes. Two runs that
produce byte-identical output from identical inputs share a key (reuse); any
input change yields a different key (no stale cache reuse). File bytes are
covered separately by the content SHA-256 in the artifact record.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Union

ARTIFACT_KEY_VERSION = "v1"


def _stable_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonicalize_input(canonical_input: Union[Dict[str, Any], List[Any]]) -> str:
    """Pinned canonical serialization of the canonical input set (§13).

    The canonical input is the versioned production inputs the artifact was
    generated from (locked screenplay text, shot plan intent, bibles, etc.).
    List order is PRESERVED (an ordered screenplay scene sequence is
    semantically meaningful — reordering scenes is a different input).
    Callers that want order-independent identity MUST pass a pre-sorted list
    (e.g. reference hash sets, which `compute_artifact_key` already sorts
    separately). This keeps the mapping injective: no two distinct inputs
    collapse to the same key.
    """
    if isinstance(canonical_input, list):
        return _stable_json([_canonical_atom(v) for v in canonical_input])
    if isinstance(canonical_input, dict):
        return _stable_json({k: _canonical_atom(v) for k, v in sorted(canonical_input.items())})
    return _stable_json(_canonical_atom(canonical_input))


def _canonical_atom(value: Any) -> Any:
    """Normalize scalar/container values into a stable form (order preserved)."""
    if isinstance(value, (list, tuple)):
        return [_canonical_atom(v) for v in value]
    if isinstance(value, dict):
        return {k: _canonical_atom(v) for k, v in sorted(value.items())}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def compute_artifact_key(
    *,
    canonical_input: Union[Dict[str, Any], List[Any]],
    prompt_version: str,
    reference_hashes: List[str],
    model: str,
    generation_mode: str,
    generation_parameters: Optional[Dict[str, Any]] = None,
    key_version: str = ARTIFACT_KEY_VERSION,
) -> str:
    """Compute the pinned-version content key (§13).

    The six components are encoded as ONE JSON array (not joined with a
    separator) so the encoding is injective — no two distinct component sets
    can produce the same seed regardless of `|` or any other characters in
    the inputs.

    Raises ValueError if the caller requests an unknown key version — an old
    key is never silently reinterpreted under a newer algorithm.
    """
    if key_version != ARTIFACT_KEY_VERSION:
        raise ValueError(
            f"Unknown artifact key version {key_version!r}; "
            f"current pinned version is {ARTIFACT_KEY_VERSION!r}. "
            f"Old keys are never reinterpreted under a new algorithm (§13)."
        )

    refs = _stable_json(sorted(reference_hashes))
    params = _stable_json(dict(generation_parameters or {}))
    seed = _stable_json(
        [
            canonicalize_input(canonical_input),
            _stable_json(str(prompt_version)),
            refs,
            _stable_json(str(model)),
            _stable_json(str(generation_mode)),
            params,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{key_version}:{digest}"


def key_matches(record_key: str, expected_key: str) -> bool:
    """Full-key match including the key-version prefix (§14.4 reuse rule 1)."""
    return record_key == expected_key


def key_version_of(record_key: str) -> Optional[str]:
    """Extract the pinned version prefix from a stored key (None if unparseable)."""
    if ":" in record_key:
        return record_key.split(":", 1)[0]
    return None


__all__ = [
    "ARTIFACT_KEY_VERSION",
    "canonicalize_input",
    "compute_artifact_key",
    "key_matches",
    "key_version_of",
]
