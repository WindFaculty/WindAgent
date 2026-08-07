"""
Credential guard for the Universal Asset Gateway (VP3D Phase 5).

Backlog item 6: no credential is ever stored in a request/artifact; receipts
only keep redacted secret references. The guard raises a typed
``SecretLeakError`` when a payload contains a secret VALUE (detected by core
text redaction patterns) — fail closed BEFORE the payload is accepted or
persisted. Secret REFERENCES (e.g. ``env:WINDAGENT_MESH_API_KEY``) are not
credential values and pass the guard; the transport resolves them at call
time.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from windagent_core.domain.video_production.asset_resolution import SecretLeakError
from windagent_core.security.redaction import redact_before_persist, redact_text

Payload = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


def assert_no_credentials(
    payload: Dict[str, Any], *, context: str = "payload"
) -> None:
    """Raise SecretLeakError if ``payload`` contains a credential VALUE.

    Values that core ``redact_text`` would mask are credentials (raw API keys,
    bearer tokens, ...). Secret references such as ``env:VAR`` are unchanged by
    redaction and therefore allowed.
    """
    _walk_assert(payload, context=context)


def _walk_assert(payload: Payload, *, context: str) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            _walk_assert(value, context=f"{context}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _walk_assert(value, context=f"{context}[{index}]")
    elif isinstance(payload, str) and payload:
        if redact_text(payload) != payload:
            raise SecretLeakError(
                f"Credential-like value leaked into {context}; refusing payload.",
                details={"context": context},
            )


def redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the redacted copy for receipts/logs (never the raw value)."""
    return redact_before_persist(payload)


__all__ = ["assert_no_credentials", "redact_payload"]
