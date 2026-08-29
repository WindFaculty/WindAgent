"""Immutable Base Layer Safety Guard for Continual Harness (Phase 10 — ban_ke_hoach_v1 §15, §29).

Enforces strict isolation of the immutable base layer:
- Base system instructions cannot be overwritten or self-edited.
- Core security policy cannot be relaxed or bypassed.
- Permission model & Capability broker cannot be modified by candidates.
- Promotion policy, eligibility gates, and audit requirements are immutable.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from windagent_core.domain.harness import HarnessEntry, HarnessEntryKind

FORBIDDEN_IMMUTABLE_PATTERNS = [
    r"disable\s+security",
    r"bypass\s+(permission|policy|auth|gate|audit)",
    r"override\s+(security|permission|promotion|audit)",
    r"ignore\s+(safety|permission|policy|rules)",
    r"grant\s+all\s+permissions",
    r"admin\s+override",
    r"jailbreak",
    r"ignore\s+previous\s+instructions",
    r"disregard\s+system\s+instructions",
    r"elevate\s+privilege",
    r"disable\s+fencing",
    r"disable\s+lease",
    r"delete\s+audit\s+log",
]

PROTECTED_POLICY_NAMES = {
    "core_security_policy",
    "permission_model",
    "capability_broker",
    "promotion_policy",
    "audit_policy",
    "base_system_instructions",
    "immutable_base_policy",
    "eligibility_gate_policy",
}


class ImmutableBaseViolationError(ValueError):
    """Raised when a candidate or refinement attempts to tamper with the immutable base layer."""
    pass


class ImmutableBaseGuard:
    """Zero-tolerance security guard protecting WindAgent immutable core invariants."""

    @classmethod
    def check_text(cls, text: str) -> Tuple[bool, Optional[str]]:
        """Checks a text snippet against forbidden immutable tampering patterns."""
        if not text:
            return True, None

        normalized = text.lower()
        for pattern in FORBIDDEN_IMMUTABLE_PATTERNS:
            if re.search(pattern, normalized):
                return False, f"Forbidden immutable base tampering pattern detected: '{pattern}'"

        return True, None

    @classmethod
    def check_entry(cls, entry: HarnessEntry) -> Tuple[bool, Optional[str]]:
        """Validates that an individual HarnessEntry respects immutable base policies."""
        # 1. Check protected entry names
        normalized_name = entry.name.strip().lower()
        if normalized_name in PROTECTED_POLICY_NAMES:
            return False, f"Cannot override protected immutable policy entry: '{entry.name}'"

        # 2. Check kind-specific restrictions
        if entry.kind == HarnessEntryKind.ROUTING_POLICY:
            # Cannot route to unverified external security authorities
            route_target = str(entry.content.get("target", "")).lower()
            if "bypass" in route_target or "unfiltered" in route_target:
                return False, f"Routing policy cannot route to bypass targets: '{route_target}'"

        # 3. Check text content for forbidden patterns
        content_str = str(entry.content)
        is_safe, violation = cls.check_text(content_str)
        if not is_safe:
            return False, violation

        is_safe, violation = cls.check_text(entry.name)
        if not is_safe:
            return False, violation

        return True, None

    @classmethod
    def validate_entries(cls, entries: List[HarnessEntry]) -> None:
        """Validates a batch of harness entries, raising ImmutableBaseViolationError on any violation."""
        for entry in entries:
            is_safe, violation = cls.check_entry(entry)
            if not is_safe:
                raise ImmutableBaseViolationError(
                    f"Entry '{entry.name}' (id={entry.entry_id}, kind={entry.kind.value}) "
                    f"violates immutable base policy: {violation}"
                )

    @classmethod
    def is_valid_refinement(cls, entries: List[HarnessEntry]) -> Tuple[bool, List[str]]:
        """Non-raising validation helper returning boolean and list of violation messages."""
        violations = []
        for entry in entries:
            is_safe, violation = cls.check_entry(entry)
            if not is_safe and violation:
                violations.append(f"[{entry.name}]: {violation}")
        return len(violations) == 0, violations

