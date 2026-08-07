"""
Capability matching for the Universal Asset Gateway (VP3D Phase 5).

Matching happens BEFORE any provider call: a requirement is compared against
each adapter's declared ``AssetProviderCapability`` and either matches or
returns the exhaustive list of unsatisfied constraints (typed rejection via
``CapabilityRejectedError``). Providers never receive a requirement they cannot
serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from windagent_core.domain.video_production.asset_resolution import (
    AssetProviderCapability,
    AssetRequirement,
    LicenseConstraint,
    ProviderAvailability,
)


@dataclass(frozen=True)
class CapabilityMatch:
    """Outcome of matching one requirement against one capability."""

    matched: bool
    reasons: Tuple[str, ...] = ()

    @property
    def rejection_reasons(self) -> List[str]:
        return list(self.reasons)


class CapabilityMatcher:
    """Deterministic capability matching (fail closed on ANY mismatch)."""

    def match(
        self,
        requirement: AssetRequirement,
        capability: AssetProviderCapability,
    ) -> CapabilityMatch:
        reasons: List[str] = []

        if capability.availability != ProviderAvailability.READY:
            reasons.append(
                f"provider not ready (availability={capability.availability.value})"
            )
        if requirement.kind not in capability.supported_kinds:
            reasons.append(
                f"kind {requirement.kind.value!r} not supported"
            )
        if requirement.style not in capability.supported_styles:
            reasons.append(
                f"style {requirement.style.value!r} not supported"
            )
        if requirement.rig_required.value != "NO_RIG" and not capability.rig_supported:
            reasons.append(
                f"rig {requirement.rig_required.value!r} not supported"
            )
        if (
            capability.max_texture_resolution > 0
            and requirement.texture_resolution > capability.max_texture_resolution
        ):
            reasons.append(
                f"texture resolution {requirement.texture_resolution} > max "
                f"{capability.max_texture_resolution}"
            )
        if requirement.license_constraint != LicenseConstraint.UNSPECIFIED:
            if requirement.license_constraint not in capability.license_constraints:
                reasons.append(
                    f"license constraint {requirement.license_constraint.value!r} "
                    "not supported"
                )
        if (
            capability.max_polygons is not None
            and requirement.budget.max_polygons > capability.max_polygons
        ):
            reasons.append(
                f"polygon budget {requirement.budget.max_polygons} > max "
                f"{capability.max_polygons}"
            )
        if (
            capability.max_file_bytes is not None
            and requirement.budget.max_file_bytes > capability.max_file_bytes
        ):
            reasons.append(
                f"file budget {requirement.budget.max_file_bytes} > max "
                f"{capability.max_file_bytes}"
            )

        return CapabilityMatch(matched=not reasons, reasons=tuple(reasons))


def find_capable_adapters(
    requirement: AssetRequirement,
    capabilities: Sequence[AssetProviderCapability],
) -> List[AssetProviderCapability]:
    """Return every capability that can serve the requirement, in order."""
    matcher = CapabilityMatcher()
    return [cap for cap in capabilities if matcher.match(requirement, cap).matched]


__all__ = ["CapabilityMatch", "CapabilityMatcher", "find_capable_adapters"]
