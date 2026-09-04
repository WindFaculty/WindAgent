"""Validate and register module manifests in the only supported bootstrap order."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import ModuleRegistry
from .discovery import ModuleDiscovery, PackageModuleDiscovery
from .errors import (
    ModuleConflictError,
    ModuleDiscoveryError,
    ModuleRegistrationError,
    ModuleValidationError,
)
from .manifest import ModuleManifest
from .runtime import ModuleRuntime


class ModuleLoader:
    """Composition service for all domain modules.

    It collects every manifest and validates the entire set before mutating a
    runtime. This prevents a duplicate command, query, job, or module ID from
    leaving a partially configured process at startup.
    """

    def __init__(self, registry: ModuleRegistry, runtime: ModuleRuntime) -> None:
        self._registry = registry
        self._runtime = runtime

    def bootstrap(self, discoveries: Iterable[ModuleDiscovery]) -> tuple[ModuleManifest, ...]:
        """Discover, validate, and register all feature modules."""
        return self.register(self.validate(self.discover(discoveries)))

    def bootstrap_package(self, package: str = "windagent.modules") -> tuple[ModuleManifest, ...]:
        """Bootstrap all manifests under one package namespace."""
        return self.bootstrap((PackageModuleDiscovery(package),))

    def discover(self, discoveries: Iterable[ModuleDiscovery]) -> tuple[ModuleManifest, ...]:
        """Collect manifests from discovery sources in deterministic ID order."""
        manifests: list[ModuleManifest] = []
        for discovery in discoveries:
            if not isinstance(discovery, ModuleDiscovery):
                raise TypeError("every discovery source must implement ModuleDiscovery")
            try:
                discovered = discovery.discover()
            except ModuleDiscoveryError:
                raise
            except Exception as error:
                raise ModuleDiscoveryError("module discovery failed") from error
            if any(not isinstance(manifest, ModuleManifest) for manifest in discovered):
                raise ModuleDiscoveryError("discovery sources must return only ModuleManifest values")
            manifests.extend(discovered)
        return tuple(sorted(manifests, key=lambda manifest: manifest.id))

    def validate(self, manifests: Iterable[ModuleManifest]) -> tuple[ModuleManifest, ...]:
        """Reject duplicate identities and the single-owner registration keys."""
        collected = tuple(manifests)
        if any(not isinstance(manifest, ModuleManifest) for manifest in collected):
            raise TypeError("all loaded values must be ModuleManifest instances")
        normalized = tuple(sorted(collected, key=lambda manifest: manifest.id))

        module_ids: set[str] = set()
        command_owners: dict[str, str] = {}
        query_owners: dict[str, str] = {}
        job_owners: dict[str, str] = {}

        for manifest in normalized:
            if manifest.id in module_ids or self._registry.get(manifest.id) is not None:
                raise ModuleConflictError(f"module '{manifest.id}' is already registered")
            module_ids.add(manifest.id)
            self._validate_single_owner("command", manifest.id, command_owners, manifest.commands)
            self._validate_single_owner("query", manifest.id, query_owners, manifest.queries)
            self._validate_single_owner("job", manifest.id, job_owners, manifest.jobs)

        return normalized

    @staticmethod
    def _validate_single_owner(
        kind: str, module_id: str, owners: dict[str, str], registrations: Iterable[object]
    ) -> None:
        for registration in registrations:
            key = getattr(registration, "key", None)
            if key is None:
                key = getattr(registration, "job_type", None)
            if not isinstance(key, str):
                raise ModuleValidationError(f"{kind} registration has no stable key")
            owner = owners.get(key)
            if owner is not None:
                raise ModuleConflictError(
                    f"{kind} '{key}' is claimed by both '{owner}' and '{module_id}'"
                )
            owners[key] = module_id

    def register(self, manifests: Iterable[ModuleManifest]) -> tuple[ModuleManifest, ...]:
        """Register validated contributions in the canonical Phase 4 sequence."""
        loaded = tuple(manifests)
        try:
            for manifest in loaded:
                for command_registration in manifest.commands:
                    self._runtime.register_command(command_registration)
            for manifest in loaded:
                for query_registration in manifest.queries:
                    self._runtime.register_query(query_registration)
            for manifest in loaded:
                for job_registration in manifest.jobs:
                    self._runtime.register_job(job_registration)
            for manifest in loaded:
                for event_handler_registration in manifest.event_handlers:
                    self._runtime.register_event_handler(event_handler_registration)
            for manifest in loaded:
                for router in manifest.routers:
                    self._runtime.register_router(manifest.id, router)
            for manifest in loaded:
                for migration in manifest.migrations:
                    self._runtime.register_migration(manifest.id, migration)
            for manifest in loaded:
                self._registry.register(manifest.descriptor)
        except ModuleRegistrationError:
            raise
        except Exception as error:
            raise ModuleRegistrationError("validated module registration failed") from error
        return loaded
