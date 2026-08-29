from __future__ import annotations
from typing import Any, Dict, Optional
from windagent_core.errors.exceptions import PermissionDeniedError
from .types import HOST_AUTHORITY_FORBIDDEN_KEYS
def _contains_forbidden(d: Dict[str, Any]) -> Optional[str]:
    for k, v in d.items():
        lk = k.lower()
        if lk in HOST_AUTHORITY_FORBIDDEN_KEYS:
            return k
        if isinstance(v, dict):
            nested = _contains_forbidden(v)
            if nested:
                return f"{k}.{nested}"
    return None
def assert_host_authority_isolation(*, metadata: Optional[Dict[str, Any]] = None, parameters: Optional[Dict[str, Any]] = None, code: Optional[str] = None) -> None:
    for label, payload in (("metadata", metadata), ("parameters", parameters)):
        if not payload:
            continue
        bad = _contains_forbidden(payload)
        if bad:
            raise PermissionDeniedError(message=f"Runtime substrate must not carry host authority field: {bad}", details={"field": bad, "label": label})
