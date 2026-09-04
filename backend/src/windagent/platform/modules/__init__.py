"""Feature module manifest, discovery, and registration runtime."""

from .contracts import ModuleDescriptor, ModuleRegistry
from .discovery import (
    DEFAULT_MODULE_PACKAGE,
    ModuleDiscovery,
    PackageModuleDiscovery,
    StaticModuleDiscovery,
)
from .errors import (
    ModuleConflictError,
    ModuleDiscoveryError,
    ModuleRegistrationError,
    ModuleRuntimeError,
    ModuleValidationError,
)
from .loader import ModuleLoader
from .manifest import (
    CommandRegistration,
    EventHandlerRegistration,
    JobRegistration,
    ModuleManifest,
    QueryRegistration,
)
from .registry import InMemoryModuleRegistry
from .runtime import ModuleRuntime

__all__ = [
    "DEFAULT_MODULE_PACKAGE",
    "CommandRegistration",
    "EventHandlerRegistration",
    "InMemoryModuleRegistry",
    "JobRegistration",
    "ModuleConflictError",
    "ModuleDescriptor",
    "ModuleDiscovery",
    "ModuleDiscoveryError",
    "ModuleLoader",
    "ModuleManifest",
    "ModuleRegistrationError",
    "ModuleRegistry",
    "ModuleRuntime",
    "ModuleRuntimeError",
    "ModuleValidationError",
    "PackageModuleDiscovery",
    "QueryRegistration",
    "StaticModuleDiscovery",
]
