"""Discovery sources for manifests without a hard-coded application module list."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module, invalidate_caches
from importlib.util import find_spec
from pkgutil import iter_modules
from typing import Protocol, runtime_checkable

from .errors import ModuleDiscoveryError
from .manifest import ModuleManifest

DEFAULT_MODULE_PACKAGE = "windagent.modules"


@runtime_checkable
class ModuleDiscovery(Protocol):
    """Returns every manifest advertised by one discovery source."""

    def discover(self) -> tuple[ModuleManifest, ...]:
        """Discover manifests without registering any of their contributions."""


@dataclass(frozen=True, slots=True)
class StaticModuleDiscovery:
    """Explicit discovery source for tests and small embedded deployments."""

    manifests: tuple[ModuleManifest, ...]

    def __init__(self, manifests: Iterable[ModuleManifest]) -> None:
        object.__setattr__(self, "manifests", tuple(manifests))

    def discover(self) -> tuple[ModuleManifest, ...]:
        return self.manifests


@dataclass(frozen=True, slots=True)
class PackageModuleDiscovery:
    """Find ``<module>.manifest:manifest`` below a package namespace.

    Adding ``windagent.modules.youtube_analytics/manifest.py`` is therefore
    enough to make a feature discoverable; no API or worker bootstrap file
    needs to know the feature's name.
    """

    package: str = DEFAULT_MODULE_PACKAGE

    def __post_init__(self) -> None:
        if not isinstance(self.package, str) or not self.package.strip():
            raise ValueError("package must be a non-empty package name")
        object.__setattr__(self, "package", self.package.strip())

    def discover(self) -> tuple[ModuleManifest, ...]:
        invalidate_caches()
        try:
            package = import_module(self.package)
        except (ImportError, ValueError) as error:
            raise ModuleDiscoveryError(f"cannot import module package '{self.package}'") from error

        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            raise ModuleDiscoveryError(f"'{self.package}' is not a package")

        manifests: list[ModuleManifest] = []
        for package_info in sorted(iter_modules(package_paths), key=lambda item: item.name):
            if package_info.name.startswith("_"):
                continue
            manifest_module_name = f"{self.package}.{package_info.name}.manifest"
            try:
                if find_spec(manifest_module_name) is None:
                    continue
                manifest_module = import_module(manifest_module_name)
            except (ImportError, ValueError) as error:
                raise ModuleDiscoveryError(
                    f"cannot import manifest module '{manifest_module_name}'"
                ) from error

            manifest = getattr(manifest_module, "manifest", None)
            if not isinstance(manifest, ModuleManifest):
                raise ModuleDiscoveryError(
                    f"'{manifest_module_name}' must expose a ModuleManifest named 'manifest'"
                )
            manifests.append(manifest)

        return tuple(manifests)
