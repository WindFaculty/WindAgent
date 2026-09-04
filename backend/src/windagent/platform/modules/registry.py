"""Deterministic in-memory implementation of the module registry contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ModuleDescriptor
from .errors import ModuleConflictError


@dataclass(slots=True)
class InMemoryModuleRegistry:
    """Store successfully loaded descriptors by their canonical module ID."""

    _descriptors: dict[str, ModuleDescriptor] = field(default_factory=dict, init=False)

    def register(self, descriptor: ModuleDescriptor) -> None:
        if descriptor.module_id in self._descriptors:
            raise ModuleConflictError(f"module '{descriptor.module_id}' is already registered")
        self._descriptors[descriptor.module_id] = descriptor

    def get(self, module_id: str) -> ModuleDescriptor | None:
        return self._descriptors.get(module_id.strip())

    def all(self) -> tuple[ModuleDescriptor, ...]:
        return tuple(self._descriptors[module_id] for module_id in sorted(self._descriptors))
