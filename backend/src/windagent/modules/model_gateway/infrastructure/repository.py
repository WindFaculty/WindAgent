"""SQL adapter for the model gateway store and transaction scope.

The store joins the caller's transaction scope exactly like every other
platform repository; the scope records outbox events atomically with the
domain writes via the platform ``TransactionalOutbox``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windagent.kernel.events import EventEnvelope
from windagent.kernel.time import normalize_utc
from windagent.platform.events.outbox import TransactionalOutbox
from windagent.platform.persistence.database import Database
from windagent.platform.persistence.unit_of_work import SqlUnitOfWork

from ..application.models import (
    AttemptRow,
    BindingRow,
    CanonicalModelRow,
    CredentialRow,
    EndpointRow,
    ProviderRow,
    QuotaStateRecord,
    ReceiptRow,
    RuleRow,
    SelectableBinding,
)
from ..application.ports import ModelGatewayStore
from ..domain.circuit import EndpointRuntimeState
from ..domain.route_lock import LockStatus, RouteLockRecord, RoutingSnapshot
from .tables import (
    attempts_table,
    bindings_table,
    canonical_models_table,
    credentials_table,
    endpoint_state_table,
    endpoints_table,
    providers_table,
    quota_state_table,
    receipts_table,
    route_locks_table,
    routing_rules_table,
)

STORE_REPOSITORY_NAME = "model_gateway_store"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _load_list(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        parsed = json.loads(raw)
    except ValueError:
        return ()
    return tuple(str(item) for item in parsed) if isinstance(parsed, list) else ()


def _dump_list(values: tuple[str, ...]) -> str:
    return json.dumps(list(values))


def make_store(session: AsyncSession) -> SqlModelGatewayStore:
    """Session-bound repository factory for ``uow.register_repository``."""
    return SqlModelGatewayStore(session)


class SqlModelGatewayStore(ModelGatewayStore):
    """Durable store bound to one session; never commits on its own."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Providers
    # ------------------------------------------------------------------ #

    async def insert_provider(
        self, row: ProviderRow, endpoint: EndpointRow | None
    ) -> bool:
        existing = await self._session.execute(
            select(providers_table.c.id).where(providers_table.c.name == row.name)
        )
        if existing.first() is not None:
            return False
        await self._session.execute(insert(providers_table).values(_provider_values(row)))
        if endpoint is not None:
            await self._session.execute(
                insert(endpoints_table).values(_endpoint_values(endpoint))
            )
        return True

    async def get_provider(self, provider_id: str) -> ProviderRow | None:
        row = (
            await self._session.execute(
                select(providers_table).where(providers_table.c.id == provider_id)
            )
        ).first()
        return _provider_from_row(row) if row else None

    async def get_provider_by_name(self, name: str) -> ProviderRow | None:
        row = (
            await self._session.execute(
                select(providers_table).where(providers_table.c.name == name)
            )
        ).first()
        return _provider_from_row(row) if row else None

    async def list_providers(self) -> tuple[ProviderRow, ...]:
        rows = (
            await self._session.execute(select(providers_table).order_by(providers_table.c.name))
        ).all()
        return tuple(_provider_from_row(row) for row in rows)

    async def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        protocol_mode: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderRow | None:
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if display_name is not None:
            values["display_name"] = display_name
        if base_url is not None:
            values["base_url"] = base_url
        if protocol_mode is not None:
            values["protocol_mode"] = protocol_mode
        if enabled is not None:
            values["enabled"] = enabled
        await self._session.execute(
            update(providers_table).where(providers_table.c.id == provider_id).values(**values)
        )
        return await self.get_provider(provider_id)

    async def delete_provider(self, provider_id: str) -> bool:
        provider = await self.get_provider(provider_id)
        if provider is None:
            return False
        await self._session.execute(
            delete(endpoints_table).where(endpoints_table.c.provider_id == provider_id)
        )
        await self._session.execute(
            delete(credentials_table).where(credentials_table.c.provider_id == provider_id)
        )
        await self._session.execute(
            delete(providers_table).where(providers_table.c.id == provider_id)
        )
        return True

    # ------------------------------------------------------------------ #
    # Endpoints
    # ------------------------------------------------------------------ #

    async def insert_endpoint(self, row: EndpointRow) -> bool:
        provider = await self.get_provider(row.provider_id)
        if provider is None:
            return False
        await self._session.execute(insert(endpoints_table).values(_endpoint_values(row)))
        return True

    async def get_endpoint(self, endpoint_id: str) -> EndpointRow | None:
        row = (
            await self._session.execute(
                select(endpoints_table).where(endpoints_table.c.id == endpoint_id)
            )
        ).first()
        return _endpoint_from_row(row) if row else None

    async def list_endpoints_for_provider(self, provider_id: str) -> tuple[EndpointRow, ...]:
        rows = (
            await self._session.execute(
                select(endpoints_table)
                .where(endpoints_table.c.provider_id == provider_id)
                .order_by(endpoints_table.c.priority.asc())
            )
        ).all()
        return tuple(_endpoint_from_row(row) for row in rows)

    async def update_endpoint_status(self, endpoint_id: str, test_status: str) -> bool:
        outcome = await self._session.execute(
            update(endpoints_table)
            .where(endpoints_table.c.id == endpoint_id)
            .values(test_status=test_status, updated_at=datetime.now(UTC))
        )
        return bool(cast('CursorResult[Any]', outcome).rowcount)

    # ------------------------------------------------------------------ #
    # Credentials
    # ------------------------------------------------------------------ #

    async def insert_credential(self, row: CredentialRow) -> bool:
        provider = await self.get_provider(row.provider_id)
        if provider is None:
            return False
        await self._session.execute(
            insert(credentials_table).values(
                {
                    "id": row.id,
                    "provider_id": row.provider_id,
                    "secret_name": row.secret_name,
                    "secret_version": row.secret_version,
                    "label": row.label,
                    "created_at": _as_utc(row.created_at),
                    "revoked_at": _as_utc(row.revoked_at),
                }
            )
        )
        return True

    async def active_credential_for_provider(self, provider_id: str) -> CredentialRow | None:
        row = (
            await self._session.execute(
                select(credentials_table)
                .where(
                    credentials_table.c.provider_id == provider_id,
                    credentials_table.c.revoked_at.is_(None),
                )
                .order_by(
                    credentials_table.c.created_at.desc(), credentials_table.c.id.desc()
                )
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        return CredentialRow(
            id=row.id,
            provider_id=row.provider_id,
            secret_name=row.secret_name,
            secret_version=int(row.secret_version),
            label=row.label,
            created_at=_as_utc(row.created_at),
            revoked_at=_as_utc(row.revoked_at),
        )

    async def revoke_active_credentials(
        self, provider_id: str, *, when: datetime
    ) -> int:
        outcome = await self._session.execute(
            update(credentials_table)
            .where(
                credentials_table.c.provider_id == provider_id,
                credentials_table.c.revoked_at.is_(None),
            )
            .values(revoked_at=normalize_utc(when))
        )
        return int(cast('CursorResult[Any]', outcome).rowcount or 0)

    # ------------------------------------------------------------------ #
    # Canonical models and bindings
    # ------------------------------------------------------------------ #

    async def upsert_model(self, row: CanonicalModelRow) -> bool:
        existing = (
            await self._session.execute(
                select(canonical_models_table).where(
                    canonical_models_table.c.canonical_name == row.canonical_name
                )
            )
        ).first()
        if existing is None:
            await self._session.execute(
                insert(canonical_models_table).values(
                    {
                        "canonical_name": row.canonical_name,
                        "vendor": row.vendor,
                        "family": row.family,
                        "revision": row.revision,
                        "quantization": row.quantization,
                        "parameter_size": row.parameter_size,
                        "equivalence_fingerprint": row.equivalence_fingerprint,
                        "context_window": row.context_window,
                        "capabilities_json": _dump_list(row.capabilities),
                        "enabled": row.enabled,
                        "created_at": _as_utc(row.created_at),
                        "updated_at": _as_utc(row.updated_at),
                    }
                )
            )
            return True
        await self._session.execute(
            update(canonical_models_table)
            .where(canonical_models_table.c.canonical_name == row.canonical_name)
            .values(
                vendor=row.vendor,
                family=row.family,
                revision=row.revision,
                quantization=row.quantization,
                parameter_size=row.parameter_size,
                equivalence_fingerprint=row.equivalence_fingerprint,
                context_window=row.context_window,
                updated_at=_as_utc(row.updated_at),
            )
        )
        return False

    async def get_model(self, canonical_name: str) -> CanonicalModelRow | None:
        row = (
            await self._session.execute(
                select(canonical_models_table).where(
                    canonical_models_table.c.canonical_name == canonical_name
                )
            )
        ).first()
        return _model_from_row(row) if row else None

    async def list_models(self) -> tuple[CanonicalModelRow, ...]:
        rows = (
            await self._session.execute(
                select(canonical_models_table).order_by(canonical_models_table.c.canonical_name)
            )
        ).all()
        return tuple(_model_from_row(row) for row in rows)

    async def upsert_binding(self, row: BindingRow) -> str:
        existing = (
            await self._session.execute(
                select(bindings_table).where(
                    bindings_table.c.endpoint_id == row.endpoint_id,
                    bindings_table.c.canonical_model_id == row.canonical_model_id,
                )
            )
        ).first()
        if existing is None:
            await self._session.execute(
                insert(bindings_table).values(
                    {
                        "id": row.id,
                        "endpoint_id": row.endpoint_id,
                        "canonical_model_id": row.canonical_model_id,
                        "provider_model_id": row.provider_model_id,
                        "equivalence_level": row.equivalence_level,
                        "equivalence_fingerprint": row.equivalence_fingerprint,
                        "pricing_class": row.pricing_class,
                        "priority": row.priority,
                        "availability": row.availability,
                        "is_active": row.is_active,
                        "last_discovered_at": _as_utc(row.last_discovered_at),
                    }
                )
            )
            return "added"
        changed = (
            existing.provider_model_id != row.provider_model_id
            or existing.equivalence_fingerprint != row.equivalence_fingerprint
            or existing.availability != "active"
            or not bool(existing.is_active)
        )
        await self._session.execute(
            update(bindings_table)
            .where(bindings_table.c.id == existing.id)
            .values(
                provider_model_id=row.provider_model_id,
                equivalence_fingerprint=row.equivalence_fingerprint,
                availability="active",
                is_active=True,
                last_discovered_at=_as_utc(row.last_discovered_at),
            )
        )
        return "updated" if changed else "unchanged"

    async def list_bindings(
        self, *, canonical_model_id: str | None = None
    ) -> tuple[BindingRow, ...]:
        statement = select(bindings_table)
        if canonical_model_id is not None:
            statement = statement.where(
                bindings_table.c.canonical_model_id == canonical_model_id
            )
        rows = (await self._session.execute(statement)).all()
        return tuple(_binding_from_row(row) for row in rows)

    async def mark_unavailable_bindings(
        self, endpoint_id: str, keep_provider_model_ids: frozenset[str], *, when: datetime
    ) -> tuple[str, ...]:
        rows = (
            await self._session.execute(
                select(bindings_table).where(
                    bindings_table.c.endpoint_id == endpoint_id,
                    bindings_table.c.availability != "unavailable",
                )
            )
        ).all()
        marked: list[str] = []
        for row in rows:
            if row.provider_model_id in keep_provider_model_ids:
                continue
            await self._session.execute(
                update(bindings_table)
                .where(bindings_table.c.id == row.id)
                .values(availability="unavailable", is_active=False)
            )
            marked.append(str(row.provider_model_id))
        return tuple(marked)

    async def list_selectable_bindings(
        self, canonical_model_id: str
    ) -> tuple[SelectableBinding, ...]:
        binding_rows = (
            await self._session.execute(
                select(bindings_table).where(
                    bindings_table.c.canonical_model_id == canonical_model_id,
                    bindings_table.c.is_active.is_(True),
                )
            )
        ).all()
        results: list[SelectableBinding] = []
        for binding in binding_rows:
            endpoint_row = (
                await self._session.execute(
                    select(endpoints_table).where(endpoints_table.c.id == binding.endpoint_id)
                )
            ).first()
            if endpoint_row is None:
                continue
            provider_row = (
                await self._session.execute(
                    select(providers_table).where(
                        providers_table.c.id == endpoint_row.provider_id
                    )
                )
            ).first()
            if provider_row is None:
                continue
            credential_row = (
                await self._session.execute(
                    select(credentials_table)
                    .where(
                        credentials_table.c.provider_id == provider_row.id,
                        credentials_table.c.revoked_at.is_(None),
                    )
                    .limit(1)
                )
            ).first()
            results.append(
                SelectableBinding(
                    binding_id=str(binding.id),
                    endpoint_id=str(endpoint_row.id),
                    provider_name=str(provider_row.name),
                    provider_id=str(provider_row.id),
                    provider_model_id=str(binding.provider_model_id),
                    base_url=str(endpoint_row.base_url),
                    protocol_mode=str(endpoint_row.protocol_mode),
                    equivalence_level=str(binding.equivalence_level),
                    endpoint_enabled=bool(endpoint_row.enabled),
                    binding_enabled=bool(binding.is_active),
                    has_credential=credential_row is not None,
                    credential_secret_name=(
                        str(credential_row.secret_name) if credential_row else None
                    ),
                )
            )
        return tuple(results)

    async def count_provider_models(self, provider_id: str) -> int:
        endpoint_ids = list(
            (
                await self._session.execute(
                    select(endpoints_table.c.id).where(
                        endpoints_table.c.provider_id == provider_id
                    )
                )
            ).scalars()
        )
        if not endpoint_ids:
            return 0
        rows = (
            await self._session.execute(
                select(bindings_table.c.canonical_model_id).where(
                    bindings_table.c.endpoint_id.in_(endpoint_ids),
                    bindings_table.c.is_active.is_(True),
                )
            )
        ).all()
        return len({row[0] for row in rows})

    async def canonical_models_for_provider(self, provider_id: str) -> tuple[str, ...]:
        endpoint_ids = list(
            (
                await self._session.execute(
                    select(endpoints_table.c.id).where(
                        endpoints_table.c.provider_id == provider_id
                    )
                )
            ).scalars()
        )
        if not endpoint_ids:
            return ()
        rows = (
            await self._session.execute(
                select(bindings_table.c.canonical_model_id).where(
                    bindings_table.c.endpoint_id.in_(endpoint_ids),
                    bindings_table.c.is_active.is_(True),
                )
            )
        ).all()
        return tuple({str(row[0]) for row in rows})

    # ------------------------------------------------------------------ #
    # Routing rules
    # ------------------------------------------------------------------ #

    async def upsert_rule(self, row: RuleRow) -> RuleRow:
        existing = (
            await self._session.execute(
                select(routing_rules_table).where(
                    routing_rules_table.c.rule_id == row.rule_id
                )
            )
        ).first()
        values = _rule_values(row)
        if existing is None:
            await self._session.execute(insert(routing_rules_table).values(values))
        else:
            await self._session.execute(
                update(routing_rules_table)
                .where(routing_rules_table.c.rule_id == row.rule_id)
                .values(**values)
            )
        return row

    async def get_rule(self, rule_id: str) -> RuleRow | None:
        row = (
            await self._session.execute(
                select(routing_rules_table).where(routing_rules_table.c.rule_id == rule_id)
            )
        ).first()
        return _rule_from_row(row) if row else None

    async def list_rules(self) -> tuple[RuleRow, ...]:
        rows = (
            await self._session.execute(
                select(routing_rules_table).order_by(routing_rules_table.c.priority.asc())
            )
        ).all()
        return tuple(_rule_from_row(row) for row in rows)

    async def delete_rule(self, rule_id: str) -> bool:
        outcome = await self._session.execute(
            delete(routing_rules_table).where(routing_rules_table.c.rule_id == rule_id)
        )
        return bool(cast('CursorResult[Any]', outcome).rowcount)

    async def rule_ids_referencing_models(
        self, canonical_models: frozenset[str]
    ) -> tuple[str, ...]:
        if not canonical_models:
            return ()
        rows = (
            await self._session.execute(
                select(routing_rules_table.c.rule_id).where(
                    routing_rules_table.c.enabled.is_(True),
                    routing_rules_table.c.canonical_model_id.in_(list(canonical_models)),
                )
            )
        ).all()
        return tuple(str(row[0]) for row in rows)

    async def disable_rules(self, rule_ids: tuple[str, ...], *, when: datetime) -> int:
        if not rule_ids:
            return 0
        outcome = await self._session.execute(
            update(routing_rules_table)
            .where(routing_rules_table.c.rule_id.in_(list(rule_ids)))
            .values(enabled=False, updated_at=normalize_utc(when))
        )
        return int(cast('CursorResult[Any]', outcome).rowcount or 0)

    # ------------------------------------------------------------------ #
    # Route locks
    # ------------------------------------------------------------------ #

    async def record_route_lock(self, lock: RouteLockRecord) -> bool:
        existing = (
            await self._session.execute(
                select(route_locks_table.c.lock_id).where(
                    route_locks_table.c.scope_type == lock.scope_type,
                    route_locks_table.c.scope_id == lock.scope_id,
                    route_locks_table.c.status == LockStatus.ACTIVE.value,
                )
            )
        ).first()
        if existing is not None:
            return False
        try:
            # The partial unique index is the cross-process CAS backstop;
            # a savepoint keeps a lost race from poisoning the transaction.
            async with self._session.begin_nested():
                await self._session.execute(
                    insert(route_locks_table).values(
                        {
                            "lock_id": lock.lock_id,
                            "scope_type": lock.scope_type,
                            "scope_id": lock.scope_id,
                            "canonical_model_id": lock.canonical_model_id,
                            "rule_id": lock.routing_snapshot.rule_id,
                            "rule_version": lock.routing_snapshot.rule_version,
                            "snapshot_json": json.dumps(
                                lock.routing_snapshot.to_dict()
                            ),
                            "status": lock.status,
                            "reselection_count": lock.reselection_count,
                            "is_fallback": lock.is_fallback,
                            "source_lock_id": lock.source_lock_id,
                            "created_at": datetime.now(UTC),
                        }
                    )
                )
        except IntegrityError:
            return False
        return True

    async def get_route_lock(self, lock_id: str) -> RouteLockRecord | None:
        row = (
            await self._session.execute(
                select(route_locks_table).where(route_locks_table.c.lock_id == lock_id)
            )
        ).first()
        return _lock_from_row(row) if row else None

    async def get_active_route_lock(
        self, scope_type: str, scope_id: str
    ) -> RouteLockRecord | None:
        row = (
            await self._session.execute(
                select(route_locks_table).where(
                    route_locks_table.c.scope_type == scope_type,
                    route_locks_table.c.scope_id == scope_id,
                    route_locks_table.c.status == LockStatus.ACTIVE.value,
                )
            )
        ).first()
        return _lock_from_row(row) if row else None

    async def release_route_lock(self, lock_id: str, *, when: datetime) -> bool:
        outcome = await self._session.execute(
            update(route_locks_table)
            .where(
                route_locks_table.c.lock_id == lock_id,
                route_locks_table.c.status == LockStatus.ACTIVE.value,
            )
            .values(status=LockStatus.RELEASED.value, released_at=normalize_utc(when))
        )
        return bool(cast('CursorResult[Any]', outcome).rowcount)

    # ------------------------------------------------------------------ #
    # Endpoint runtime state and quota
    # ------------------------------------------------------------------ #

    async def get_endpoint_state(self, endpoint_id: str) -> EndpointRuntimeState:
        row = (
            await self._session.execute(
                select(endpoint_state_table).where(
                    endpoint_state_table.c.endpoint_id == endpoint_id
                )
            )
        ).first()
        if row is None:
            return EndpointRuntimeState()
        return EndpointRuntimeState(
            consecutive_failures=int(row.consecutive_failures),
            success_count=int(row.success_count),
            failure_count=int(row.failure_count),
            cooldown_until=_as_utc(row.cooldown_until),
            circuit_open_until=_as_utc(row.circuit_open_until),
            last_latency_ms=float(row.last_latency_ms),
            last_success_at=_as_utc(row.last_success_at),
            last_failure_at=_as_utc(row.last_failure_at),
            last_error_class=row.last_error_class,
        )

    async def save_endpoint_state(
        self, endpoint_id: str, state: EndpointRuntimeState
    ) -> None:
        values = {
            "consecutive_failures": state.consecutive_failures,
            "success_count": state.success_count,
            "failure_count": state.failure_count,
            "cooldown_until": _as_utc(state.cooldown_until),
            "circuit_open_until": _as_utc(state.circuit_open_until),
            "last_latency_ms": state.last_latency_ms,
            "last_success_at": _as_utc(state.last_success_at),
            "last_failure_at": _as_utc(state.last_failure_at),
            "last_error_class": state.last_error_class,
            "updated_at": datetime.now(UTC),
        }
        existing = (
            await self._session.execute(
                select(endpoint_state_table.c.endpoint_id).where(
                    endpoint_state_table.c.endpoint_id == endpoint_id
                )
            )
        ).first()
        if existing is None:
            await self._session.execute(
                insert(endpoint_state_table).values(endpoint_id=endpoint_id, **values)
            )
        else:
            await self._session.execute(
                update(endpoint_state_table)
                .where(endpoint_state_table.c.endpoint_id == endpoint_id)
                .values(**values)
            )

    async def get_quota_state(self, provider_name: str) -> QuotaStateRecord:
        row = (
            await self._session.execute(
                select(quota_state_table).where(
                    quota_state_table.c.provider_name == provider_name
                )
            )
        ).first()
        if row is None:
            # Optimistic default preserved from the old quota repository.
            return QuotaStateRecord(provider_name=provider_name, has_quota=True)
        return QuotaStateRecord(
            provider_name=str(row.provider_name),
            has_quota=bool(row.has_quota),
            remaining_requests_today=row.remaining_requests_today,
            remaining_tokens_today=row.remaining_tokens_today,
            reset_at=_as_utc(row.reset_at),
            updated_at=_as_utc(row.updated_at),
        )

    async def save_quota_state(self, state: QuotaStateRecord) -> None:
        values = {
            "has_quota": state.has_quota,
            "remaining_requests_today": state.remaining_requests_today,
            "remaining_tokens_today": state.remaining_tokens_today,
            "reset_at": _as_utc(state.reset_at),
            "updated_at": datetime.now(UTC),
        }
        existing = (
            await self._session.execute(
                select(quota_state_table.c.provider_name).where(
                    quota_state_table.c.provider_name == state.provider_name
                )
            )
        ).first()
        if existing is None:
            await self._session.execute(
                insert(quota_state_table).values(provider_name=state.provider_name, **values)
            )
        else:
            await self._session.execute(
                update(quota_state_table)
                .where(quota_state_table.c.provider_name == state.provider_name)
                .values(**values)
            )

    # ------------------------------------------------------------------ #
    # Attempts and receipts
    # ------------------------------------------------------------------ #

    async def insert_attempt(self, row: AttemptRow) -> None:
        await self._session.execute(
            insert(attempts_table).values(
                {
                    "id": row.id,
                    "route_lock_id": row.route_lock_id,
                    "endpoint_id": row.endpoint_id,
                    "binding_id": row.binding_id,
                    "attempt_index": row.attempt_index,
                    "status": row.status,
                    "error_class": row.error_class,
                    "http_status": row.http_status,
                    "started_at": _as_utc(row.started_at),
                    "finished_at": _as_utc(row.finished_at),
                    "prompt_tokens": row.prompt_tokens,
                    "completion_tokens": row.completion_tokens,
                    "latency_ms": row.latency_ms,
                }
            )
        )

    async def insert_receipt(self, row: ReceiptRow) -> None:
        await self._session.execute(
            insert(receipts_table).values(
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "role": row.role,
                    "route_lock_id": row.route_lock_id,
                    "rule_id": row.rule_id,
                    "rule_version": row.rule_version,
                    "provider_id": row.provider_id,
                    "canonical_model_id": row.canonical_model_id,
                    "provider_model_id": row.provider_model_id,
                    "endpoint_id": row.endpoint_id,
                    "fallback_used": row.fallback_used,
                    "fallback_reason": row.fallback_reason,
                    "status": row.status,
                    "error_code": row.error_code,
                    "started_at": _as_utc(row.started_at),
                    "completed_at": _as_utc(row.completed_at),
                    "created_at": _as_utc(row.created_at),
                }
            )
        )

    async def list_receipts(
        self, *, task_id: str | None, limit: int
    ) -> tuple[ReceiptRow, ...]:
        statement = select(receipts_table).order_by(receipts_table.c.created_at.desc())
        if task_id is not None:
            statement = statement.where(receipts_table.c.task_id == task_id)
        rows = (await self._session.execute(statement.limit(limit))).all()
        return tuple(
            ReceiptRow(
                id=str(row.id),
                task_id=str(row.task_id),
                role=row.role,
                route_lock_id=str(row.route_lock_id),
                rule_id=str(row.rule_id),
                rule_version=int(row.rule_version),
                provider_id=str(row.provider_id),
                canonical_model_id=str(row.canonical_model_id),
                provider_model_id=str(row.provider_model_id),
                endpoint_id=str(row.endpoint_id),
                fallback_used=bool(row.fallback_used),
                fallback_reason=row.fallback_reason,
                status=str(row.status),
                error_code=row.error_code,
                started_at=_as_utc(row.started_at),
                completed_at=_as_utc(row.completed_at),
                created_at=_as_utc(row.created_at),
            )
            for row in rows
        )


class SqlTransactionScope:
    """Durable scope backed by the platform unit-of-work + outbox."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._uow: SqlUnitOfWork | None = None

    async def __aenter__(self) -> SqlTransactionScope:
        uow = self._database.unit_of_work()
        if not isinstance(uow, SqlUnitOfWork):  # pragma: no cover - composition guard
            raise TypeError("transaction scope requires a SQL unit of work")
        uow.register_repository(STORE_REPOSITORY_NAME, make_store)
        self._uow = uow
        await uow.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if self._uow is not None:
            await self._uow.__aexit__(exc_type, exc_value, None)
            self._uow = None
        return False

    def store(self) -> ModelGatewayStore:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        return cast(ModelGatewayStore, self._uow.repository(STORE_REPOSITORY_NAME))

    async def record_event(
        self, envelope: EventEnvelope, *, deduplication_key: str | None = None
    ) -> bool:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        outbox = TransactionalOutbox(self._uow)
        return await outbox.record_next(envelope, deduplication_key=deduplication_key)

    async def commit(self) -> None:
        if self._uow is None:
            raise RuntimeError("transaction scope is not active")
        await self._uow.commit()


def sql_scope_factory(database: Database) -> Callable[[], SqlTransactionScope]:
    """The canonical scope factory handed to ``ModelGatewayServices``."""
    return lambda: SqlTransactionScope(database)


# --------------------------------------------------------------------------- #
# Row mappers
# --------------------------------------------------------------------------- #


def _provider_values(row: ProviderRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "display_name": row.display_name,
        "vendor_type": row.vendor_type,
        "base_url": row.base_url,
        "protocol_mode": row.protocol_mode,
        "supports_model_discovery": row.supports_model_discovery,
        "enabled": row.enabled,
        "created_at": _as_utc(row.created_at) or datetime.now(UTC),
        "updated_at": _as_utc(row.updated_at) or datetime.now(UTC),
    }


def _provider_from_row(row: Any) -> ProviderRow:
    return ProviderRow(
        id=str(row.id),
        name=str(row.name),
        display_name=str(row.display_name),
        vendor_type=str(row.vendor_type),
        base_url=str(row.base_url),
        protocol_mode=str(row.protocol_mode),
        supports_model_discovery=bool(row.supports_model_discovery),
        enabled=bool(row.enabled),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _endpoint_values(row: EndpointRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider_id": row.provider_id,
        "base_url": row.base_url,
        "protocol_mode": row.protocol_mode,
        "priority": row.priority,
        "weight": row.weight,
        "enabled": row.enabled,
        "test_status": row.test_status,
        "created_at": _as_utc(row.created_at) or datetime.now(UTC),
        "updated_at": _as_utc(row.updated_at) or datetime.now(UTC),
    }


def _endpoint_from_row(row: Any) -> EndpointRow:
    return EndpointRow(
        id=str(row.id),
        provider_id=str(row.provider_id),
        base_url=str(row.base_url),
        protocol_mode=str(row.protocol_mode),
        priority=int(row.priority),
        weight=int(row.weight),
        enabled=bool(row.enabled),
        test_status=str(row.test_status),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _model_from_row(row: Any) -> CanonicalModelRow:
    return CanonicalModelRow(
        canonical_name=str(row.canonical_name),
        vendor=str(row.vendor),
        family=str(row.family),
        revision=row.revision,
        quantization=row.quantization,
        parameter_size=row.parameter_size,
        equivalence_fingerprint=str(row.equivalence_fingerprint),
        context_window=row.context_window,
        capabilities=_load_list(row.capabilities_json),
        enabled=bool(row.enabled),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _binding_from_row(row: Any) -> BindingRow:
    return BindingRow(
        id=str(row.id),
        endpoint_id=str(row.endpoint_id),
        canonical_model_id=str(row.canonical_model_id),
        provider_model_id=str(row.provider_model_id),
        equivalence_level=str(row.equivalence_level),
        equivalence_fingerprint=str(row.equivalence_fingerprint),
        pricing_class=str(row.pricing_class),
        priority=int(row.priority),
        availability=str(row.availability),
        is_active=bool(row.is_active),
        last_discovered_at=_as_utc(row.last_discovered_at),
    )


def _rule_values(row: RuleRow) -> dict[str, Any]:
    return {
        "rule_id": row.rule_id,
        "rule_version": row.rule_version,
        "canonical_model_id": row.canonical_model_id,
        "fallback_model_id": row.fallback_model_id,
        "description": row.description,
        "enabled": row.enabled,
        "priority": row.priority,
        "task_labels_json": _dump_list(row.task_labels),
        "agent_types_json": _dump_list(row.agent_types),
        "workflow_types_json": _dump_list(row.workflow_types),
        "required_capabilities_json": _dump_list(row.required_capabilities),
        "min_context_tokens": row.min_context_tokens,
        "requires_tools": row.requires_tools,
        "requires_vision": row.requires_vision,
        "cost_classes_json": _dump_list(row.cost_classes),
        "requires_local": row.requires_local,
        "requires_private": row.requires_private,
        "user_preference_model": row.user_preference_model,
        "created_at": _as_utc(row.created_at),
        "updated_at": _as_utc(row.updated_at),
    }


def _rule_from_row(row: Any) -> RuleRow:
    return RuleRow(
        rule_id=str(row.rule_id),
        rule_version=int(row.rule_version),
        canonical_model_id=str(row.canonical_model_id),
        fallback_model_id=row.fallback_model_id,
        description=str(row.description),
        enabled=bool(row.enabled),
        priority=int(row.priority),
        task_labels=_load_list(row.task_labels_json),
        agent_types=_load_list(row.agent_types_json),
        workflow_types=_load_list(row.workflow_types_json),
        required_capabilities=_load_list(row.required_capabilities_json),
        min_context_tokens=int(row.min_context_tokens),
        requires_tools=bool(row.requires_tools),
        requires_vision=bool(row.requires_vision),
        cost_classes=_load_list(row.cost_classes_json),
        requires_local=bool(row.requires_local),
        requires_private=bool(row.requires_private),
        user_preference_model=row.user_preference_model,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _lock_from_row(row: Any) -> RouteLockRecord:
    try:
        snapshot_data = json.loads(row.snapshot_json)
    except ValueError:
        snapshot_data = {}
    snapshot = (
        RoutingSnapshot.from_dict(snapshot_data)
        if isinstance(snapshot_data, dict)
        else RoutingSnapshot(rule_id=str(row.rule_id), rule_version=0, canonical_model_id=str(row.canonical_model_id))
    )
    created_at = _as_utc(row.created_at)
    released_at = _as_utc(row.released_at)
    return RouteLockRecord(
        lock_id=str(row.lock_id),
        scope_type=str(row.scope_type),
        scope_id=str(row.scope_id),
        canonical_model_id=str(row.canonical_model_id),
        routing_snapshot=snapshot,
        status=str(row.status),
        created_at=created_at.timestamp() if created_at is not None else 0.0,
        released_at=released_at.timestamp() if released_at is not None else None,
        reselection_count=int(row.reselection_count),
        is_fallback=bool(row.is_fallback),
        source_lock_id=row.source_lock_id,
    )
