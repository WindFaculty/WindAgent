"""
Idempotency Key validation, storage, and replay mechanics for V3 mutations.
"""

from __future__ import annotations
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field
from windagent_api.routers.v3.common.problems import ApiProblemException


class IdempotencyRecord(BaseModel):
    key: str
    route: str
    request_fingerprint: str
    response_status: int
    response_body: Dict[str, Any]
    created_at: float = Field(default_factory=time.time)
    expires_at: float


class IdempotencyConflictError(ApiProblemException):
    """Raised when an existing idempotency key is reused with a different request payload."""
    def __init__(self, key: str):
        super().__init__(
            status_code=409,
            title="Idempotency Conflict",
            detail=f"Idempotency key '{key}' was previously used with different request parameters.",
            code="IDEMPOTENCY_CONFLICT",
            type_uri="https://windagent.dev/problems/idempotency-conflict",
            retryable=False,
            details={"idempotency_key": key}
        )


class IdempotencyStore:
    """In-memory idempotency cache with TTL expiration (expandable to Redis/Database)."""
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, IdempotencyRecord] = {}

    def _compute_fingerprint(self, body: Any) -> str:
        if body is None:
            return "empty"
        if isinstance(body, (dict, list)):
            dumped = json.dumps(body, sort_keys=True)
        else:
            dumped = str(body)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

    def check(self, key: str, route: str, body: Any) -> Optional[Tuple[int, Dict[str, Any]]]:
        """
        Check if key exists:
        - If not exists or expired: returns None (proceed with execution).
        - If exists with same fingerprint: returns cached (status_code, body).
        - If exists with different fingerprint: raises IdempotencyConflictError.
        """
        now = time.time()
        record = self._store.get(key)
        if not record:
            return None

        if record.expires_at < now:
            del self._store[key]
            return None

        current_fp = self._compute_fingerprint(body)
        if record.request_fingerprint != current_fp or record.route != route:
            raise IdempotencyConflictError(key)

        return record.response_status, record.response_body

    def save(self, key: str, route: str, body: Any, response_status: int, response_body: Dict[str, Any]) -> None:
        now = time.time()
        fp = self._compute_fingerprint(body)
        self._store[key] = IdempotencyRecord(
            key=key,
            route=route,
            request_fingerprint=fp,
            response_status=response_status,
            response_body=response_body,
            created_at=now,
            expires_at=now + self.ttl_seconds
        )


GLOBAL_IDEMPOTENCY_STORE = IdempotencyStore()
