"""Errors raised while composing feature modules into a V2 runtime."""

from __future__ import annotations


class ModuleRuntimeError(RuntimeError):
    """Base error for module discovery, validation, or registration failures."""


class ModuleDiscoveryError(ModuleRuntimeError):
    """A configured discovery source could not produce valid manifests."""


class ModuleValidationError(ModuleRuntimeError):
    """One or more manifests cannot safely be loaded together."""


class ModuleConflictError(ModuleValidationError):
    """Two modules claim an identity or single-owner registration key."""


class ModuleRegistrationError(ModuleRuntimeError):
    """A validated manifest could not be registered with the target runtime."""
