"""Application service for the namespaced durable V3 resource authority.

Phase 4: V3 routers must not own or mutate domain collections. They delegate
to this application service, which depends only on the core port
(``V3ResourceRepositoryPort``) and a Unit-of-Work factory. The concrete SQL
repository is injected by the composition root.

The service owns the transaction boundary so that writes, idempotency lookup,
and optimistic concurrency share one UoW transaction.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from windagent_core.contracts.repositories.unit_of_work import UnitOfWorkPort
from windagent_core.contracts.repositories.v3_resource_repository import (
    V3ResourceRepositoryPort,
)


class V3ResourceService:
    """Transactional application service over a namespaced V3 resource store."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWorkPort],
        repository_factory: Callable[[Any], V3ResourceRepositoryPort],
    ) -> None:
        self._uow_factory = uow_factory
        self._repository_factory = repository_factory

    async def get(self, namespace: str, resource_id: str) -> Optional[Dict[str, Any]]:
        async with self._uow_factory() as uow:
            repo = self._repository_factory(uow.session)
            return await repo.get(namespace, resource_id)

    async def list(self, namespace: str) -> List[Dict[str, Any]]:
        async with self._uow_factory() as uow:
            repo = self._repository_factory(uow.session)
            return await repo.list(namespace)

    async def create(
        self,
        namespace: str,
        resource_id: str,
        data: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        async with self._uow_factory() as uow:
            repo = self._repository_factory(uow.session)
            result = await repo.create(namespace, resource_id, data, idempotency_key)
            await uow.commit()
            return result

    async def update(
        self,
        namespace: str,
        resource_id: str,
        data: Dict[str, Any],
        expected_version: int,
    ) -> Optional[Dict[str, Any]]:
        async with self._uow_factory() as uow:
            repo = self._repository_factory(uow.session)
            result = await repo.update(namespace, resource_id, data, expected_version)
            if result is not None:
                await uow.commit()
            return result

    async def delete(self, namespace: str, resource_id: str) -> bool:
        async with self._uow_factory() as uow:
            repo = self._repository_factory(uow.session)
            result = await repo.delete(namespace, resource_id)
            await uow.commit()
            return result

    async def find_by_idempotency(
        self, namespace: str, idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        async with self._uow_factory() as uow:
            repo = self._repository_factory(uow.session)
            return await repo.find_by_idempotency(namespace, idempotency_key)


__all__ = ["V3ResourceService"]
