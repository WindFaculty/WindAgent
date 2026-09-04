"""Application ports: durable store, transaction scope, and adapter factory.

The application layer depends only on these protocols; the SQL adapter
(infrastructure) and the test fakes both satisfy them.  A transaction scope
yields a store and records events atomically with the domain writes — the
platform outbox pattern preserved at the module boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from windagent.kernel.events import EventEnvelope

from ..domain.circuit import EndpointRuntimeState
from ..domain.route_lock import RouteLockRecord
from ..providers.contracts import ProviderAdapter
from .models import (
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


@runtime_checkable
class ModelGatewayStore(Protocol):
    """Durable access to every model-gateway aggregate.

    Implementations join the caller's transaction scope; they never commit
    on their own.
    """

    # -- providers ---------------------------------------------------------
    async def insert_provider(self, row: ProviderRow, endpoint: EndpointRow | None) -> bool:
        """Insert a provider (plus optional initial endpoint) atomically.

        Returns ``False`` when a provider with the same name already exists.
        """
        ...

    async def get_provider(self, provider_id: str) -> ProviderRow | None:
        """Fetch one provider by id."""
        ...

    async def get_provider_by_name(self, name: str) -> ProviderRow | None:
        """Fetch one provider by unique name."""
        ...

    async def list_providers(self) -> tuple[ProviderRow, ...]:
        """List every provider."""
        ...

    async def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        protocol_mode: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderRow | None:
        """Update mutable provider fields; ``None`` leaves a field unchanged."""
        ...

    async def delete_provider(self, provider_id: str) -> bool:
        """Delete a provider and its endpoints/credentials."""
        ...

    # -- endpoints ---------------------------------------------------------
    async def insert_endpoint(self, row: EndpointRow) -> bool:
        """Insert an endpoint; ``False`` when the provider does not exist."""
        ...

    async def get_endpoint(self, endpoint_id: str) -> EndpointRow | None:
        """Fetch one endpoint by id."""
        ...

    async def list_endpoints_for_provider(self, provider_id: str) -> tuple[EndpointRow, ...]:
        """List a provider's endpoints."""
        ...

    async def update_endpoint_status(self, endpoint_id: str, test_status: str) -> bool:
        """Record a connection-test outcome on an endpoint."""
        ...

    # -- credentials -------------------------------------------------------
    async def insert_credential(self, row: CredentialRow) -> bool:
        """Insert credential metadata; ``False`` when the provider is missing."""
        ...

    async def active_credential_for_provider(self, provider_id: str) -> CredentialRow | None:
        """Return the newest active credential, if any."""
        ...

    async def revoke_active_credentials(self, provider_id: str, *, when: datetime) -> int:
        """Revoke every active credential of a provider."""
        ...

    # -- canonical models and bindings --------------------------------------
    async def upsert_model(self, row: CanonicalModelRow) -> bool:
        """Insert or update a canonical model; ``True`` when created."""
        ...

    async def get_model(self, canonical_name: str) -> CanonicalModelRow | None:
        """Fetch one canonical model."""
        ...

    async def list_models(self) -> tuple[CanonicalModelRow, ...]:
        """List the canonical catalog."""
        ...

    async def upsert_binding(self, row: BindingRow) -> str:
        """Insert or update a binding; returns ``added``/``updated``/``unchanged``."""
        ...

    async def list_bindings(self, *, canonical_model_id: str | None = None) -> tuple[BindingRow, ...]:
        """List bindings, optionally scoped to one canonical model."""
        ...

    async def mark_unavailable_bindings(
        self, endpoint_id: str, keep_provider_model_ids: frozenset[str], *, when: datetime
    ) -> tuple[str, ...]:
        """Mark stale bindings unavailable; returns the marked ids."""
        ...

    async def list_selectable_bindings(self, canonical_model_id: str) -> tuple[SelectableBinding, ...]:
        """List active bindings joined with endpoint/provider/credential state."""
        ...

    async def count_provider_models(self, provider_id: str) -> int:
        """Count distinct canonical models bound to a provider's endpoints."""
        ...

    async def canonical_models_for_provider(self, provider_id: str) -> tuple[str, ...]:
        """List canonical model ids bound to a provider's endpoints."""
        ...

    # -- routing rules -------------------------------------------------------
    async def upsert_rule(self, row: RuleRow) -> RuleRow:
        """Insert or update a rule, bumping the version on conflict."""
        ...

    async def get_rule(self, rule_id: str) -> RuleRow | None:
        """Fetch one rule."""
        ...

    async def list_rules(self) -> tuple[RuleRow, ...]:
        """List every rule."""
        ...

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete one rule."""
        ...

    async def rule_ids_referencing_models(self, canonical_models: frozenset[str]) -> tuple[str, ...]:
        """Return enabled rule ids whose models fall in ``canonical_models``."""
        ...

    async def disable_rules(self, rule_ids: tuple[str, ...], *, when: datetime) -> int:
        """Disable the given rules; returns the affected count."""
        ...

    # -- route locks ----------------------------------------------------------
    async def record_route_lock(self, lock: RouteLockRecord) -> bool:
        """Insert a lock; ``False`` when the scope already holds an active one."""
        ...

    async def get_route_lock(self, lock_id: str) -> RouteLockRecord | None:
        """Fetch one lock by id."""
        ...

    async def get_active_route_lock(self, scope_type: str, scope_id: str) -> RouteLockRecord | None:
        """Fetch the single active lock for a scope."""
        ...

    async def release_route_lock(self, lock_id: str, *, when: datetime) -> bool:
        """Release an active lock; ``False`` when it is gone or released."""
        ...

    # -- endpoint runtime state and quota --------------------------------------
    async def get_endpoint_state(self, endpoint_id: str) -> EndpointRuntimeState:
        """Return the durable runtime state (empty record when fresh)."""
        ...

    async def save_endpoint_state(self, endpoint_id: str, state: EndpointRuntimeState) -> None:
        """Persist the runtime state."""
        ...

    async def get_quota_state(self, provider_name: str) -> QuotaStateRecord:
        """Return the durable quota observation (optimistic default)."""
        ...

    async def save_quota_state(self, state: QuotaStateRecord) -> None:
        """Persist the quota observation."""
        ...

    # -- attempts and receipts ---------------------------------------------------
    async def insert_attempt(self, row: AttemptRow) -> None:
        """Append one execution-attempt record."""
        ...

    async def insert_receipt(self, row: ReceiptRow) -> None:
        """Append one routing receipt."""
        ...

    async def list_receipts(self, *, task_id: str | None, limit: int) -> tuple[ReceiptRow, ...]:
        """List recent receipts, optionally scoped to one task."""
        ...


@runtime_checkable
class TransactionScope(Protocol):
    """One durable scope: domain writes plus atomic outbox event recording.

    Used as ``async with scope_factory() as scope:``; ``__aexit__`` rolls
    back unless :meth:`commit` already persisted the scope.
    """

    async def __aenter__(self) -> TransactionScope:
        """Open the transaction and bind the store."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> bool:
        """Close the scope without suppressing application exceptions."""
        ...

    def store(self) -> ModelGatewayStore:
        """The store bound to this scope's transaction."""
        ...

    async def record_event(
        self, envelope: EventEnvelope, *, deduplication_key: str | None = None
    ) -> bool:
        """Append an event to the outbox inside the same transaction.

        Returns ``False`` when a record with the same deduplication key
        already exists.
        """
        ...

    async def commit(self) -> None:
        """Atomically persist everything recorded in this scope."""
        ...


@runtime_checkable
class AdapterFactory(Protocol):
    """Builds provider adapters at the credential use boundary."""

    def resolve(
        self,
        protocol_mode: str,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float | None = None,
    ) -> ProviderAdapter:
        """Return the transport for one attempt."""
        ...
