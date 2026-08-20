"""Core port for the namespaced durable V3 resource repository (Phase 4).

Phase 4 migrates every canonical mutable V3 router authority (projects,
episodes, tasks, workflows, providers, models, routing, assets, reviews,
world, storyboard, characters, production, agent definitions/instances,
conversations) from module-level RAM stores to a durable SQL authority.

Where no domain-specific durable model already exists, a namespaced durable
V3 resource repository is the single authority. It is a real SQL authority
with:

- an explicit core port (this module),
- an application service (``windagent_api.services.v3_resource_service``),
- a SQL adapter (``windagent_storage.repositories.v3_resource_repository``),
- optimistic version semantics (``expected_version`` compare-and-swap),
- durable idempotency records (``Idempotency-Key`` header).

Each router uses a distinct ``namespace`` so the same repository backs many
aggregates without creating a second authority for any existing aggregate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class V3ResourceRepositoryPort(Protocol):
    """Durable, namespaced, versioned resource store used by V3 routers.

    All methods stage work on the caller's transaction boundary (Unit of
    Work). The caller owns commit/rollback so that writes, idempotency
    lookup, and optimistic concurrency share one transaction.
    """

    async def get(self, namespace: str, resource_id: str) -> Optional[Dict[str, Any]]:
        """Return the stored resource dict (including ``version``) or None."""

    async def list(self, namespace: str) -> List[Dict[str, Any]]:
        """Return all resources in a namespace (newest first)."""

    async def create(
        self,
        namespace: str,
        resource_id: str,
        data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a new resource at version 1.

        If ``idempotency_key`` is supplied and a prior record exists for that
        key in this namespace, return the existing resource instead of
        inserting a duplicate.
        """

    async def update(
        self,
        namespace: str,
        resource_id: str,
        data: Dict[str, Any],
        expected_version: int,
    ) -> Optional[Dict[str, Any]]:
        """Compare-and-swap update guarded by ``expected_version``.

        Returns the updated resource on success, or ``None`` when the
        resource does not exist or the version does not match (caller maps
        to 404/409).
        """

    async def delete(self, namespace: str, resource_id: str) -> bool:
        """Delete a resource. Returns True if it existed."""

    async def find_by_idempotency(
        self, namespace: str, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        """Return the resource previously created under an idempotency key."""


__all__ = ["V3ResourceRepositoryPort"]
