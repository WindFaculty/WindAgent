"""Stable module identity contracts.

The executable manifest, discovery, and registration runtime live beside this
small protocol in the same package. Keeping the descriptor separate lets
callers ask which modules were loaded without exposing a feature's handlers,
routers, or migration objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    """Stable identity and advertised capabilities of one feature module."""

    module_id: str
    version: str
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "module_id", _required_text(self.module_id, "module_id"))
        object.__setattr__(self, "version", _required_text(self.version, "version"))
        normalized_capabilities = tuple(
            _required_text(capability, "capability") for capability in self.capabilities
        )
        if len(set(normalized_capabilities)) != len(normalized_capabilities):
            raise ValueError("capabilities must not contain duplicates")
        object.__setattr__(self, "capabilities", normalized_capabilities)


@runtime_checkable
class ModuleRegistry(Protocol):
    """Registry of successfully loaded modules available to a composition root."""

    def register(self, descriptor: ModuleDescriptor) -> None:
        """Register a descriptor during application bootstrap."""

    def get(self, module_id: str) -> ModuleDescriptor | None:
        """Return the descriptor for ``module_id`` when it is registered."""

    def all(self) -> tuple[ModuleDescriptor, ...]:
        """Return the complete, deterministic set of registered modules."""
