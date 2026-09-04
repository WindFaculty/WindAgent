"""Provider registry service: vendors, endpoints, credentials, rules, catalog.

REWRITE of the frozen ``management/service.py`` plus the rule management of
the old API layer.  Preserved behaviors:

- atomic provider + endpoint registration with duplicate detection;
- write-only credentials: raw secrets travel to the platform ``SecretStore``
  and only metadata is durably stored or returned — no read path exists;
- credential rotation creates a new version and revokes the old rows;
- provider deletion refuses when enabled rules still reference the models
  (``allow_disabling_rules`` disables them first, audited by events);
- discovery reconciliation adds/updates/keeps and marks missing bindings
  unavailable — it never deletes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from windagent.kernel.time import Clock, SystemClock, utc_now
from windagent.platform.security import SecretStore, SecretValue

from ..domain.errors import (
    DuplicateProviderError,
    ModelGatewayValidationError,
    ProviderInUseError,
    ProviderNotFoundError,
    RuleNotFoundError,
    RuleVersionConflictError,
)
from ..domain.normalization import normalize_model_id
from ..providers.contracts import DiscoveredModel
from .models import (
    BindingRow,
    CanonicalModelRow,
    CredentialRow,
    CredentialView,
    DiscoveryReconciliation,
    EndpointRow,
    EndpointView,
    ProviderRow,
    ProviderView,
    QuotaStateRecord,
    RuleRow,
    RuleView,
)
from .ports import TransactionScope


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ModelGatewayValidationError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ModelGatewayValidationError(f"{field_name} cannot be empty")
    return normalized


def _slug(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "provider"


class ProviderRegistryService:
    """Owns every registry mutation; the API routes only dispatch to it."""

    def __init__(
        self,
        *,
        scope_factory: Callable[[], TransactionScope],
        secrets: SecretStore,
        clock: Clock | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._secrets = secrets
        self._clock: Clock = clock or SystemClock()

    # ------------------------------------------------------------------ #
    # Providers
    # ------------------------------------------------------------------ #

    async def register_provider(
        self,
        *,
        name: str,
        display_name: str | None = None,
        vendor_type: str = "cloud",
        base_url: str,
        protocol_mode: str = "openai",
        credential_secret: str | None = None,
        credential_label: str = "",
        supports_model_discovery: bool = True,
        endpoint_id: str | None = None,
    ) -> ProviderView:
        """Register a vendor with an initial endpoint and optional credential."""
        clean_name = _required_text(name, "name")
        clean_base_url = _required_text(base_url, "base_url")
        clean_protocol = _required_text(protocol_mode, "protocol_mode")

        provider_id = f"pv-{_slug(clean_name)}"
        endpoint_row = EndpointRow(
            id=endpoint_id or f"ep-{_slug(clean_name)}-{uuid4().hex[:6]}",
            provider_id=provider_id,
            base_url=clean_base_url,
            protocol_mode=clean_protocol,
        )
        provider_row = ProviderRow(
            id=provider_id,
            name=clean_name,
            display_name=display_name or clean_name,
            vendor_type=vendor_type or "cloud",
            base_url=clean_base_url,
            protocol_mode=clean_protocol,
            supports_model_discovery=supports_model_discovery,
        )

        credential_id: str | None = None
        secret_name: str | None = None
        if credential_secret:
            credential_id = f"cred-{uuid4().hex[:12]}"
            secret_name = self._credential_secret_name(credential_id)
            await self._secrets.write(secret_name, SecretValue(credential_secret))

        async with self._scope_factory() as scope:
            store = scope.store()
            if await store.get_provider_by_name(clean_name) is not None:
                raise DuplicateProviderError(
                    f"provider {clean_name!r} already exists",
                    context={"provider_name": clean_name},
                )
            created = await store.insert_provider(provider_row, endpoint_row)
            if not created:
                raise DuplicateProviderError(
                    f"provider {clean_name!r} already exists",
                    context={"provider_name": clean_name},
                )
            if credential_id and secret_name:
                await store.insert_credential(
                    CredentialRow(
                        id=credential_id,
                        provider_id=provider_id,
                        secret_name=secret_name,
                        label=credential_label,
                        created_at=utc_now(),
                    )
                )
            await scope.commit()
        return await self.get_provider(provider_id)

    async def update_provider(
        self,
        provider_id: str,
        *,
        display_name: str | None = None,
        base_url: str | None = None,
        protocol_mode: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderView:
        """Update mutable provider fields (secrets are never editable)."""
        async with self._scope_factory() as scope:
            row = await scope.store().update_provider(
                provider_id,
                display_name=display_name,
                base_url=base_url,
                protocol_mode=protocol_mode,
                enabled=enabled,
            )
            if row is None:
                raise ProviderNotFoundError(
                    f"provider {provider_id!r} not found",
                    context={"provider_id": provider_id},
                )
            await scope.commit()
        return await self.get_provider(provider_id)

    async def delete_provider(
        self, provider_id: str, *, allow_disabling_rules: bool = False
    ) -> dict[str, object]:
        """Delete a provider, refusing while enabled rules reference its models."""
        async with self._scope_factory() as scope:
            store = scope.store()
            provider = await store.get_provider(provider_id)
            if provider is None:
                raise ProviderNotFoundError(
                    f"provider {provider_id!r} not found",
                    context={"provider_id": provider_id},
                )
            blocking = tuple(
                await store.rule_ids_referencing_models(
                    frozenset(await store.canonical_models_for_provider(provider_id))
                )
            )
            disabled_rules: tuple[str, ...] = ()
            if blocking and allow_disabling_rules:
                await store.disable_rules(blocking, when=utc_now())
                disabled_rules = blocking
                blocking = ()
            if blocking:
                raise ProviderInUseError(
                    "provider is still referenced by enabled routing rules",
                    context={
                        "provider_id": provider_id,
                        "blocking_rules": list(blocking),
                    },
                )
            await store.delete_provider(provider_id)
            await scope.commit()
        return {"provider_id": provider_id, "disabled_rules": list(disabled_rules)}

    # ------------------------------------------------------------------ #
    # Credentials (write-only)
    # ------------------------------------------------------------------ #

    async def rotate_credential(
        self, provider_id: str, *, secret: str, label: str = ""
    ) -> CredentialView:
        """Store a new credential version and revoke the previous one."""
        if not secret or not secret.strip():
            raise ModelGatewayValidationError("credential secret cannot be empty")
        credential_id = f"cred-{uuid4().hex[:12]}"
        secret_name = self._credential_secret_name(credential_id)
        now = utc_now()

        async with self._scope_factory() as scope:
            store = scope.store()
            provider = await store.get_provider(provider_id)
            if provider is None:
                raise ProviderNotFoundError(
                    f"provider {provider_id!r} not found",
                    context={"provider_id": provider_id},
                )
            previous = await store.active_credential_for_provider(provider_id)
            next_version = (previous.secret_version + 1) if previous else 1
            stale_secret_names: tuple[str, ...] = (
                (previous.secret_name,) if previous is not None else ()
            )
            await self._secrets.write(secret_name, SecretValue(secret))
            # Revoke the old actives first, then insert the new row, so the
            # revoke can never touch the credential it precedes.
            await store.revoke_active_credentials(provider_id, when=now)
            await store.insert_credential(
                CredentialRow(
                    id=credential_id,
                    provider_id=provider_id,
                    secret_name=secret_name,
                    secret_version=next_version,
                    label=label,
                    created_at=now,
                )
            )
            await scope.commit()
        # The superseded secret material leaves the store entirely.
        for stale_name in stale_secret_names:
            await self._secrets.delete(stale_name)

        row = CredentialRow(
            id=credential_id,
            provider_id=provider_id,
            secret_name=secret_name,
            secret_version=next_version,
            label=label,
            created_at=now,
        )
        return CredentialView(
            id=row.id,
            provider_id=row.provider_id,
            label=row.label,
            secret_version=row.secret_version,
            created_at=row.created_at,
        )

    async def remove_credential(self, provider_id: str) -> bool:
        """Revoke and delete the stored secret material of a provider."""
        now = utc_now()
        secret_name: str | None = None
        async with self._scope_factory() as scope:
            store = scope.store()
            active = await store.active_credential_for_provider(provider_id)
            if active is None:
                return False
            secret_name = active.secret_name
            await store.revoke_active_credentials(provider_id, when=now)
            await scope.commit()
        if secret_name is not None:
            await self._secrets.delete(secret_name)
        return True

    async def add_endpoint(
        self,
        provider_id: str,
        *,
        base_url: str,
        protocol_mode: str | None = None,
        priority: int = 50,
        weight: int = 100,
    ) -> EndpointView:
        """Register an additional callable endpoint for a provider."""
        clean_base_url = _required_text(base_url, "base_url")
        async with self._scope_factory() as scope:
            store = scope.store()
            provider = await store.get_provider(provider_id)
            if provider is None:
                raise ProviderNotFoundError(
                    f"provider {provider_id!r} not found",
                    context={"provider_id": provider_id},
                )
            row = EndpointRow(
                id=f"ep-{_slug(provider.name)}-{uuid4().hex[:6]}",
                provider_id=provider_id,
                base_url=clean_base_url,
                protocol_mode=protocol_mode or provider.protocol_mode,
                priority=priority,
                weight=weight,
            )
            if not await store.insert_endpoint(row):
                raise ProviderNotFoundError(
                    f"provider {provider_id!r} not found",
                    context={"provider_id": provider_id},
                )
            await scope.commit()
        return EndpointView(
            id=row.id,
            provider_id=row.provider_id,
            base_url=row.base_url,
            protocol_mode=row.protocol_mode,
            priority=row.priority,
            weight=row.weight,
            enabled=row.enabled,
            test_status=row.test_status,
        )

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    async def get_provider(self, provider_id: str) -> ProviderView:
        """Fetch one provider view."""
        async with self._scope_factory() as scope:
            store = scope.store()
            row = await store.get_provider(provider_id)
            endpoints = await store.list_endpoints_for_provider(provider_id)
            credential = await store.active_credential_for_provider(provider_id)
            model_count = await store.count_provider_models(provider_id)
        if row is None:
            raise ProviderNotFoundError(
                f"provider {provider_id!r} not found",
                context={"provider_id": provider_id},
            )
        return ProviderView(
            id=row.id,
            name=row.name,
            display_name=row.display_name,
            vendor_type=row.vendor_type,
            base_url=row.base_url,
            protocol_mode=row.protocol_mode,
            supports_model_discovery=row.supports_model_discovery,
            enabled=row.enabled,
            endpoint_count=len(endpoints),
            has_credential=credential is not None,
            model_count=model_count,
        )

    async def list_providers(self) -> tuple[ProviderView, ...]:
        """List every provider view."""
        async with self._scope_factory() as scope:
            store = scope.store()
            rows = await store.list_providers()
            views: list[ProviderView] = []
            for row in rows:
                endpoints = await store.list_endpoints_for_provider(row.id)
                credential = await store.active_credential_for_provider(row.id)
                model_count = await store.count_provider_models(row.id)
                views.append(
                    ProviderView(
                        id=row.id,
                        name=row.name,
                        display_name=row.display_name,
                        vendor_type=row.vendor_type,
                        base_url=row.base_url,
                        protocol_mode=row.protocol_mode,
                        supports_model_discovery=row.supports_model_discovery,
                        enabled=row.enabled,
                        endpoint_count=len(endpoints),
                        has_credential=credential is not None,
                        model_count=model_count,
                    )
                )
        return tuple(views)

    async def list_endpoints(self, provider_id: str) -> tuple[EndpointView, ...]:
        """List a provider's endpoint views."""
        async with self._scope_factory() as scope:
            rows = await scope.store().list_endpoints_for_provider(provider_id)
        return tuple(
            EndpointView(
                id=row.id,
                provider_id=row.provider_id,
                base_url=row.base_url,
                protocol_mode=row.protocol_mode,
                priority=row.priority,
                weight=row.weight,
                enabled=row.enabled,
                test_status=row.test_status,
            )
            for row in rows
        )

    async def list_models(self) -> tuple[tuple[CanonicalModelRow, tuple[BindingRow, ...]], ...]:
        """Return the canonical catalog with bindings per model."""
        async with self._scope_factory() as scope:
            store = scope.store()
            models = await store.list_models()
            grouped: list[tuple[CanonicalModelRow, tuple[BindingRow, ...]]] = []
            for model in models:
                bindings = await store.list_bindings(canonical_model_id=model.canonical_name)
                grouped.append((model, bindings))
        return tuple(grouped)

    # ------------------------------------------------------------------ #
    # Routing rules
    # ------------------------------------------------------------------ #

    async def upsert_rule(
        self,
        *,
        rule_id: str,
        canonical_model_id: str,
        fallback_model_id: str | None = None,
        description: str = "",
        enabled: bool = True,
        priority: int | None = None,
        expected_version: int | None = None,
        task_labels: tuple[str, ...] = (),
        agent_types: tuple[str, ...] = (),
        workflow_types: tuple[str, ...] = (),
        required_capabilities: tuple[str, ...] = (),
        min_context_tokens: int = 0,
        requires_tools: bool = False,
        requires_vision: bool = False,
        cost_classes: tuple[str, ...] = (),
        requires_local: bool = False,
        requires_private: bool = False,
        user_preference_model: str | None = None,
    ) -> RuleView:
        """Create or update a rule; updates bump the durable rule version."""
        clean_rule_id = _required_text(rule_id, "rule_id")
        clean_model = _required_text(canonical_model_id, "canonical_model_id")
        async with self._scope_factory() as scope:
            store = scope.store()
            existing = await store.get_rule(clean_rule_id)
            if existing is not None and expected_version is not None:
                if expected_version != existing.rule_version:
                    raise RuleVersionConflictError(
                        f"rule {clean_rule_id!r} changed concurrently",
                        context={
                            "rule_id": clean_rule_id,
                            "expected_version": expected_version,
                            "actual_version": existing.rule_version,
                        },
                    )
            version = 1 if existing is None else existing.rule_version + 1
            resolved_priority = (
                priority
                if priority is not None
                else (existing.priority if existing is not None else 50)
            )
            row = RuleRow(
                rule_id=clean_rule_id,
                rule_version=version,
                canonical_model_id=clean_model,
                fallback_model_id=fallback_model_id,
                description=description,
                enabled=enabled,
                priority=resolved_priority,
                task_labels=tuple(task_labels),
                agent_types=tuple(agent_types),
                workflow_types=tuple(workflow_types),
                required_capabilities=tuple(required_capabilities),
                min_context_tokens=min_context_tokens,
                requires_tools=requires_tools,
                requires_vision=requires_vision,
                cost_classes=tuple(cost_classes),
                requires_local=requires_local,
                requires_private=requires_private,
                user_preference_model=user_preference_model,
                updated_at=utc_now(),
            )
            saved = await store.upsert_rule(row)
            await scope.commit()
        return RuleView.from_row(saved)

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete one rule."""
        async with self._scope_factory() as scope:
            deleted = await scope.store().delete_rule(rule_id)
            await scope.commit()
        if not deleted:
            raise RuleNotFoundError(
                f"rule {rule_id!r} not found", context={"rule_id": rule_id}
            )
        return True

    async def list_rules(self) -> tuple[RuleView, ...]:
        """List every rule view."""
        async with self._scope_factory() as scope:
            rows = await scope.store().list_rules()
        return tuple(RuleView.from_row(row) for row in rows)

    # ------------------------------------------------------------------ #
    # Discovery reconciliation
    # ------------------------------------------------------------------ #

    async def record_discovery(
        self, endpoint_id: str, models: tuple[DiscoveredModel, ...]
    ) -> DiscoveryReconciliation:
        """Reconcile a discovery snapshot into the canonical catalog.

        Binding semantics preserved from the frozen registry service: added,
        updated, and unchanged states are computed at write time, and bindings
        that disappear from the snapshot are marked unavailable — never
        deleted.
        """
        now = utc_now()
        added: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []

        async with self._scope_factory() as scope:
            store = scope.store()
            endpoint = await store.get_endpoint(endpoint_id)
            if endpoint is None:
                raise ProviderNotFoundError(
                    f"endpoint {endpoint_id!r} not found",
                    context={"endpoint_id": endpoint_id},
                )
            provider = await store.get_provider(endpoint.provider_id)
            if provider is None:
                raise ProviderNotFoundError(
                    f"provider {endpoint.provider_id!r} not found",
                    context={"endpoint_id": endpoint_id},
                )

            for discovered in models:
                normalized = normalize_model_id(discovered.id, default_vendor=provider.name)
                await store.upsert_model(
                    CanonicalModelRow(
                        canonical_name=normalized.canonical_name,
                        vendor=normalized.vendor,
                        family=normalized.family,
                        revision=normalized.revision,
                        quantization=normalized.quantization,
                        parameter_size=normalized.parameter_size,
                        equivalence_fingerprint=normalized.equivalence_fingerprint,
                        context_window=discovered.context_window,
                        created_at=now,
                        updated_at=now,
                    )
                )
                outcome = await store.upsert_binding(
                    BindingRow(
                        id=f"bnd-{uuid4().hex[:12]}",
                        endpoint_id=endpoint_id,
                        canonical_model_id=normalized.canonical_name,
                        provider_model_id=discovered.id,
                        equivalence_fingerprint=normalized.equivalence_fingerprint,
                        last_discovered_at=now,
                    )
                )
                if outcome == "added":
                    added.append(discovered.id)
                elif outcome == "updated":
                    updated.append(discovered.id)
                else:
                    unchanged.append(discovered.id)

            unavailable = await store.mark_unavailable_bindings(
                endpoint_id,
                frozenset(model.id for model in models),
                when=now,
            )
            await scope.commit()

        return DiscoveryReconciliation(
            added=tuple(added),
            updated=tuple(updated),
            unchanged=tuple(unchanged),
            unavailable=tuple(unavailable),
        )

    async def record_quota(
        self,
        provider_name: str,
        *,
        has_quota: bool,
        remaining_requests_today: int | None = None,
        remaining_tokens_today: int | None = None,
        reset_at: datetime | None = None,
    ) -> None:
        """Persist a quota observation used by endpoint scoring."""
        async with self._scope_factory() as scope:
            await scope.store().save_quota_state(
                QuotaStateRecord(
                    provider_name=provider_name,
                    has_quota=has_quota,
                    remaining_requests_today=remaining_requests_today,
                    remaining_tokens_today=remaining_tokens_today,
                    reset_at=reset_at,
                    updated_at=utc_now(),
                )
            )
            await scope.commit()

    # ------------------------------------------------------------------ #

    @staticmethod
    def _credential_secret_name(credential_id: str) -> str:
        return f"model_gateway/credentials/{credential_id}"
