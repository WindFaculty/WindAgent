"""In-memory store and transaction scope for unit tests and dev embedding.

Not durable by design (plan section 8: only PostgreSQL is canonical); this
adapter exists so the module's application behavior can be tested offline
and so tiny deployments can exercise routing without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from windagent.kernel.events import EventEnvelope

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
from ..domain.route_lock import LockStatus, RouteLockRecord


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryModelGatewayStore(ModelGatewayStore):
    """Dictionary-backed implementation of the store port."""

    def __init__(self) -> None:
        self.providers: dict[str, ProviderRow] = {}
        self.provider_by_name: dict[str, str] = {}
        self.endpoints: dict[str, EndpointRow] = {}
        self.credentials: dict[str, CredentialRow] = {}
        self.models: dict[str, CanonicalModelRow] = {}
        self.bindings: dict[tuple[str, str], BindingRow] = {}
        self.rules: dict[str, RuleRow] = {}
        self.locks: dict[str, RouteLockRecord] = {}
        self.endpoint_states: dict[str, EndpointRuntimeState] = {}
        self.quota_states: dict[str, QuotaStateRecord] = {}
        self.attempts: list[AttemptRow] = []
        self.receipts: list[ReceiptRow] = []
        self.events: list[EventEnvelope] = []

    # -- providers ---------------------------------------------------------
    async def insert_provider(
        self, row: ProviderRow, endpoint: EndpointRow | None
    ) -> bool:
        if row.name in self.provider_by_name:
            return False
        self.providers[row.id] = row
        self.provider_by_name[row.name] = row.id
        if endpoint is not None:
            self.endpoints[endpoint.id] = endpoint
        return True

    async def get_provider(self, provider_id: str) -> ProviderRow | None:
        return self.providers.get(provider_id)

    async def get_provider_by_name(self, name: str) -> ProviderRow | None:
        provider_id = self.provider_by_name.get(name)
        return self.providers.get(provider_id) if provider_id else None

    async def list_providers(self) -> tuple[ProviderRow, ...]:
        return tuple(self.providers.values())

    async def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        protocol_mode: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderRow | None:
        row = self.providers.get(provider_id)
        if row is None:
            return None
        updated = ProviderRow(
            id=row.id,
            name=row.name,
            display_name=display_name if display_name is not None else row.display_name,
            vendor_type=row.vendor_type,
            base_url=base_url if base_url is not None else row.base_url,
            protocol_mode=protocol_mode if protocol_mode is not None else row.protocol_mode,
            supports_model_discovery=row.supports_model_discovery,
            enabled=enabled if enabled is not None else row.enabled,
            created_at=row.created_at,
            updated_at=_utc_now(),
        )
        self.providers[provider_id] = updated
        return updated

    async def delete_provider(self, provider_id: str) -> bool:
        row = self.providers.pop(provider_id, None)
        if row is None:
            return False
        self.provider_by_name.pop(row.name, None)
        for key in [k for k, v in self.endpoints.items() if v.provider_id == provider_id]:
            del self.endpoints[key]
            self.bindings = {
                k: v for k, v in self.bindings.items() if v.endpoint_id != key
            }
        for key in [k for k, v in self.credentials.items() if v.provider_id == provider_id]:
            del self.credentials[key]
        return True

    # -- endpoints ---------------------------------------------------------
    async def insert_endpoint(self, row: EndpointRow) -> bool:
        if row.provider_id not in self.providers:
            return False
        self.endpoints[row.id] = row
        return True

    async def get_endpoint(self, endpoint_id: str) -> EndpointRow | None:
        return self.endpoints.get(endpoint_id)

    async def list_endpoints_for_provider(self, provider_id: str) -> tuple[EndpointRow, ...]:
        return tuple(e for e in self.endpoints.values() if e.provider_id == provider_id)

    async def update_endpoint_status(self, endpoint_id: str, test_status: str) -> bool:
        row = self.endpoints.get(endpoint_id)
        if row is None:
            return False
        self.endpoints[endpoint_id] = EndpointRow(
            id=row.id,
            provider_id=row.provider_id,
            base_url=row.base_url,
            protocol_mode=row.protocol_mode,
            priority=row.priority,
            weight=row.weight,
            enabled=row.enabled,
            test_status=test_status,
            created_at=row.created_at,
            updated_at=_utc_now(),
        )
        return True

    # -- credentials ---------------------------------------------------------
    async def insert_credential(self, row: CredentialRow) -> bool:
        if row.provider_id not in self.providers:
            return False
        self.credentials[row.id] = row
        return True

    async def active_credential_for_provider(self, provider_id: str) -> CredentialRow | None:
        active = [
            c
            for c in self.credentials.values()
            if c.provider_id == provider_id and c.revoked_at is None
        ]
        if not active:
            return None
        return sorted(
            active, key=lambda c: (c.created_at or _utc_now(), c.id), reverse=True
        )[0]

    async def revoke_active_credentials(
        self, provider_id: str, *, when: datetime
    ) -> int:
        count = 0
        for key, credential in list(self.credentials.items()):
            if credential.provider_id == provider_id and credential.revoked_at is None:
                self.credentials[key] = CredentialRow(
                    id=credential.id,
                    provider_id=credential.provider_id,
                    secret_name=credential.secret_name,
                    secret_version=credential.secret_version,
                    label=credential.label,
                    created_at=credential.created_at,
                    revoked_at=when,
                )
                count += 1
        return count

    # -- models and bindings -------------------------------------------------
    async def upsert_model(self, row: CanonicalModelRow) -> bool:
        created = row.canonical_name not in self.models
        if created:
            self.models[row.canonical_name] = row
        else:
            existing = self.models[row.canonical_name]
            self.models[row.canonical_name] = CanonicalModelRow(
                canonical_name=existing.canonical_name,
                vendor=row.vendor,
                family=row.family,
                revision=row.revision,
                quantization=row.quantization,
                parameter_size=row.parameter_size,
                equivalence_fingerprint=row.equivalence_fingerprint,
                context_window=row.context_window,
                capabilities=existing.capabilities,
                enabled=existing.enabled,
                created_at=existing.created_at,
                updated_at=row.updated_at,
            )
        return created

    async def get_model(self, canonical_name: str) -> CanonicalModelRow | None:
        return self.models.get(canonical_name)

    async def list_models(self) -> tuple[CanonicalModelRow, ...]:
        return tuple(sorted(self.models.values(), key=lambda m: m.canonical_name))

    async def upsert_binding(self, row: BindingRow) -> str:
        key = (row.endpoint_id, row.canonical_model_id)
        existing = self.bindings.get(key)
        if existing is None:
            self.bindings[key] = row
            return "added"
        changed = (
            existing.provider_model_id != row.provider_model_id
            or existing.availability != "active"
            or not existing.is_active
        )
        self.bindings[key] = BindingRow(
            id=existing.id,
            endpoint_id=existing.endpoint_id,
            canonical_model_id=existing.canonical_model_id,
            provider_model_id=row.provider_model_id,
            equivalence_level=existing.equivalence_level,
            equivalence_fingerprint=row.equivalence_fingerprint,
            pricing_class=existing.pricing_class,
            priority=existing.priority,
            availability="active",
            is_active=True,
            last_discovered_at=row.last_discovered_at,
        )
        return "updated" if changed else "unchanged"

    async def list_bindings(
        self, *, canonical_model_id: str | None = None
    ) -> tuple[BindingRow, ...]:
        return tuple(
            b
            for b in self.bindings.values()
            if canonical_model_id is None or b.canonical_model_id == canonical_model_id
        )

    async def mark_unavailable_bindings(
        self, endpoint_id: str, keep_provider_model_ids: frozenset[str], *, when: datetime
    ) -> tuple[str, ...]:
        marked: list[str] = []
        for key, binding in list(self.bindings.items()):
            if binding.endpoint_id != endpoint_id or binding.availability == "unavailable":
                continue
            if binding.provider_model_id in keep_provider_model_ids:
                continue
            self.bindings[key] = BindingRow(
                id=binding.id,
                endpoint_id=binding.endpoint_id,
                canonical_model_id=binding.canonical_model_id,
                provider_model_id=binding.provider_model_id,
                equivalence_level=binding.equivalence_level,
                equivalence_fingerprint=binding.equivalence_fingerprint,
                pricing_class=binding.pricing_class,
                priority=binding.priority,
                availability="unavailable",
                is_active=False,
                last_discovered_at=binding.last_discovered_at,
            )
            marked.append(binding.provider_model_id)
        return tuple(marked)

    async def list_selectable_bindings(
        self, canonical_model_id: str
    ) -> tuple[SelectableBinding, ...]:
        results: list[SelectableBinding] = []
        for binding in self.bindings.values():
            if binding.canonical_model_id != canonical_model_id or not binding.is_active:
                continue
            endpoint = self.endpoints.get(binding.endpoint_id)
            if endpoint is None:
                continue
            provider = self.providers.get(endpoint.provider_id)
            if provider is None:
                continue
            credential = await self.active_credential_for_provider(provider.id)
            results.append(
                SelectableBinding(
                    binding_id=binding.id,
                    endpoint_id=endpoint.id,
                    provider_name=provider.name,
                    provider_id=provider.id,
                    provider_model_id=binding.provider_model_id,
                    base_url=endpoint.base_url,
                    protocol_mode=endpoint.protocol_mode,
                    equivalence_level=binding.equivalence_level,
                    endpoint_enabled=endpoint.enabled,
                    binding_enabled=binding.is_active,
                    has_credential=credential is not None,
                    credential_secret_name=(
                        credential.secret_name if credential else None
                    ),
                )
            )
        return tuple(results)

    async def count_provider_models(self, provider_id: str) -> int:
        endpoint_ids = {
            e.id for e in self.endpoints.values() if e.provider_id == provider_id
        }
        return len(
            {
                b.canonical_model_id
                for b in self.bindings.values()
                if b.endpoint_id in endpoint_ids and b.is_active
            }
        )

    async def canonical_models_for_provider(self, provider_id: str) -> tuple[str, ...]:
        endpoint_ids = {
            e.id for e in self.endpoints.values() if e.provider_id == provider_id
        }
        return tuple(
            {
                b.canonical_model_id
                for b in self.bindings.values()
                if b.endpoint_id in endpoint_ids and b.is_active
            }
        )

    # -- rules ---------------------------------------------------------------
    async def upsert_rule(self, row: RuleRow) -> RuleRow:
        self.rules[row.rule_id] = row
        return row

    async def get_rule(self, rule_id: str) -> RuleRow | None:
        return self.rules.get(rule_id)

    async def list_rules(self) -> tuple[RuleRow, ...]:
        return tuple(sorted(self.rules.values(), key=lambda r: r.priority))

    async def delete_rule(self, rule_id: str) -> bool:
        return self.rules.pop(rule_id, None) is not None

    async def rule_ids_referencing_models(
        self, canonical_models: frozenset[str]
    ) -> tuple[str, ...]:
        return tuple(
            rule.rule_id
            for rule in self.rules.values()
            if rule.enabled and rule.canonical_model_id in canonical_models
        )

    async def disable_rules(self, rule_ids: tuple[str, ...], *, when: datetime) -> int:
        count = 0
        for rule_id in rule_ids:
            rule = self.rules.get(rule_id)
            if rule is None or not rule.enabled:
                continue
            self.rules[rule_id] = RuleRow(
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                canonical_model_id=rule.canonical_model_id,
                fallback_model_id=rule.fallback_model_id,
                description=rule.description,
                enabled=False,
                priority=rule.priority,
                task_labels=rule.task_labels,
                agent_types=rule.agent_types,
                workflow_types=rule.workflow_types,
                required_capabilities=rule.required_capabilities,
                min_context_tokens=rule.min_context_tokens,
                requires_tools=rule.requires_tools,
                requires_vision=rule.requires_vision,
                cost_classes=rule.cost_classes,
                requires_local=rule.requires_local,
                requires_private=rule.requires_private,
                user_preference_model=rule.user_preference_model,
                created_at=rule.created_at,
                updated_at=when,
            )
            count += 1
        return count

    # -- route locks -----------------------------------------------------------
    async def record_route_lock(self, lock: RouteLockRecord) -> bool:
        for existing in self.locks.values():
            if (
                existing.scope_type == lock.scope_type
                and existing.scope_id == lock.scope_id
                and existing.status == LockStatus.ACTIVE.value
            ):
                return False
        self.locks[lock.lock_id] = lock
        return True

    async def get_route_lock(self, lock_id: str) -> RouteLockRecord | None:
        return self.locks.get(lock_id)

    async def get_active_route_lock(
        self, scope_type: str, scope_id: str
    ) -> RouteLockRecord | None:
        for lock in self.locks.values():
            if (
                lock.scope_type == scope_type
                and lock.scope_id == scope_id
                and lock.status == LockStatus.ACTIVE.value
            ):
                return lock
        return None

    async def release_route_lock(self, lock_id: str, *, when: datetime) -> bool:
        lock = self.locks.get(lock_id)
        if lock is None or lock.status != LockStatus.ACTIVE.value:
            return False
        from dataclasses import replace

        self.locks[lock_id] = replace(
            lock, status=LockStatus.RELEASED.value, released_at=when.timestamp()
        )
        return True

    # -- state and quota ---------------------------------------------------------
    async def get_endpoint_state(self, endpoint_id: str) -> EndpointRuntimeState:
        return self.endpoint_states.get(endpoint_id, EndpointRuntimeState())

    async def save_endpoint_state(
        self, endpoint_id: str, state: EndpointRuntimeState
    ) -> None:
        self.endpoint_states[endpoint_id] = state

    async def get_quota_state(self, provider_name: str) -> QuotaStateRecord:
        return self.quota_states.get(
            provider_name, QuotaStateRecord(provider_name=provider_name, has_quota=True)
        )

    async def save_quota_state(self, state: QuotaStateRecord) -> None:
        self.quota_states[state.provider_name] = state

    # -- attempts and receipts ------------------------------------------------------
    async def insert_attempt(self, row: AttemptRow) -> None:
        self.attempts.append(row)

    async def insert_receipt(self, row: ReceiptRow) -> None:
        self.receipts.append(row)

    async def list_receipts(
        self, *, task_id: str | None, limit: int
    ) -> tuple[ReceiptRow, ...]:
        rows = [
            r for r in self.receipts if task_id is None or r.task_id == task_id
        ]
        return tuple(reversed(rows[-limit:]))


class InMemoryTransactionScope:
    """Single-transaction in-memory scope with event recording."""

    def __init__(self, store: InMemoryModelGatewayStore) -> None:
        self._store = store
        self._pending: list[tuple[EventEnvelope, str | None]] = []
        self._committed = False

    async def __aenter__(self) -> InMemoryTransactionScope:
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if exc_type is not None:
            self._pending.clear()
        return False

    def store(self) -> InMemoryModelGatewayStore:
        return self._store

    async def record_event(
        self, envelope: EventEnvelope, *, deduplication_key: str | None = None
    ) -> bool:
        self._pending.append((envelope, deduplication_key))
        return True

    async def commit(self) -> None:
        for envelope, _key in self._pending:
            self._store.events.append(envelope)
        self._pending.clear()
        self._committed = True


def memory_scope_factory(
    store: InMemoryModelGatewayStore,
) -> Callable[[], InMemoryTransactionScope]:
    """Scope factory over an in-memory store (never commits anywhere)."""
    return lambda: InMemoryTransactionScope(store)
